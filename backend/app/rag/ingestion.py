"""Ingestion pipeline: bytes -> pages -> normalized text -> chunks -> embeddings in Chroma."""

import hashlib

from app.rag.chunking import chunk_pages
from app.rag.loaders import extract_pages
from app.rag.vector_store import VectorStore


def content_hash(data: bytes) -> str:
    """SHA-256 of the raw bytes, used to detect the same file being uploaded twice."""
    return hashlib.sha256(data).hexdigest()


def ingest_document(
    data: bytes,
    *,
    file_type: str,
    owner_id: str,
    document_id: str,
    filename: str,
    vector_store: VectorStore,
    chunk_size: int,
    chunk_overlap: int,
) -> int:
    """Index one document and return its chunk count. Safe to re-run for the same document_id."""
    pages = extract_pages(data, file_type)
    chunks = chunk_pages(
        pages,
        owner_id=owner_id,
        document_id=document_id,
        filename=filename,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    vector_store.replace_document_chunks(document_id, chunks)
    return len(chunks)
