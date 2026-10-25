import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import PGVECTOR_DIMENSIONS
from app.db.base import Base


class DocumentChunk(Base):
    """One embedded chunk (used when VECTOR_STORE=pgvector).

    Chunks reference their document with ON DELETE CASCADE, so deleting a document removes its
    vectors in the same transaction. Searches join to documents and only use 'ready' rows.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunks_owner_id_embedding_model", "owner_id", "embedding_model"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # "<document_id>:<chunk_index>"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    # Duplicated from documents for a direct tenant filter; enforced by the foreign key.
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    # Vectors from different models are never compared: every search filters on this column.
    embedding_model: Mapped[str] = mapped_column(String(100))
    chunk_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(PGVECTOR_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
