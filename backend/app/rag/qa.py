"""Question answering: retrieve, check sufficiency, generate, validate, cite."""

import logging
import re
from collections.abc import Collection

from langchain_core.language_models import BaseChatModel

from app.rag.prompts import INSUFFICIENT_EVIDENCE_MARKER, build_messages, source_label
from app.rag.providers import classify_provider_error
from app.rag.types import ChatTurn, Citation, RagAnswer, RetrievedChunk
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "I couldn't find enough information in your documents to answer that. "
    "Try rephrasing the question, or upload a document that covers this topic."
)
EXCERPT_CHARS = 300

_BRACKETED = re.compile(r"\[([^\[\]]{1,40})\]")
_LABEL_LIST = re.compile(r"\s*S\d+(\s*,\s*S\d+)*\s*")


def answer_question(
    question: str,
    *,
    owner_id: str,
    vector_store: VectorStore,
    chat_model: BaseChatModel,
    top_k: int,
    min_relevance: float,
    relevance_margin: float,
    history: list[ChatTurn] | None = None,
    document_ids: Collection[str] | None = None,
) -> RagAnswer:
    retrieved = vector_store.search(question, owner_id=owner_id, k=top_k, document_ids=document_ids)
    evidence = select_evidence(retrieved, min_relevance=min_relevance, margin=relevance_margin)
    logger.info(
        "Retrieval finished",
        extra={"retrieved": len(retrieved), "above_threshold": len(evidence), "top_score": max((c.score for c in retrieved), default=None)},
    )
    if not evidence:
        # No usable evidence: answer without calling the model, so it cannot make something up.
        return RagAnswer(answer=INSUFFICIENT_EVIDENCE_ANSWER, citations=[], sufficient_evidence=False)

    raw_answer = generate(chat_model, build_messages(question, evidence, history or []))
    return validate_answer(raw_answer, evidence)


def select_evidence(chunks: list[RetrievedChunk], *, min_relevance: float, margin: float) -> list[RetrievedChunk]:
    """Keep chunks above an absolute threshold and close to the best match.

    The absolute threshold rejects questions the documents do not cover; the margin removes
    weakly related chunks that add noise (and tokens) without adding evidence.
    """
    relevant = [c for c in chunks if c.score >= min_relevance]
    if not relevant:
        return []
    best = max(c.score for c in relevant)
    return [c for c in relevant if c.score >= best - margin]


def generate(chat_model: BaseChatModel, messages: list) -> str:
    try:
        return _text_content(chat_model.invoke(messages).content)
    except Exception as exc:
        logger.warning("Chat model call failed: %s", type(exc).__name__)
        raise classify_provider_error(exc) from exc


def _text_content(content: str | list) -> str:
    # Some providers return a list of content blocks instead of a plain string.
    if isinstance(content, str):
        return content
    return "".join(block if isinstance(block, str) else str(block.get("text", "")) for block in content)


def validate_answer(raw_answer: str, evidence: list[RetrievedChunk]) -> RagAnswer:
    """Turn raw model output into a safe answer whose citations come only from retrieved chunks.

    The model may only reference labels; source names, pages and excerpts are always taken from
    the retrieved chunks themselves, so it cannot invent a citation.
    """
    text = raw_answer.strip()
    if not text or INSUFFICIENT_EVIDENCE_MARKER in text:
        return RagAnswer(answer=INSUFFICIENT_EVIDENCE_ANSWER, citations=[], sufficient_evidence=False)

    valid_labels = {source_label(i): chunk for i, chunk in enumerate(evidence)}
    cited: list[str] = []

    def keep_valid_labels(match: re.Match) -> str:
        content = match.group(1)
        if not _LABEL_LIST.fullmatch(content):
            return match.group(0)  # ordinary bracketed text, not a citation
        labels = [label.strip() for label in content.split(",") if label.strip() in valid_labels]
        for label in labels:
            if label not in cited:
                cited.append(label)
        return "".join(f"[{label}]" for label in labels)

    text = _BRACKETED.sub(keep_valid_labels, text).strip()

    # Small models often forget to cite. Then every chunk given to the model is shown as a source,
    # which is still truthful: the answer was generated from exactly these chunks.
    labels = sorted(cited, key=lambda label: int(label[1:])) if cited else list(valid_labels)
    citations = [_citation(label, valid_labels[label]) for label in labels]
    return RagAnswer(answer=text, citations=citations, sufficient_evidence=True)


def _citation(label: str, chunk: RetrievedChunk) -> Citation:
    excerpt = chunk.text if len(chunk.text) <= EXCERPT_CHARS else chunk.text[:EXCERPT_CHARS].rstrip() + "..."
    return Citation(
        label=label,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        page=chunk.page,
        excerpt=excerpt,
        score=round(chunk.score, 4),
    )


