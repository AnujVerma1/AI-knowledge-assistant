import json
from pathlib import Path

import pytest

from app.rag.chunking import chunk_pages
from app.rag.loaders import extract_pages
from app.rag.types import RetrievedChunk
from evaluation.metrics import (
    contains_fact,
    first_relevant_rank,
    mean_reciprocal_rank,
    missing_facts,
    percentile,
    recall_at_k,
    ungrounded_numbers,
)

DATASET = Path(__file__).resolve().parents[1] / "evaluation" / "dataset.json"
SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _chunk(filename: str, page: int | None, text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id="c", document_id="d", filename=filename, page=page, text=text, score=0.8)


def test_relevance_requires_file_page_and_evidence():
    chunks = [
        _chunk("other.pdf", 3, "respond within 15 minutes"),
        _chunk("policy.pdf", 2, "respond within 15 minutes"),
        _chunk("policy.pdf", 3, "on-call engineer must respond\nwithin 15   minutes"),
    ]
    assert first_relevant_rank(chunks, "policy.pdf", 3, "respond within 15 minutes") == 3
    assert first_relevant_rank(chunks, "policy.pdf", 1, "respond within 15 minutes") is None


def test_recall_and_mrr():
    ranks = [1, 3, None, 5]
    assert recall_at_k(ranks, 1) == 0.25
    assert recall_at_k(ranks, 5) == 0.75
    assert mean_reciprocal_rank(ranks) == pytest.approx((1 + 1 / 3 + 1 / 5) / 4)


def test_key_facts_match_whole_words_and_alternatives():
    assert contains_fact("Lock after 5 minutes [S1].", ["5", "five"])
    assert not contains_fact("Lock after 15 minutes.", ["5"])
    assert missing_facts("The team lead must approve.", [["team lead"], ["HR"]]) == ["HR"]


def test_ungrounded_numbers_ignore_separators_and_citation_labels():
    passages = ["The sum insured is INR 5,00,000 per family per year."]
    assert ungrounded_numbers("INR 500,000 per year [S1].", passages) == []
    assert ungrounded_numbers("INR 7,00,000 per year.", passages) == ["7,00,000"]


def test_percentile_nearest_rank():
    assert percentile([5, 1, 3, 2, 4], 50) == 3
    assert percentile([5, 1, 3, 2, 4], 95) == 5


def test_every_evidence_passage_exists_in_the_sample_documents():
    """Guards the dataset itself: a typo in an evidence string would silently lower recall."""
    chunks = []
    for path in sorted(SAMPLES.iterdir()):
        pages = extract_pages(path.read_bytes(), path.suffix[1:])
        for doc in chunk_pages(pages, owner_id="x", document_id=path.stem, filename=path.name, chunk_size=1000, chunk_overlap=150):
            chunks.append(_chunk(path.name, doc.metadata.get("page"), doc.page_content))

    questions = json.loads(DATASET.read_text(encoding="utf-8"))["questions"]
    assert 30 <= len(questions) <= 50
    for q in (q for q in questions if q["answerable"]):
        source = q["source"]
        assert first_relevant_rank(chunks, source["file"], source["page"], q["evidence"]) is not None, q["id"]
