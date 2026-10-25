import uuid

import httpx

from app.api.deps import get_chat_model
from app.models import Document, DocumentStatus
from app.rag.qa import INSUFFICIENT_EVIDENCE_ANSWER
from tests.api.conftest import upload
from tests.fakes import RaisingChatModel

HANDBOOK = b"Employees get 24 days of paid leave per year. Unused leave days expire on 31 March."
QUESTION = "How many days of paid leave do employees get?"


def _conversation(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


def _ask(client, conversation_id: str, content: str = QUESTION, **extra):
    return client.post(f"/api/conversations/{conversation_id}/messages", json={"content": content, **extra})


def test_question_is_answered_with_citations_and_saved(alice, chat_model):
    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    conversation_id = _conversation(alice)

    response = _ask(alice, conversation_id)
    assert response.status_code == 200
    body = response.json()
    assert body["sufficient_evidence"] is True
    assert body["assistant_message"]["content"] == "Employees get 24 days of paid leave per year [S1]."
    [citation] = body["assistant_message"]["citations"]
    assert citation["document_id"] == document_id
    assert citation["filename"] == "handbook.txt"
    assert "24 days" in citation["excerpt"]

    # The prompt sent to the model contained the user's document as evidence.
    assert "24 days of paid leave" in chat_model.calls[0][-1].content

    conversation = alice.get(f"/api/conversations/{conversation_id}").json()
    assert conversation["title"] == QUESTION
    assert [m["role"] for m in conversation["messages"]] == ["user", "assistant"]
    assert conversation["messages"][1]["citations"][0]["document_id"] == document_id


def test_one_users_documents_never_reach_another_users_answers(alice, bob, chat_model):
    upload(alice, "handbook.txt", HANDBOOK)
    response = _ask(bob, _conversation(bob))

    assert response.json()["sufficient_evidence"] is False
    assert response.json()["assistant_message"]["content"] == INSUFFICIENT_EVIDENCE_ANSWER
    assert response.json()["assistant_message"]["citations"] == []
    assert chat_model.calls == []  # no evidence -> the model is not even called


def test_users_cannot_access_each_others_conversations(alice, bob):
    conversation_id = _conversation(alice)
    assert bob.get("/api/conversations").json()["conversations"] == []
    assert bob.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert _ask(bob, conversation_id).status_code == 404
    assert bob.delete(f"/api/conversations/{conversation_id}").status_code == 404
    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 200


def test_selecting_another_users_document_is_rejected(alice, bob):
    alice_document = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    response = _ask(bob, _conversation(bob), document_ids=[alice_document])
    assert response.status_code == 400


def test_deleting_documents_hides_them_even_if_vectors_remain(alice, chat_model, session_factory):
    document_id = upload(alice, "handbook.txt", HANDBOOK).json()["id"]
    # Simulate a deletion that has started but has not cleaned up the vectors yet.
    with session_factory() as db:
        db.get(Document, uuid.UUID(document_id)).status = DocumentStatus.DELETING
        db.commit()

    response = _ask(alice, _conversation(alice))
    assert response.json()["sufficient_evidence"] is False
    assert chat_model.calls == []


def test_model_failure_returns_a_safe_error_and_saves_nothing(api, alice):
    upload(alice, "handbook.txt", HANDBOOK)
    conversation_id = _conversation(alice)

    api.dependency_overrides[get_chat_model] = lambda: RaisingChatModel(ConnectionError("ollama down"))
    unavailable = _ask(alice, conversation_id)
    api.dependency_overrides[get_chat_model] = lambda: RaisingChatModel(httpx.ReadTimeout("slow"))
    timeout = _ask(alice, conversation_id)

    assert (unavailable.status_code, unavailable.json()["error"]["code"]) == (503, "model_unavailable")
    assert (timeout.status_code, timeout.json()["error"]["code"]) == (504, "model_timeout")
    assert "ollama" not in unavailable.text.lower()
    assert alice.get(f"/api/conversations/{conversation_id}").json()["messages"] == []


def test_follow_up_questions_include_recent_history_but_not_as_evidence(alice, chat_model):
    upload(alice, "handbook.txt", HANDBOOK)
    conversation_id = _conversation(alice)
    _ask(alice, conversation_id)
    _ask(alice, conversation_id, "When do unused leave days expire?")

    second_prompt = chat_model.calls[1]
    assert [m.type for m in second_prompt] == ["system", "human", "ai", "human"]
    assert second_prompt[1].content == QUESTION
    assert "<documents>" in second_prompt[-1].content
    assert "<documents>" not in second_prompt[2].content


def test_deleting_a_conversation_removes_it(alice):
    conversation_id = _conversation(alice)
    assert alice.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert alice.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_question_validation(alice):
    conversation_id = _conversation(alice)
    assert _ask(alice, conversation_id, "   ").status_code == 422
    assert _ask(alice, conversation_id, "x" * 2001).status_code == 422
