"""Answering a question inside a conversation, with per-user document access enforced."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from langchain_core.language_models import BaseChatModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import BadRequestError, NotFoundError
from app.models import Conversation, Message, MessageRole
from app.rag.qa import answer_question
from app.rag.types import ChatTurn, RagAnswer
from app.rag.vector_store import VectorStore
from app.repositories import conversations as conversations_repo
from app.repositories import documents as documents_repo

DEFAULT_TITLE = "New conversation"
TITLE_CHARS = 60


def ask(
    db: Session,
    conversation: Conversation,
    *,
    owner_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID] | None,
    vector_store: VectorStore,
    chat_model: BaseChatModel,
    settings: Settings,
) -> tuple[Message, Message, RagAnswer]:
    # The searchable set comes from PostgreSQL, not from the request or the vector store:
    # only this user's documents whose status is 'ready' right now.
    allowed = documents_repo.ready_ids(db, owner_id, among=document_ids)
    if document_ids is not None and set(document_ids) - allowed:
        raise BadRequestError("Some selected documents are not available. They may still be processing or have been deleted.")

    history = [
        ChatTurn(role=m.role, content=m.content)
        for m in conversations_repo.recent_messages(db, conversation.id, settings.history_window_messages)
    ]
    asked_at = datetime.now(UTC)
    db.commit()  # end the read transaction so no connection is held during the model call

    result = answer_question(
        question,
        owner_id=str(owner_id),
        vector_store=vector_store,
        chat_model=chat_model,
        top_k=settings.retrieval_top_k,
        min_relevance=settings.min_relevance_score,
        relevance_margin=settings.relevance_margin,
        history=history,
        document_ids={str(i) for i in allowed},
    )

    # Nothing is saved if retrieval or the model failed, so a failed request leaves no half-answer.
    user_message = Message(conversation_id=conversation.id, role=MessageRole.USER, content=question, created_at=asked_at)
    assistant_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=result.answer,
        citations=[asdict(c) for c in result.citations],
        created_at=datetime.now(UTC),
    )
    if conversation.title == DEFAULT_TITLE:
        conversation.title = _title_from(question)
    conversation.updated_at = datetime.now(UTC)
    db.add_all([user_message, assistant_message])
    try:
        db.commit()
    except IntegrityError as exc:  # the conversation was deleted while the answer was generated
        db.rollback()
        raise NotFoundError("The conversation no longer exists.") from exc
    return user_message, assistant_message, result


def _title_from(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= TITLE_CHARS else title[: TITLE_CHARS - 3].rstrip() + "..."
