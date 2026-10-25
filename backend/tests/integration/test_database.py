"""Schema tests against the real Neon database (run with: $env:RUN_INTEGRATION="1"; pytest tests/integration).

Every test works inside a transaction that is rolled back, so no data is left behind.
"""

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import Conversation, Document, Message, User

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="set RUN_INTEGRATION=1 to run")


@pytest.fixture
def db():
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _user(db: Session, email: str | None = None) -> User:
    user = User(email=email or f"{uuid.uuid4().hex[:8]}@example.com", password_hash="not-a-real-hash")
    db.add(user)
    db.flush()
    return user


def _document(owner: User, content_hash: str = "a" * 64) -> Document:
    return Document(
        owner_id=owner.id,
        filename="policy.pdf",
        file_type="pdf",
        size_bytes=1234,
        storage_key=f"{owner.id}/{uuid.uuid4()}.pdf",
        content_hash=content_hash,
    )


def test_conversation_with_citations_round_trip(db):
    user = _user(db)
    conversation = Conversation(owner_id=user.id, title="Leave policy")
    conversation.messages = [
        Message(role="user", content="How many leave days?"),
        Message(role="assistant", content="24 days [S1].", citations=[{"label": "S1", "page": 3}]),
    ]
    db.add(conversation)
    db.flush()
    db.expire_all()

    loaded = db.scalars(select(Conversation).where(Conversation.owner_id == user.id)).one()
    assert [m.role for m in loaded.messages] == ["user", "assistant"]
    assert loaded.messages[1].citations == [{"label": "S1", "page": 3}]


def test_uppercase_email_is_rejected_by_the_database(db):
    with pytest.raises(IntegrityError):
        _user(db, email="Someone@Example.com")


def test_same_file_twice_for_one_user_is_rejected_but_allowed_for_another(db):
    alice, bob = _user(db), _user(db)
    db.add_all([_document(alice), _document(bob)])
    db.flush()

    db.add(_document(alice))
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_a_user_cascades_to_their_data(db):
    user = _user(db)
    conversation = Conversation(owner_id=user.id, title="t", messages=[Message(role="user", content="hi")])
    db.add_all([conversation, _document(user)])
    db.flush()
    user_id, conversation_id = user.id, conversation.id

    db.delete(user)
    db.flush()
    db.expire_all()

    assert db.scalar(select(Document).where(Document.owner_id == user_id)) is None
    assert db.scalar(select(Conversation).where(Conversation.id == conversation_id)) is None
    assert db.scalar(select(Message).where(Message.conversation_id == conversation_id)) is None
