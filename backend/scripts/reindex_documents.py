"""Rebuild the vectors of every 'ready' document with the currently configured embedding model.

Run after changing EMBEDDING_PROVIDER / EMBEDDING_MODEL (each model has its own collection):
    python -m scripts.reindex_documents

Original files are read from file storage, so nothing has to be uploaded again. Documents are
processed one at a time to stay within free-tier rate limits; failures are reported and skipped.
"""

import os
import sys
import time

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from sqlalchemy import select

from app.api.deps import get_storage, get_vector_store
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session_factory
from app.models import Document, DocumentStatus
from app.rag.ingestion import ingest_document
from app.rag.vector_store import collection_name_for


def main() -> int:
    settings = get_settings()
    storage, vector_store = get_storage(), get_vector_store()
    print(f"Re-indexing into collection '{collection_name_for(settings)}' ({settings.embedding_provider}: {settings.embedding_model})")

    with get_session_factory()() as db:
        documents = list(db.scalars(select(Document).where(Document.status == DocumentStatus.READY)))
        failures = 0
        for document in documents:
            started = time.perf_counter()
            try:
                count = ingest_document(
                    storage.read(document.storage_key),
                    file_type=document.file_type,
                    owner_id=str(document.owner_id),
                    document_id=str(document.id),
                    filename=document.filename,
                    vector_store=vector_store,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )
            except AppError as exc:
                failures += 1
                print(f"  FAILED {document.filename}: {exc.message}")
                continue
            document.chunk_count = count
            db.commit()
            print(f"  ok {document.filename}: {count} chunks ({time.perf_counter() - started:.1f}s)")

    print(f"Done: {len(documents) - failures}/{len(documents)} documents re-indexed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
