import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListOut(BaseModel):
    conversations: list[ConversationOut]


class CitationOut(BaseModel):
    label: str
    document_id: uuid.UUID
    filename: str
    page: int | None
    excerpt: str
    chunk_id: str
    score: float


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    citations: list[CitationOut] | None
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class AskRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    # Limit the question to these documents; None means all of the user's ready documents.
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be empty")
        return value


class AskResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    sufficient_evidence: bool
