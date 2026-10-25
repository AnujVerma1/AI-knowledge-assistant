import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from app.api.deps import CsrfProtected, CurrentUser, SessionDep, SettingsDep, get_chat_model, get_vector_store
from app.core.errors import NotFoundError
from app.core.rate_limit import rate_limiter
from app.models import Conversation
from app.rag.vector_store import VectorStore
from app.repositories import conversations as conversations_repo
from app.schemas.conversations import (
    AskRequest,
    AskResponse,
    ConversationCreate,
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    MessageOut,
)
from app.services import chat as chat_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _owned_conversation(db: Session, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> Conversation:
    conversation = conversations_repo.get_owned(db, conversation_id, owner_id)
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


@router.post("", status_code=201, response_model=ConversationOut, dependencies=[CsrfProtected])
def create_conversation(body: ConversationCreate, user: CurrentUser, db: SessionDep):
    title = (body.title or "").strip() or chat_service.DEFAULT_TITLE
    conversation = Conversation(owner_id=user.id, title=title)
    db.add(conversation)
    db.commit()
    return conversation


@router.get("", response_model=ConversationListOut)
def list_conversations(user: CurrentUser, db: SessionDep):
    return ConversationListOut(conversations=conversations_repo.list_owned(db, user.id))


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: SessionDep):
    return _owned_conversation(db, conversation_id, user.id)


@router.delete("/{conversation_id}", status_code=204, dependencies=[CsrfProtected])
def delete_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> None:
    db.delete(_owned_conversation(db, conversation_id, user.id))
    db.commit()


@router.post("/{conversation_id}/messages", response_model=AskResponse, dependencies=[CsrfProtected])
def ask_question(
    conversation_id: uuid.UUID,
    body: AskRequest,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    chat_model: Annotated[BaseChatModel, Depends(get_chat_model)],
):
    rate_limiter.check(f"chat:{user.id}", settings.chat_rate_limit_per_minute)
    conversation = _owned_conversation(db, conversation_id, user.id)
    user_message, assistant_message, result = chat_service.ask(
        db,
        conversation,
        owner_id=user.id,
        question=body.content,
        document_ids=body.document_ids,
        vector_store=vector_store,
        chat_model=chat_model,
        settings=settings,
    )
    return AskResponse(
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
        sufficient_evidence=result.sufficient_evidence,
    )
