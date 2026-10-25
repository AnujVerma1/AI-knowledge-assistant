import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Response, UploadFile
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    CsrfProtected,
    CurrentUser,
    SessionDep,
    SettingsDep,
    get_storage,
    get_vector_store,
)
from app.core.errors import NotFoundError
from app.core.rate_limit import rate_limiter
from app.db.session import get_session_factory
from app.models import Document, DocumentStatus
from app.rag.vector_store import VectorStore
from app.repositories import documents as documents_repo
from app.schemas.documents import DocumentListOut, DocumentOut
from app.services import documents as documents_service
from app.services.storage import FileStorage

router = APIRouter(prefix="/documents", tags=["documents"])

StorageDep = Annotated[FileStorage, Depends(get_storage)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]

_CONTENT_TYPES = {"pdf": "application/pdf", "txt": "text/plain; charset=utf-8"}


def _owned_document(db: Session, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document:
    document = documents_repo.get_owned(db, document_id, owner_id)
    # Another user's document gets the same 404 as a missing one, so IDs cannot be probed.
    if document is None or document.status == DocumentStatus.DELETING:
        raise NotFoundError("Document not found.")
    return document


@router.post("", status_code=202, response_model=DocumentOut, dependencies=[CsrfProtected])
def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    vector_store: VectorStoreDep,
    session_factory: SessionFactoryDep,
):
    """Validates and stores the file, then indexes it in the background (status: processing -> ready | failed)."""
    rate_limiter.check(f"upload:{user.id}", settings.upload_rate_limit_per_minute)
    data = file.file.read(settings.max_upload_bytes + 1)
    document = documents_service.upload_document(
        db, owner_id=user.id, filename=file.filename, data=data, storage=storage, settings=settings
    )
    background_tasks.add_task(
        documents_service.process_document,
        document.id,
        session_factory=session_factory,
        storage=storage,
        vector_store=vector_store,
        settings=settings,
    )
    return document


@router.get("", response_model=DocumentListOut)
def list_documents(user: CurrentUser, db: SessionDep):
    return DocumentListOut(documents=documents_repo.list_owned(db, user.id))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, user: CurrentUser, db: SessionDep):
    return _owned_document(db, document_id, user.id)


@router.get("/{document_id}/file")
def download_document(document_id: uuid.UUID, user: CurrentUser, db: SessionDep, storage: StorageDep):
    """Returns the original file so citations can be opened (append #page=N for PDFs)."""
    document = _owned_document(db, document_id, user.id)
    return Response(
        content=storage.read(document.storage_key),
        media_type=_CONTENT_TYPES[document.file_type],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{document_id}/retry", status_code=202, response_model=DocumentOut, dependencies=[CsrfProtected])
def retry_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    vector_store: VectorStoreDep,
    session_factory: SessionFactoryDep,
):
    document = _owned_document(db, document_id, user.id)
    documents_service.mark_for_retry(db, document)
    background_tasks.add_task(
        documents_service.process_document,
        document.id,
        session_factory=session_factory,
        storage=storage,
        vector_store=vector_store,
        settings=settings,
    )
    return document


@router.delete("/{document_id}", status_code=204, dependencies=[CsrfProtected])
def delete_document(
    document_id: uuid.UUID, user: CurrentUser, db: SessionDep, storage: StorageDep, vector_store: VectorStoreDep
) -> None:
    document = documents_repo.get_owned(db, document_id, user.id)
    if document is None:  # a document stuck in 'deleting' may be deleted again to finish cleanup
        raise NotFoundError("Document not found.")
    documents_service.delete_document(db, document, storage=storage, vector_store=vector_store)
