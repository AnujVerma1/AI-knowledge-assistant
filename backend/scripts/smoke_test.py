"""End-to-end smoke test against a running API (real database, vector store and model).

    python -m scripts.smoke_test                      # http://127.0.0.1:8001
    python -m scripts.smoke_test https://your-api.example.com

Creates two throwaway users, uploads the sample documents, asks questions and checks user
isolation, then deletes the documents and conversations it created.
"""

import sys
import time
import uuid
from pathlib import Path

import httpx

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


class Session:
    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=180)

    def register(self) -> str:
        email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
        response = self.http.post("/api/auth/register", json={"email": email, "password": "smoke-test-password"})
        _expect(response, 201)
        self.http.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return email

    def call(self, method: str, path: str, expected: int, **kwargs) -> httpx.Response:
        return _expect(self.http.request(method, path, **kwargs), expected)


def _expect(response: httpx.Response, status: int) -> httpx.Response:
    if response.status_code != status:
        raise AssertionError(f"{response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}: {response.text}")
    return response


def step(message: str) -> None:
    print(f"  ok  {message}", flush=True)


def main(base_url: str) -> None:
    print(f"Smoke test against {base_url}")
    alice, bob = Session(base_url), Session(base_url)
    alice.register()
    bob.register()
    step("registered two users (session cookie + CSRF token)")
    alice.call("GET", "/api/health/ready", 200)
    step("database ready")

    document_ids = []
    for path in (SAMPLES / "northwind_handbook.txt", SAMPLES / "northwind_security_policy.pdf"):
        response = alice.call("POST", "/api/documents", 202, files={"file": (path.name, path.read_bytes())})
        document_ids.append(response.json()["id"])
    for document_id in document_ids:
        deadline = time.monotonic() + 300
        while (document := alice.call("GET", f"/api/documents/{document_id}", 200).json())["status"] == "processing":
            if time.monotonic() > deadline:
                raise AssertionError("document processing timed out")
            time.sleep(2)
        assert document["status"] == "ready", document
        step(f"{document['filename']} indexed: {document['chunk_count']} chunks")

    duplicate = alice.call("POST", "/api/documents", 409, files={"file": ("again.txt", (SAMPLES / "northwind_handbook.txt").read_bytes())})
    step(f"duplicate upload rejected: {duplicate.json()['error']['message']}")

    conversation_id = alice.call("POST", "/api/conversations", 201, json={}).json()["id"]
    for question in ("How fast must the on-call engineer respond to a P1 incident?", "What is the capital of France?"):
        started = time.perf_counter()
        body = alice.call("POST", f"/api/conversations/{conversation_id}/messages", 200, json={"content": question}).json()
        answer = body["assistant_message"]
        sources = ", ".join(f"{c['filename']} p.{c['page']}" if c["page"] else c["filename"] for c in answer["citations"]) or "none"
        step(f"asked {question!r} ({time.perf_counter() - started:.1f}s)\n        answer: {answer['content']!r}\n        sources: {sources}")

    bob_conversation = bob.call("POST", "/api/conversations", 201, json={}).json()["id"]
    leaked = bob.call("POST", f"/api/conversations/{bob_conversation}/messages", 200, json={"content": "How fast must a P1 incident be answered?"}).json()
    assert leaked["sufficient_evidence"] is False and leaked["assistant_message"]["citations"] == [], leaked
    bob.call("GET", f"/api/documents/{document_ids[0]}", 404)
    bob.call("GET", f"/api/conversations/{conversation_id}", 404)
    step("second user cannot retrieve, read or cite the first user's data")

    for document_id in document_ids:
        alice.call("DELETE", f"/api/documents/{document_id}", 204)
    after = alice.call("POST", f"/api/conversations/{conversation_id}/messages", 200, json={"content": "How fast must a P1 incident be answered?"}).json()
    assert after["sufficient_evidence"] is False, after
    step("deleted documents are no longer used for answers")

    history = alice.call("GET", f"/api/conversations/{conversation_id}", 200).json()
    step(f"conversation '{history['title']}' stored {len(history['messages'])} messages")
    alice.call("DELETE", f"/api/conversations/{conversation_id}", 204)
    bob.call("DELETE", f"/api/conversations/{bob_conversation}", 204)
    alice.call("POST", "/api/auth/logout", 204)
    alice.call("GET", "/api/auth/me", 401)
    step("cleaned up and logged out")
    print("Smoke test passed.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001")
