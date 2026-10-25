"""PgVectorStore against the real Neon database (run with: $env:RUN_INTEGRATION="1"; pytest tests/integration).

The store opens its own sessions; here they are bound to one connection whose outer transaction
is rolled back at the end, so the tests leave no data behind.
"""

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import PGVECTOR_DIMENSIONS
from app.db.session import get_engine
from app.models import Document, DocumentChunk, DocumentStatus, User
from app.rag.chunking import chunk_pages
from app.rag.pgvector_store import PgVectorStore
from app.rag.types import PageText
from tests.fakes import BagOfWordsEmbeddings

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to run")

MODEL = "fake-bag-of-words"


@pytest.fixture
def factory():
    connection = get_engine().connect()
    transaction = connection.begin()
    try:
        yield sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def store(factory) -> PgVectorStore:
    return PgVectorStore(factory, BagOfWordsEmbeddings(PGVECTOR_DIMENSIONS), MODEL)


def _user(factory) -> uuid.UUID:
    with factory() as db:
        user = User(email=f"{uuid.uuid4().hex[:10]}@example.com", password_hash="x")
        db.add(user)
        db.commit()
        return user.id


def _document(factory, owner_id: uuid.UUID, text: str, status: str = DocumentStatus.READY) -> str:
    document_id = uuid.uuid4()
    with factory() as db:
        db.add(
            Document(
                id=document_id,
                owner_id=owner_id,
                filename=f"{document_id}.txt",
                file_type="txt",
                size_bytes=len(text),
                storage_key=f"{owner_id}/{document_id}.txt",
                content_hash=uuid.uuid4().hex,
                status=status,
                chunk_count=0,
            )
        )
        db.commit()
    return str(document_id)


def _index(store: PgVectorStore, owner_id: uuid.UUID, document_id: str, text: str) -> None:
    chunks = chunk_pages(
        [PageText(1, text)], owner_id=str(owner_id), document_id=document_id, filename="f.txt", chunk_size=200, chunk_overlap=20
    )
    store.replace_document_chunks(document_id, chunks)


def test_search_is_scoped_to_owner_and_ready_documents(store, factory):
    alice, bob = _user(factory), _user(factory)
    alice_doc = _document(factory, alice, "Alice salary review happens in April.")
    bob_doc = _document(factory, bob, "Bob salary review happens in October.")
    processing_doc = _document(factory, alice, "Salary review drafts are still processing.", DocumentStatus.PROCESSING)
    _index(store, alice, alice_doc, "Alice salary review happens in April.")
    _index(store, bob, bob_doc, "Bob salary review happens in October.")
    _index(store, alice, processing_doc, "Salary review drafts are still processing.")

    results = store.search("When is the salary review?", owner_id=str(alice), k=10)

    assert [r.document_id for r in results] == [alice_doc]
    assert results[0].page == 1
    assert 0 < results[0].score <= 1


def test_document_filter_and_relevance_order(store, factory):
    owner = _user(factory)
    leave = _document(factory, owner, "leave")
    laptops = _document(factory, owner, "laptops")
    _index(store, owner, leave, "Employees get 24 days of paid leave every year.")
    _index(store, owner, laptops, "Laptops must use full disk encryption.")

    ranked = store.search("paid leave days", owner_id=str(owner), k=2)
    assert ranked[0].document_id == leave
    assert ranked[0].score > ranked[1].score

    only_laptops = store.search("paid leave days", owner_id=str(owner), k=5, document_ids={laptops})
    assert {r.document_id for r in only_laptops} == {laptops}
    assert store.search("anything", owner_id=str(owner), k=5, document_ids=set()) == []


def test_reindex_replaces_chunks_and_delete_cascades(store, factory):
    owner = _user(factory)
    document_id = _document(factory, owner, "policy")
    _index(store, owner, document_id, "Old policy text. " * 40)
    _index(store, owner, document_id, "New short policy text.")

    with factory() as db:
        contents = db.scalars(select(DocumentChunk.content).where(DocumentChunk.document_id == uuid.UUID(document_id))).all()
        assert contents == ["New short policy text."]
        db.delete(db.get(Document, uuid.UUID(document_id)))
        db.commit()
        remaining = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id))).all()
        assert remaining == []  # ON DELETE CASCADE removed the vectors with the document


def test_vectors_from_another_embedding_model_are_ignored(store, factory):
    owner = _user(factory)
    document_id = _document(factory, owner, "leave")
    _index(store, owner, document_id, "Employees get 24 days of paid leave.")

    other_model = PgVectorStore(factory, BagOfWordsEmbeddings(PGVECTOR_DIMENSIONS), "some-other-model")
    assert other_model.search("paid leave", owner_id=str(owner), k=5) == []
    assert store.delete_document(document_id) == 1
