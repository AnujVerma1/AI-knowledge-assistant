import pytest

from app.core.errors import EmbeddingError
from app.rag.chunking import chunk_pages
from app.rag.ingestion import ingest_document
from app.rag.providers import GuardedEmbeddings
from app.rag.types import PageText
from app.rag.vector_store import ChromaVectorStore
from tests.fakes import FailingEmbeddings


def _ingest(store, text: str, *, owner_id: str, document_id: str) -> int:
    return ingest_document(
        text.encode(),
        file_type="txt",
        owner_id=owner_id,
        document_id=document_id,
        filename=f"{document_id}.txt",
        vector_store=store,
        chunk_size=500,
        chunk_overlap=50,
    )


def test_search_only_returns_the_owners_chunks(vector_store):
    _ingest(vector_store, "Alice's salary review happens in April every year.", owner_id="alice", document_id="a1")
    _ingest(vector_store, "Bob's salary review happens in October every year.", owner_id="bob", document_id="b1")

    results = vector_store.search("When is the salary review?", owner_id="bob", k=10)

    assert [c.document_id for c in results] == ["b1"]
    assert all("Alice" not in c.text for c in results)


def test_search_can_be_limited_to_selected_documents(vector_store):
    _ingest(vector_store, "Refunds are processed within 7 days.", owner_id="u", document_id="d1")
    _ingest(vector_store, "Refunds require a receipt.", owner_id="u", document_id="d2")

    assert {c.document_id for c in vector_store.search("refunds", owner_id="u", k=10, document_ids={"d2"})} == {"d2"}
    assert vector_store.search("refunds", owner_id="u", k=10, document_ids=set()) == []


def test_delete_document_removes_all_its_chunks(vector_store):
    _ingest(vector_store, "Paragraph about onboarding. " * 60, owner_id="u", document_id="d1")
    _ingest(vector_store, "Onboarding checklist for interns.", owner_id="u", document_id="d2")

    assert vector_store.delete_document("d1") > 1
    assert {c.document_id for c in vector_store.search("onboarding", owner_id="u", k=10)} == {"d2"}


def test_reindexing_replaces_stale_chunks(vector_store):
    _ingest(vector_store, "Old policy text. " * 100, owner_id="u", document_id="d1")
    assert _ingest(vector_store, "New short policy text.", owner_id="u", document_id="d1") == 1

    results = vector_store.search("policy text", owner_id="u", k=10)
    assert len(results) == 1
    assert results[0].text == "New short policy text."


def test_embedding_failure_is_reported_as_embedding_error(tmp_path):
    import chromadb

    store = ChromaVectorStore(chromadb.PersistentClient(path=str(tmp_path)), "failing", GuardedEmbeddings(FailingEmbeddings()))
    chunks = chunk_pages([PageText(None, "text")], owner_id="u", document_id="d", filename="f.txt", chunk_size=100, chunk_overlap=0)
    with pytest.raises(EmbeddingError):
        store.replace_document_chunks("d", chunks)
    with pytest.raises(EmbeddingError):
        store.search("text", owner_id="u", k=3)
