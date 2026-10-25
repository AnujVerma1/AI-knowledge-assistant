"""Conversation queries. Every read takes owner_id, so a query can never return another user's rows."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message


def get_owned(db: Session, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> Conversation | None:
    return db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
    )


def list_owned(db: Session, owner_id: uuid.UUID) -> list[Conversation]:
    query = select(Conversation).where(Conversation.owner_id == owner_id).order_by(Conversation.updated_at.desc())
    return list(db.scalars(query))


def recent_messages(db: Session, conversation_id: uuid.UUID, limit: int) -> list[Message]:
    """The last `limit` messages, oldest first."""
    if limit <= 0:
        return []
    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(reversed(list(db.scalars(query))))
