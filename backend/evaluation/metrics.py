"""Evaluation metrics in plain Python (no evaluation framework).

Retrieval is scored against a labelled passage; answers are scored with deterministic checks
(key facts, citations, number grounding) that are cheap, repeatable and easy to explain. They
are proxies: a correct answer worded unusually can fail a key-fact check, and a check passing
does not prove an answer is fully correct.
"""

import math
import re
from collections.abc import Iterable, Sequence

from app.rag.types import RetrievedChunk

_CITATION_LABEL = re.compile(r"\[S\d+\]")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize(text: str) -> str:
    """Lower-case and collapse all whitespace, so line breaks inside passages do not matter."""
    return " ".join(text.lower().split())


def is_relevant(chunk: RetrievedChunk, expected_file: str, expected_page: int | None, evidence: str) -> bool:
    """A chunk is relevant if it comes from the expected file/page and contains the evidence passage."""
    if chunk.filename != expected_file:
        return False
    if expected_page is not None and chunk.page != expected_page:
        return False
    return normalize(evidence) in normalize(chunk.text)


def first_relevant_rank(chunks: Sequence[RetrievedChunk], expected_file: str, expected_page: int | None, evidence: str) -> int | None:
    """1-based rank of the first relevant chunk, or None if no retrieved chunk is relevant."""
    for rank, chunk in enumerate(chunks, start=1):
        if is_relevant(chunk, expected_file, expected_page, evidence):
            return rank
    return None


def recall_at_k(ranks: Iterable[int | None], k: int) -> float:
    """Share of questions whose relevant passage is among the top k results."""
    ranks = list(ranks)
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else math.nan


def mean_reciprocal_rank(ranks: Iterable[int | None]) -> float:
    """Average of 1/rank (0 when not retrieved): rewards putting the right passage first."""
    ranks = list(ranks)
    return sum(1 / r for r in ranks if r is not None) / len(ranks) if ranks else math.nan


def contains_fact(text: str, alternatives: Sequence[str]) -> bool:
    """True if any accepted spelling of a fact appears in the text as a whole word or phrase."""
    haystack = normalize(_CITATION_LABEL.sub(" ", text))
    for alternative in alternatives:
        pattern = r"(?<![\w])" + re.escape(normalize(alternative)) + r"(?![\w])"
        if re.search(pattern, haystack):
            return True
    return False


def missing_facts(answer: str, key_facts: Sequence[Sequence[str]]) -> list[str]:
    """The key facts (first spelling shown) that the answer does not contain."""
    return [alternatives[0] for alternatives in key_facts if not contains_fact(answer, alternatives)]


def ungrounded_numbers(answer: str, passages: Iterable[str]) -> list[str]:
    """Numbers stated in the answer that appear in none of the passages given to the model.

    An invented figure is the most damaging kind of unsupported claim in policy documents, and
    it can be detected without a judge model. Thousands separators are ignored on both sides
    (INR 5,00,000 and 500000 count as the same number).
    """
    source_numbers = {n.replace(",", "") for passage in passages for n in _NUMBER.findall(passage)}
    answer_numbers = _NUMBER.findall(_CITATION_LABEL.sub(" ", answer))
    return sorted({n for n in answer_numbers if n.replace(",", "") not in source_numbers})


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100)."""
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[index]
