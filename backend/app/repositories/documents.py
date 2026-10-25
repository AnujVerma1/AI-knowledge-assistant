"""Document queries. Every read takes owner_id, so a query can never return another user's rows."""

import uuid
from collections.abc import Collection

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Document, DocumentStatus


def get_owned(db: Session, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document | None:
    return db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner_id))


def get_by_hash(db: Session, owner_id: uuid.UUID, content_hash: str) -> Document | None:
    return db.scalar(select(Document).where(Document.owner_id == owner_id, Document.content_hash == content_hash))


def list_owned(db: Session, owner_id: uuid.UUID) -> list[Document]:
    query = (
        select(Document)
        .where(Document.owner_id == owner_id, Document.status != DocumentStatus.DELETING)
        .order_by(Document.created_at.desc())
    )
    return list(db.scalars(query))


def ready_ids(db: Session, owner_id: uuid.UUID, among: Collection[uuid.UUID] | None = None) -> set[uuid.UUID]:
    """IDs of the owner's documents that may be searched right now."""
    query = select(Document.id).where(Document.owner_id == owner_id, Document.status == DocumentStatus.READY)
    if among is not None:
        query = query.where(Document.id.in_(list(among)))
    return set(db.scalars(query))


def ids_with_status(db: Session, status: DocumentStatus) -> list[uuid.UUID]:
    return list(db.scalars(select(Document.id).where(Document.status == status)))


def transition(
    db: Session, document_id: uuid.UUID, *, from_status: DocumentStatus, to_status: DocumentStatus, **values
) -> bool:
    """Atomically change status only if the document is still in from_status. Returns success."""
    result = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.status == from_status)
        .values(status=to_status, **values)
    )
    return result.rowcount == 1
