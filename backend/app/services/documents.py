"""Document lifecycle: upload -> processing -> ready | failed, and deletion.

Processing runs in a FastAPI background task inside the web process. That keeps the first
version simple, with known limits: work is lost if the process stops (recover_interrupted
marks such documents as failed so the user can retry), and documents are processed one at a
time per process.
"""

import logging
import threading
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, DocumentProcessingError, PayloadTooLargeError
from app.models import Document, DocumentStatus
from app.rag.ingestion import content_hash, ingest_document
from app.rag.loaders import detect_file_type, extract_pages
from app.rag.vector_store import VectorStore
from app.repositories import documents as documents_repo
from app.services.storage import FileStorage

logger = logging.getLogger(__name__)

# Embedding is CPU- and memory-heavy on small machines, so only one document is indexed at a time.
_INGESTION_LOCK = threading.Lock()

INTERRUPTED_MESSAGE = "Processing was interrupted by a server restart. Use Retry to process the document again."


def clean_filename(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if len(name) > 255:
        stem, _, extension = name.rpartition(".")
        name = f"{stem[: 250 - len(extension)]}.{extension}"
    return name or "document"


def upload_document(
    db: Session, *, owner_id: uuid.UUID, filename: str | None, data: bytes, storage: FileStorage, settings: Settings
) -> Document:
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"Files can be at most {settings.max_upload_mb} MB.")
    if not data:
        raise DocumentProcessingError("The file is empty.")
    filename = clean_filename(filename)
    file_type = detect_file_type(filename, data)
    # Extraction is fast; doing it now gives immediate feedback for empty, scanned or broken files.
    extract_pages(data, file_type)

    digest = content_hash(data)
    _raise_if_duplicate(db, owner_id, digest)

    document_id = uuid.uuid4()
    storage_key = f"{owner_id}/{document_id}.{file_type}"
    storage.save(storage_key, data)
    document = Document(
        id=document_id,
        owner_id=owner_id,
        filename=filename,
        file_type=file_type,
        size_bytes=len(data),
        storage_key=storage_key,
        content_hash=digest,
        status=DocumentStatus.PROCESSING,
        chunk_count=0,
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:  # the same file uploaded twice at the same moment
        db.rollback()
        storage.delete(storage_key)
        _raise_if_duplicate(db, owner_id, digest)
        raise
    return document


def _raise_if_duplicate(db: Session, owner_id: uuid.UUID, digest: str) -> None:
    existing = documents_repo.get_by_hash(db, owner_id, digest)
    if existing is not None:
        raise ConflictError(
            f"You already uploaded this file as '{existing.filename}'.",
            details={"document_id": str(existing.id), "status": existing.status},
        )


def process_document(
    document_id: uuid.UUID,
    *,
    session_factory: sessionmaker[Session],
    storage: FileStorage,
    vector_store: VectorStore,
    settings: Settings,
) -> None:
    with _INGESTION_LOCK:
        with session_factory() as db:
            document = db.get(Document, document_id)
            if document is None or document.status != DocumentStatus.PROCESSING:
                return
            owner_id, filename, file_type, storage_key = (
                document.owner_id,
                document.filename,
                document.file_type,
                document.storage_key,
            )
        # No database connection is held during the slow extraction and embedding work.
        try:
            chunk_count = ingest_document(
                storage.read(storage_key),
                file_type=file_type,
                owner_id=str(owner_id),
                document_id=str(document_id),
                filename=filename,
                vector_store=vector_store,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
        except Exception as exc:
            if isinstance(exc, AppError):
                message = exc.message
                logger.warning("Document processing failed", extra={"document_id": str(document_id), "error_code": exc.code})
            else:
                message = "An unexpected error occurred while processing the document."
                logger.exception("Document processing crashed", extra={"document_id": str(document_id)})
            with session_factory() as db:
                documents_repo.transition(
                    db,
                    document_id,
                    from_status=DocumentStatus.PROCESSING,
                    to_status=DocumentStatus.FAILED,
                    error_message=message[:500],
                    chunk_count=0,
                )
                db.commit()
            _delete_vectors_quietly(vector_store, document_id)
            return

        with session_factory() as db:
            marked_ready = documents_repo.transition(
                db,
                document_id,
                from_status=DocumentStatus.PROCESSING,
                to_status=DocumentStatus.READY,
                chunk_count=chunk_count,
                error_message=None,
            )
            db.commit()
        if not marked_ready:
            # The document was deleted while it was being processed: remove the new vectors too.
            _delete_vectors_quietly(vector_store, document_id)
        else:
            logger.info("Document ready", extra={"document_id": str(document_id), "chunks": chunk_count})


def mark_for_retry(db: Session, document: Document) -> None:
    if document.status != DocumentStatus.FAILED:
        raise ConflictError("Only documents that failed processing can be retried.")
    documents_repo.transition(
        db, document.id, from_status=DocumentStatus.FAILED, to_status=DocumentStatus.PROCESSING, error_message=None
    )
    db.commit()
    db.refresh(document)


def delete_document(db: Session, document: Document, *, storage: FileStorage, vector_store: VectorStore) -> None:
    """Hide the document first, then clean up its vectors and file, then remove the row.

    Retrieval only searches documents whose status is 'ready' in PostgreSQL, so from the first
    commit onwards the document's chunks can no longer reach an answer, even if vector cleanup
    fails. A failed cleanup leaves the row in 'deleting' so it can be retried.
    """
    document.status = DocumentStatus.DELETING
    db.commit()
    vector_store.delete_document(str(document.id))
    storage.delete(document.storage_key)
    db.delete(document)
    db.commit()


def recover_interrupted(session_factory: sessionmaker[Session], *, storage: FileStorage, vector_store: VectorStore) -> None:
    """Run at startup: resolve documents left mid-way by a previous process."""
    with session_factory() as db:
        for document_id in documents_repo.ids_with_status(db, DocumentStatus.PROCESSING):
            documents_repo.transition(
                db,
                document_id,
                from_status=DocumentStatus.PROCESSING,
                to_status=DocumentStatus.FAILED,
                error_message=INTERRUPTED_MESSAGE,
            )
        db.commit()
        for document_id in documents_repo.ids_with_status(db, DocumentStatus.DELETING):
            document = db.get(Document, document_id)
            try:
                delete_document(db, document, storage=storage, vector_store=vector_store)
            except Exception:
                db.rollback()
                logger.warning("Could not finish deleting a document", extra={"document_id": str(document_id)})


def _delete_vectors_quietly(vector_store: VectorStore, document_id: uuid.UUID) -> None:
    try:
        vector_store.delete_document(str(document_id))
    except Exception:
        logger.warning("Vector cleanup failed", extra={"document_id": str(document_id)})
