"""Shared FastAPI dependencies: authentication, CSRF and access to infrastructure.

Infrastructure objects (vector store, chat model, file storage) are created once and can be
replaced in tests through app.dependency_overrides.
"""

import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import ACCESS_COOKIE, CSRF_HEADER, TokenClaims, decode_session_token
from app.db.session import get_db, get_session_factory
from app.models import User
from app.rag import providers
from app.rag.pgvector_store import PgVectorStore
from app.rag.vector_store import ChromaVectorStore, VectorStore, build_chroma_client, collection_name_for
from app.repositories import users as users_repo
from app.services.storage import FileStorage, LocalFileStorage, S3FileStorage

SessionDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_token_claims(request: Request, settings: SettingsDep) -> TokenClaims:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise AuthenticationError()
    return decode_session_token(token, settings)


def get_current_user(claims: Annotated[TokenClaims, Depends(get_token_claims)], db: SessionDep) -> User:
    # The user identity comes only from the signed token, never from the request body or URL.
    user = users_repo.get_by_id(db, claims.user_id)
    if user is None:
        raise AuthenticationError()
    return user


def require_csrf(request: Request, claims: Annotated[TokenClaims, Depends(get_token_claims)]) -> None:
    header = request.headers.get(CSRF_HEADER, "")
    if not hmac.compare_digest(header.encode(), claims.csrf_token.encode()):
        raise PermissionDeniedError("Missing or invalid CSRF token. Refresh the page and try again.")


CurrentUser = Annotated[User, Depends(get_current_user)]
CsrfProtected = Depends(require_csrf)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    embeddings = providers.get_embeddings(settings)
    if settings.vector_store == "pgvector":
        return PgVectorStore(get_session_factory(), embeddings, settings.embedding_model)
    return ChromaVectorStore(build_chroma_client(settings), collection_name_for(settings), embeddings)


@lru_cache
def get_chat_model() -> BaseChatModel:
    return providers.get_chat_model(get_settings())


@lru_cache
def get_storage() -> FileStorage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3FileStorage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            region=settings.s3_region,
        )
    return LocalFileStorage(settings.local_upload_dir)
