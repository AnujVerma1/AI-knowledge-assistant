"""Plain data types passed between RAG pipeline stages."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class PageText:
    page: int | None  # 1-based page number; None for formats without pages (TXT)
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    text: str
    score: float  # cosine similarity in [-1, 1]; higher means more relevant


@dataclass(frozen=True)
class Citation:
    label: str  # "S1", "S2", ... as shown to the model
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    excerpt: str
    score: float


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    citations: list[Citation]
    sufficient_evidence: bool
    # The chunks that were given to the model (after the relevance filter); used for evaluation.
    evidence: list[RetrievedChunk] = field(default_factory=list)
