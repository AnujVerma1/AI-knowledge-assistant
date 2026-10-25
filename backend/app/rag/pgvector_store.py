"""Vector storage inside PostgreSQL with the pgvector extension (VECTOR_STORE=pgvector).

Compared with a separate vector database, chunks live next to the rows that own them:
- authorization and freshness are part of the search query (join to documents, status='ready');
- deleting a document cascades to its chunks in the same transaction;
- re-indexing replaces a document's chunks atomically (delete + insert in one transaction).

No ANN index is created: with a per-user filter, an exact scan is fast at this scale and
always returns the true nearest neighbours. An HNSW index becomes worthwhile around ~100k chunks.
"""

import uuid
from collections.abc import Collection

from langchain_core.documents import Document as LangChainDocument
from langchain_core.embeddings import Embeddings
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import PGVECTOR_DIMENSIONS
from app.core.errors import VectorStoreError
from app.models import Document, DocumentChunk, DocumentStatus
from app.rag.types import RetrievedChunk


class PgVectorStore:
    def __init__(self, session_factory: sessionmaker[Session], embeddings: Embeddings, embedding_model: str) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._model = embedding_model

    def replace_document_chunks(self, document_id: str, chunks: list[LangChainDocument]) -> None:
        # Embed first (slow, external) so no database transaction is held open meanwhile.
        vectors = self._embeddings.embed_documents([c.page_content for c in chunks]) if chunks else []
        for vector in vectors:
            if len(vector) != PGVECTOR_DIMENSIONS:
                raise VectorStoreError(f"Embedding has {len(vector)} dimensions; the database expects {PGVECTOR_DIMENSIONS}.")
        rows = [
            DocumentChunk(
                id=chunk.metadata["chunk_id"],
                document_id=uuid.UUID(document_id),
                owner_id=uuid.UUID(chunk.metadata["owner_id"]),
                embedding_model=self._model,
                chunk_index=chunk.metadata["chunk_index"],
                page=chunk.metadata.get("page"),
                content=chunk.page_content,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            with self._session_factory() as db, db.begin():
                db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id)))
                db.add_all(rows)
        except SQLAlchemyError as exc:  # includes the document being deleted meanwhile (foreign key)
            raise VectorStoreError() from exc

    def delete_document(self, document_id: str) -> int:
        try:
            with self._session_factory() as db, db.begin():
                result = db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id)))
                return result.rowcount
        except SQLAlchemyError as exc:
            raise VectorStoreError() from exc

    def search(
        self, query: str, *, owner_id: str, k: int, document_ids: Collection[str] | None = None
    ) -> list[RetrievedChunk]:
        if document_ids is not None and not document_ids:
            return []
        query_vector = self._embeddings.embed_query(query)
        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        statement = (
            select(DocumentChunk, Document.filename, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.owner_id == uuid.UUID(owner_id),
                Document.owner_id == uuid.UUID(owner_id),
                Document.status == DocumentStatus.READY,
                DocumentChunk.embedding_model == self._model,
            )
            .order_by(distance)
            .limit(k)
        )
        if document_ids is not None:
            statement = statement.where(DocumentChunk.document_id.in_([uuid.UUID(i) for i in document_ids]))
        try:
            with self._session_factory() as db:
                rows = db.execute(statement).all()
        except SQLAlchemyError as exc:
            raise VectorStoreError() from exc
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=str(chunk.document_id),
                filename=filename,
                page=chunk.page,
                text=chunk.content,
                score=1.0 - float(chunk_distance),
            )
            for chunk, filename, chunk_distance in rows
        ]
