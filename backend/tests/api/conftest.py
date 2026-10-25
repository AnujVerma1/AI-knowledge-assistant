"""API test setup: an in-memory SQLite database, fake models and temporary storage.

These tests check HTTP behaviour, authentication and authorization quickly and offline.
PostgreSQL-specific behaviour is covered by tests/integration against Neon.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables
from app.api.deps import get_chat_model, get_storage, get_vector_store
from app.core.rate_limit import rate_limiter
from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.services.storage import LocalFileStorage
from tests.fakes import RecordingChatModel


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    # document_chunks needs PostgreSQL's pgvector; it is covered by tests/integration instead.
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "document_chunks"])
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def chat_model():
    return RecordingChatModel("Employees get 24 days of paid leave per year [S1].")


@pytest.fixture
def storage(tmp_path):
    return LocalFileStorage(tmp_path / "uploads")


@pytest.fixture
def api(session_factory, vector_store, chat_model, storage):
    rate_limiter.reset()
    application = create_app()

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides.update(
        {
            get_db: override_db,
            get_session_factory: lambda: session_factory,
            get_vector_store: lambda: vector_store,
            get_chat_model: lambda: chat_model,
            get_storage: lambda: storage,
        }
    )
    return application


@pytest.fixture
def make_client(api):
    """Each client has its own cookie jar, i.e. acts as a separate browser."""
    clients = []

    def _make() -> TestClient:
        client = TestClient(api)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def register(client: TestClient, email: str, password: str = "correct-horse-battery") -> dict:
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    # Behave like the frontend: send the CSRF token back on state-changing requests.
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


@pytest.fixture
def alice(make_client) -> TestClient:
    client = make_client()
    register(client, "alice@example.com")
    return client


@pytest.fixture
def bob(make_client) -> TestClient:
    client = make_client()
    register(client, "bob@example.com")
    return client


def upload(client: TestClient, filename: str, data: bytes):
    return client.post("/api/documents", files={"file": (filename, data)})
