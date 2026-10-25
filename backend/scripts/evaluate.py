"""Evaluate retrieval and answer quality on the labelled dataset (evaluation/dataset.json).

    python -m scripts.evaluate                    # retrieval + answers with the configured models
    python -m scripts.evaluate --judge            # also ask the chat model whether answers are supported
    python -m scripts.evaluate --retrieval-only   # embeddings only, no chat-model calls

The sample documents are indexed into a temporary Chroma collection with the configured
embedding model and the production chunking settings; no database or user data is touched.
Answers go through the same answer_question() used by the API (threshold, prompt, validation).
Results are printed and saved to evaluation/results/<timestamp>.json and evaluation/REPORT.md.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.config import Settings as ChromaClientSettings
from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.core.errors import AppError, ModelRateLimitedError
from app.rag.ingestion import ingest_document
from app.rag.providers import get_chat_model, get_embeddings
from app.rag.qa import answer_question, generate
from app.rag.types import RagAnswer
from app.rag.vector_store import ChromaVectorStore
from evaluation.metrics import (
    first_relevant_rank,
    is_relevant,
    mean_reciprocal_rank,
    missing_facts,
    percentile,
    recall_at_k,
    ungrounded_numbers,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
EVALUATION_DIR = BACKEND_DIR / "evaluation"
SAMPLES_DIR = BACKEND_DIR.parent / "samples"
OWNER_ID = "evaluation"
RECALL_KS = (1, 3, 5)

T = TypeVar("T")


class CachedEmbeddings(Embeddings):
    """Avoids embedding the same question twice (raw retrieval + answer pipeline)."""

    def __init__(self, inner: Embeddings) -> None:
        self._inner = inner
        self._queries: dict[str, list[float]] = {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if text not in self._queries:
            self._queries[text] = self._inner.embed_query(text)
        return self._queries[text]


class BackoffClock:
    """Total time spent waiting after rate limits, so latency figures can exclude it."""

    waited_s = 0.0
    retries = 0


def with_retry(call: Callable[[], T], attempts: int = 4) -> T:
    """Free tiers allow few requests per minute: wait and retry when rate limited."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except ModelRateLimitedError:
            if attempt == attempts:
                raise
            wait = 20 * attempt
            print(f"    rate limited, waiting {wait}s", flush=True)
            BackoffClock.retries += 1
            BackoffClock.waited_s += wait
            time.sleep(wait)
    raise AssertionError("unreachable")


JUDGE_PROMPT = """You check whether an ANSWER is fully supported by the PASSAGES.
A statement is supported only if the passages state it (paraphrasing is fine). Ignore citation labels such as [S1].
Reply with JSON only, no other text: {"supported": true or false, "unsupported_claims": ["..."]}"""


def judge_support(chat_model, answer: str, passages: list[str]) -> tuple[bool | None, list[str]]:
    body = "\n\n".join(f"<passage>\n{p}\n</passage>" for p in passages)
    raw = with_retry(lambda: generate(chat_model, [SystemMessage(JUDGE_PROMPT), HumanMessage(f"PASSAGES:\n{body}\n\nANSWER:\n{answer}")]))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        verdict = json.loads(match.group(0)) if match else {}
        return bool(verdict["supported"]), [str(c) for c in verdict.get("unsupported_claims", [])]
    except (ValueError, KeyError, TypeError):
        return None, [f"unparseable judge output: {raw[:120]!r}"]


def build_index(settings, embeddings: Embeddings, directory: str) -> tuple[ChromaVectorStore, int]:
    client = chromadb.PersistentClient(path=directory, settings=ChromaClientSettings(anonymized_telemetry=False))
    store = ChromaVectorStore(client, "evaluation", embeddings)
    total = 0
    for path in sorted(SAMPLES_DIR.iterdir()):
        total += with_retry(
            lambda path=path: ingest_document(
                path.read_bytes(),
                file_type=path.suffix[1:],
                owner_id=OWNER_ID,
                document_id=path.name,
                filename=path.name,
                vector_store=store,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
        )
    return store, total


def evaluate_question(item: dict, store, chat_model, settings, *, retrieval_only: bool, judge: bool) -> dict:
    row: dict = {"id": item["id"], "question": item["question"], "answerable": item["answerable"]}
    retrieved = with_retry(lambda: store.search(item["question"], owner_id=OWNER_ID, k=max(RECALL_KS)))
    row["top_score"] = round(retrieved[0].score, 3) if retrieved else None
    if item["answerable"]:
        source = item["source"]
        row["rank"] = first_relevant_rank(retrieved, source["file"], source["page"], item["evidence"])
    if retrieval_only:
        return row

    started, waited_before = time.perf_counter(), BackoffClock.waited_s
    result: RagAnswer = with_retry(
        lambda: answer_question(
            item["question"],
            owner_id=OWNER_ID,
            vector_store=store,
            chat_model=chat_model,
            top_k=settings.retrieval_top_k,
            min_relevance=settings.min_relevance_score,
            relevance_margin=settings.relevance_margin,
        )
    )
    # Rate-limit back-off is the free tier's quota, not the pipeline's speed: exclude it.
    row["latency_s"] = round(time.perf_counter() - started - (BackoffClock.waited_s - waited_before), 2)
    row["answer"] = result.answer
    row["answered"] = result.sufficient_evidence
    row["evidence_chunks"] = len(result.evidence)
    passages = [c.text for c in result.evidence]

    if item["answerable"]:
        source = item["source"]
        relevant = lambda c: is_relevant(c, source["file"], source["page"], item["evidence"])  # noqa: E731
        row["context_hit"] = any(relevant(c) for c in result.evidence)
        if result.sufficient_evidence:
            by_id = {c.chunk_id: c for c in result.evidence}
            row["missing_facts"] = missing_facts(result.answer, item["key_facts"])
            row["citation_correct"] = any(relevant(by_id[c.chunk_id]) for c in result.citations if c.chunk_id in by_id)
            row["ungrounded_numbers"] = ungrounded_numbers(result.answer, passages)
            if judge:
                row["judge_supported"], row["judge_unsupported_claims"] = judge_support(chat_model, result.answer, passages)
    else:
        # Refused before the model was called (no chunk passed the threshold) or by the model itself.
        row["refused_by"] = None if result.sufficient_evidence else ("threshold" if not result.evidence else "model")
    return row


def rate(rows: list[dict], predicate: Callable[[dict], bool]) -> float | None:
    return round(sum(1 for r in rows if predicate(r)) / len(rows), 3) if rows else None


def summarize(rows: list[dict], *, retrieval_only: bool, judge: bool) -> dict:
    ok = [r for r in rows if "error" not in r]
    answerable = [r for r in ok if r["answerable"]]
    unanswerable = [r for r in ok if not r["answerable"]]
    ranks = [r["rank"] for r in answerable]
    summary: dict = {
        "questions": len(rows),
        "failed_requests": len(rows) - len(ok),
        "retrieval": {f"recall@{k}": round(recall_at_k(ranks, k), 3) for k in RECALL_KS}
        | {"mrr": round(mean_reciprocal_rank(ranks), 3), "n": len(answerable)},
    }
    if retrieval_only:
        return summary
    answered = [r for r in answerable if r["answered"]]
    summary["answerable"] = {
        "n": len(answerable),
        "answered_rate": rate(answerable, lambda r: r["answered"]),
        "context_recall": rate(answerable, lambda r: r["context_hit"]),
        "key_fact_accuracy": rate(answerable, lambda r: r["answered"] and not r["missing_facts"]),
        "citation_correctness": rate(answered, lambda r: r["citation_correct"]),
        "number_grounding": rate(answered, lambda r: not r["ungrounded_numbers"]),
    }
    if judge:
        judged = [r for r in answered if r.get("judge_supported") is not None]
        summary["answerable"]["judge_supported"] = rate(judged, lambda r: r["judge_supported"])
        summary["answerable"]["judge_n"] = len(judged)
    summary["unanswerable"] = {
        "n": len(unanswerable),
        "correct_refusal_rate": rate(unanswerable, lambda r: r["refused_by"] is not None),
        "refused_by_threshold": sum(1 for r in unanswerable if r["refused_by"] == "threshold"),
        "refused_by_model": sum(1 for r in unanswerable if r["refused_by"] == "model"),
    }
    latencies = [r["latency_s"] for r in ok]
    summary["latency_s"] = {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95), "max": max(latencies, default=None)}
    summary["rate_limit_retries"] = BackoffClock.retries
    return summary


def write_report(config: dict, summary: dict, rows: list[dict], json_path: Path) -> Path:
    def pct(value) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"

    retrieval = summary["retrieval"]
    lines = [
        "# Evaluation report",
        "",
        f"Generated by `python -m scripts.evaluate` on {config['run_at']} (raw results: `{json_path.relative_to(EVALUATION_DIR).as_posix()}`).",
        "",
        "## Setup",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Chat model | `{config['chat_model']}` |",
        f"| Embedding model | `{config['embedding_model']}` ({config['embedding_dimensions'] or 'default'} dimensions) |",
        f"| Corpus | {config['documents']} sample documents, {config['chunks']} chunks (chunk size {config['chunk_size']}, overlap {config['chunk_overlap']}) |",
        f"| Answer pipeline | top-{config['top_k']} retrieval, relevance threshold {config['min_relevance']}, margin {config['relevance_margin']} |",
        f"| Questions | {summary['questions']} ({retrieval['n']} answerable, {summary['questions'] - retrieval['n']} unanswerable), failed requests: {summary['failed_requests']} |",
        "",
        "## Retrieval (raw top-k, before the relevance threshold)",
        "",
        "| Recall@1 | Recall@3 | Recall@5 | MRR |",
        "|---|---|---|---|",
        f"| {pct(retrieval['recall@1'])} | {pct(retrieval['recall@3'])} | {pct(retrieval['recall@5'])} | {retrieval['mrr']:.3f} |",
        "",
        "Recall@k: share of answerable questions whose labelled passage is among the top k chunks. "
        "MRR: mean of 1/rank of that passage. With only "
        f"{config['chunks']} chunks in the corpus, Recall@5 is an easy bar; Recall@1 and MRR are more informative.",
    ]
    if "answerable" in summary:
        a, u, lat = summary["answerable"], summary["unanswerable"], summary["latency_s"]
        lines += [
            "",
            f"## Answers to answerable questions (n={a['n']})",
            "",
            "| Metric | Result | Meaning |",
            "|---|---|---|",
            f"| Answered | {pct(a['answered_rate'])} | Did not wrongly refuse |",
            f"| Context recall | {pct(a['context_recall'])} | The labelled passage was among the chunks sent to the model |",
            f"| Key-fact accuracy | {pct(a['key_fact_accuracy'])} | Answered and contains every expected key fact |",
            f"| Citation correctness | {pct(a['citation_correctness'])} | Of answered: a cited source contains the labelled passage |",
            f"| Number grounding | {pct(a['number_grounding'])} | Of answered: every number in the answer appears in the passages |",
        ]
        if "judge_supported" in a:
            lines.append(
                f"| Supported (LLM judge) | {pct(a['judge_supported'])} | Of {a['judge_n']} judged: the chat model found no unsupported claim |"
            )
        lines += [
            "",
            f"## Unanswerable questions (n={u['n']})",
            "",
            f"Correct refusals: **{pct(u['correct_refusal_rate'])}** "
            f"({u['refused_by_threshold']} by the relevance threshold before any model call, {u['refused_by_model']} by the model).",
            "",
            "## Latency and reliability",
            "",
            f"Answer latency (embedding + retrieval + generation, measured from a laptop in India to the API): "
            f"p50 {lat['p50']} s, p95 {lat['p95']} s, max {lat['max']} s. "
            f"Rate-limit back-off is excluded ({summary['rate_limit_retries']} rate-limited requests were retried). "
            f"Failed requests: {summary['failed_requests']}. "
            "Unanswerable questions refused by the threshold make no model call, which lowers the median.",
        ]
        if all(v == 1.0 for v in (a["answered_rate"], a["key_fact_accuracy"], a["citation_correctness"], u["correct_refusal_rate"])):
            lines += [
                "",
                "**Reading these results:** every answer metric is at its maximum. On a dataset this small and "
                "self-written, that is a ceiling effect: the questions are not hard enough to separate a good system "
                "from a better one. Harder questions (multi-part, paraphrased, conflicting sources) are the next step.",
            ]
    problems = [r for r in rows if _problem(r)]
    lines += ["", "## Questions with any issue (including a passage not ranked first)", ""]
    if problems:
        lines += ["| ID | Question | Issue |", "|---|---|---|"]
        lines += [f"| {r['id']} | {r['question']} | {_problem(r)} |" for r in problems]
    else:
        lines.append("None.")
    lines += [
        "",
        "## Limitations",
        "",
        "- Small, synthetic corpus written for this project; results do not predict performance on large or messy document sets.",
        "- Key-fact and number checks are string matches: a correct answer phrased differently can fail, and passing does not prove the whole answer is right.",
        "- The LLM judge (when used) is the same model that wrote the answers, so it may share its blind spots.",
        "- Model outputs vary between runs; compare several runs before drawing conclusions from small differences.",
    ]
    report_path = EVALUATION_DIR / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _problem(row: dict) -> str:
    if "error" in row:
        return f"request failed: {row['error']}"
    issues = []
    if row["answerable"]:
        if row.get("rank") is None or row["rank"] > max(RECALL_KS):
            issues.append(f"passage not in top {max(RECALL_KS)}")
        elif row["rank"] > 1:
            issues.append(f"labelled passage ranked {row['rank']}, not first")
        if "answered" in row:
            if not row["answered"]:
                issues.append("wrongly refused")
            else:
                if row["missing_facts"]:
                    issues.append(f"missing facts {row['missing_facts']}")
                if not row["citation_correct"]:
                    issues.append("citation does not contain the passage")
                if row["ungrounded_numbers"]:
                    issues.append(f"numbers not in passages {row['ungrounded_numbers']}")
                if row.get("judge_supported") is False:
                    issues.append(f"judge: unsupported {row.get('judge_unsupported_claims')}")
    elif row.get("refused_by", "n/a") is None:
        issues.append(f"answered instead of refusing: {row['answer'][:80]!r}")
    return "; ".join(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retrieval-only", action="store_true", help="skip answer generation")
    parser.add_argument("--judge", action="store_true", help="also judge answer support with the chat model")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds to wait between questions (free-tier limits)")
    parser.add_argument("--limit", type=int, help="only evaluate the first N questions")
    args = parser.parse_args()

    settings = get_settings()
    questions = json.loads((EVALUATION_DIR / "dataset.json").read_text(encoding="utf-8"))["questions"][: args.limit]
    embeddings = CachedEmbeddings(get_embeddings(settings))
    chat_model = None if args.retrieval_only else get_chat_model(settings)
    chat_name = settings.hosted_llm_model if settings.llm_provider == "openai_compatible" else settings.ollama_model

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        store, chunk_count = build_index(settings, embeddings, directory)
        print(f"Indexed {len(list(SAMPLES_DIR.iterdir()))} documents into {chunk_count} chunks. Evaluating {len(questions)} questions...")
        rows = []
        for number, item in enumerate(questions, start=1):
            try:
                row = evaluate_question(item, store, chat_model, settings, retrieval_only=args.retrieval_only, judge=args.judge)
            except AppError as exc:
                row = {"id": item["id"], "question": item["question"], "answerable": item["answerable"], "error": exc.code}
            rows.append(row)
            status = _problem(row) or "ok"
            print(f"  [{number:2}/{len(questions)}] {item['id']:8} {status}", flush=True)
            if number < len(questions):
                time.sleep(args.delay)

    run_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    config = {
        "run_at": run_at,
        "chat_model": chat_name if not args.retrieval_only else None,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "documents": len(list(SAMPLES_DIR.iterdir())),
        "chunks": chunk_count,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "top_k": settings.retrieval_top_k,
        "min_relevance": settings.min_relevance_score,
        "relevance_margin": settings.relevance_margin,
        "judge": args.judge,
    }
    summary = summarize(rows, retrieval_only=args.retrieval_only, judge=args.judge)
    results_dir = EVALUATION_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    json_path.write_text(json.dumps({"config": config, "summary": summary, "questions": rows}, indent=2), encoding="utf-8")
    report_path = write_report(config, summary, rows, json_path)

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nSaved {json_path} and {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
