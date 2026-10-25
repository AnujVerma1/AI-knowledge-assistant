"""Vector storage: add, search and delete chunks, always scoped to one owner.

Two implementations share the VectorStore interface: ChromaVectorStore (below; local development
and tests) and PgVectorStore (app/rag/pgvector_store.py; PostgreSQL in production). VECTOR_STORE
selects one in app/api/deps.py.
"""

import logging
import re
from collections.abc import Collection
from typing import Protocol

import chromadb
from chromadb.config import Settings as ChromaClientSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.core.errors import EmbeddingError, VectorStoreError
from app.rag.types import RetrievedChunk

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    def replace_document_chunks(self, document_id: str, chunks: list[Document]) -> None:
        """Replace all chunks of a document (safe re-indexing)."""

    def delete_document(self, document_id: str) -> int:
        """Delete a document's chunks and return how many were removed."""

    def search(
        self, query: str, *, owner_id: str, k: int, document_ids: Collection[str] | None = None
    ) -> list[RetrievedChunk]:
        """The k nearest chunks owned by owner_id, optionally limited to some documents."""


def collection_name_for(settings: Settings, suffix: str = "") -> str:
    """One collection per embedding model.

    Vectors from different embedding models have different sizes and meanings and must never be
    compared. Switching EMBEDDING_MODEL therefore starts a fresh collection, which is filled by
    re-indexing (python -m scripts.reindex_documents).
    """
    model = re.sub(r"[^a-zA-Z0-9._-]+", "-", settings.embedding_model).strip("-._")
    dimensions = f"-{settings.embedding_dimensions}" if settings.embedding_dimensions else ""
    return f"{settings.chroma_collection}{suffix}_{model}{dimensions}"


def build_chroma_client(settings: Settings) -> chromadb.ClientAPI:
    if settings.chroma_mode == "cloud":
        return chromadb.CloudClient(
            tenant=settings.chroma_tenant,
            database=settings.chroma_database,
            api_key=settings.chroma_api_key.get_secret_value(),
        )
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(settings.chroma_persist_dir),
        settings=ChromaClientSettings(anonymized_telemetry=False),
    )


class ChromaVectorStore:
    def __init__(self, client: chromadb.ClientAPI, collection_name: str, embeddings: Embeddings) -> None:
        self._store = Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=embeddings,
            # Cosine distance makes scores comparable across queries, so one relevance threshold works.
            collection_metadata={"hnsw:space": "cosine"},
        )

    def replace_document_chunks(self, document_id: str, chunks: list[Document]) -> None:
        """Delete any existing chunks for the document, then add the new ones (safe re-indexing)."""
        self.delete_document(document_id)
        if not chunks:
            return
        try:
            self._store.add_documents(chunks, ids=[c.id for c in chunks])
        except EmbeddingError:
            raise
        except Exception as exc:
            raise VectorStoreError() from exc

    def delete_document(self, document_id: str) -> int:
        try:
            ids = self._store.get(where={"document_id": document_id}, include=[])["ids"]
            if ids:
                self._store.delete(ids=ids)
            return len(ids)
        except Exception as exc:
            raise VectorStoreError() from exc

    def search(
        self,
        query: str,
        *,
        owner_id: str,
        k: int,
        document_ids: Collection[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the k nearest chunks owned by owner_id, optionally limited to some documents.

        The owner filter runs inside Chroma, and every result is checked again here so a wrong
        filter can never leak another user's text into a prompt.
        """
        if document_ids is not None and not document_ids:
            return []
        where: dict = {"owner_id": owner_id}
        if document_ids is not None:
            where = {"$and": [where, {"document_id": {"$in": list(document_ids)}}]}
        try:
            results = self._store.similarity_search_with_score(query, k=k, filter=where)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise VectorStoreError() from exc

        chunks = []
        for doc, distance in results:
            metadata = doc.metadata
            if metadata.get("owner_id") != owner_id:
                logger.error("Discarded a retrieved chunk owned by another user", extra={"chunk_id": metadata.get("chunk_id")})
                continue
            if document_ids is not None and metadata.get("document_id") not in document_ids:
                continue
            chunks.append(
                RetrievedChunk(
                    chunk_id=metadata["chunk_id"],
                    document_id=metadata["document_id"],
                    filename=metadata["filename"],
                    page=metadata.get("page"),
                    text=doc.page_content,
                    score=1.0 - distance,
                )
            )
        return chunks
