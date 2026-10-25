import enum
import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DocumentStatus(enum.StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        # The same file (same bytes) can be uploaded once per user; other users are unaffected.
        UniqueConstraint("owner_id", "content_hash"),
        CheckConstraint("file_type IN ('pdf', 'txt')", name="file_type"),
        CheckConstraint("status IN ('processing', 'ready', 'failed', 'deleting')", name="status"),
        Index("ix_documents_owner_id_created_at", "owner_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Where the original file lives in file storage (a local path or an object-storage key).
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PROCESSING)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # A message that is safe to show to the user; internal details are only logged.
    error_message: Mapped[str | None] = mapped_column(String(500))
