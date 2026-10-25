import uuid

from app.api.deps import get_vector_store
from app.models import Document, DocumentStatus
from app.rag.providers import GuardedEmbeddings
from app.rag.vector_store import ChromaVectorStore
from app.services.documents import INTERRUPTED_MESSAGE
from tests.api.conftest import upload
from tests.fakes import FailingEmbeddings
from tests.pdf_factory import build_pdf

HANDBOOK = b"Employees get 24 days of paid leave per year. Unused leave days expire on 31 March."


def test_upload_is_processed_into_a_ready_document(alice, vector_store):
    response = upload(alice, "handbook.txt", HANDBOOK)
    assert response.status_code == 202
    assert response.json()["status"] == "processing"

    document = alice.get(f"/api/documents/{response.json()['id']}").json()  # background task has run
    assert document["status"] == "ready"
    assert document["chunk_count"] == 1

    me = alice.get("/api/auth/me").json()["user"]["id"]
    assert vector_store.search("paid leave", owner_id=me, k=4)[0].document_id == document["id"]


def test_pdf_upload_keeps_pages_and_can_be_downloaded(alice, vector_store):
    pdf = build_pdf(["Page one is about passwords.", "Page two is about laptops and encryption."])
    document = upload(alice, "policy.pdf", pdf).json()

    me = alice.get("/api/auth/me").json()["user"]["id"]
    hit = vector_store.search("laptops encryption", owner_id=me, k=1)[0]
    assert hit.page == 2

    download = alice.get(f"/api/documents/{document['id']}/file")
    assert download.status_code == 200
    assert download.content == pdf
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["x-content-type-options"] == "nosniff"


def test_invalid_files_are_rejected_with_clear_errors(alice):
    cases = {
        ("photo.png", b"\x89PNG\r\n"): (415, "unsupported_file"),
        ("fake.pdf", b"not really a pdf"): (415, "unsupported_file"),
        ("empty.txt", b""): (422, "document_unprocessable"),
        ("blank.txt", b"   \n  "): (422, "document_unprocessable"),
        ("scanned.pdf", build_pdf([""])): (422, "document_unprocessable"),
        ("broken.pdf", b"%PDF-1.4\n garbage"): (422, "document_unprocessable"),
    }
    for (filename, data), (status, code) in cases.items():
        response = upload(alice, filename, data)
        assert (response.status_code, response.json()["error"]["code"]) == (status, code), filename
    assert alice.get("/api/documents").json()["documents"] == []


def test_oversized_upload_is_rejected(alice):
    response = upload(alice, "big.txt", b"a" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_duplicate_upload_points_to_the_existing_document(alice, bob):
    first = upload(alice, "handbook.txt", HANDBOOK).json()
    again = upload(alice, "copy-of-handbook.txt", HANDBOOK)
    assert again.status_code == 409
    assert again.json()["error"]["details"]["document_id"] == first["id"]
    # Duplicate detection is per user: Bob may upload the same file.
    assert upload(bob, "handbook.txt", HANDBOOK).status_code == 202


def test_users_cannot_see_or_touch_each_others_documents(alice, bob):
    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]

    assert bob.get("/api/documents").json()["documents"] == []
    for method, path in [
        ("GET", f"/api/documents/{document_id}"),
        ("GET", f"/api/documents/{document_id}/file"),
        ("POST", f"/api/documents/{document_id}/retry"),
        ("DELETE", f"/api/documents/{document_id}"),
    ]:
        response = bob.request(method, path)
        assert response.status_code == 404, (method, path)
    assert alice.get(f"/api/documents/{document_id}").json()["status"] == "ready"


def test_delete_removes_row_vectors_and_file(alice, vector_store, storage, session_factory):
    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    with session_factory() as db:
        storage_key = db.get(Document, uuid.UUID(document_id)).storage_key

    assert alice.delete(f"/api/documents/{document_id}").status_code == 204

    me = alice.get("/api/auth/me").json()["user"]["id"]
    assert vector_store.search("paid leave", owner_id=me, k=4) == []
    assert alice.get(f"/api/documents/{document_id}").status_code == 404
    assert not (storage._root / storage_key).exists()


def test_processing_failure_is_reported_and_can_be_retried(api, alice, tmp_path):
    import chromadb

    failing_store = ChromaVectorStore(
        chromadb.PersistentClient(path=str(tmp_path / "failing")), "failing", GuardedEmbeddings(FailingEmbeddings())
    )
    api.dependency_overrides[get_vector_store] = lambda: failing_store

    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    document = alice.get(f"/api/documents/{document_id}").json()
    assert document["status"] == "failed"
    assert "embedding model is currently unavailable" in document["error_message"]

    retry = alice.post(f"/api/documents/{document_id}/retry")
    assert retry.status_code == 202
    assert alice.post(f"/api/documents/{document_id}/retry").status_code == 202  # failed again -> retryable


def test_ready_documents_cannot_be_retried(alice):
    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    assert alice.post(f"/api/documents/{document_id}/retry").status_code == 409


def test_startup_marks_interrupted_processing_as_failed(alice, session_factory, make_client):
    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    with session_factory() as db:
        db.get(Document, uuid.UUID(document_id)).status = DocumentStatus.PROCESSING
        db.commit()

    make_client()  # starting a new client runs the application's startup (lifespan) again

    document = alice.get(f"/api/documents/{document_id}").json()
    assert document["status"] == "failed"
    assert document["error_message"] == INTERRUPTED_MESSAGE
