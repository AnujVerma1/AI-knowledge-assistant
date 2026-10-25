"""Phase 1 environment check.

Run from the backend folder with the virtual environment active:
    python -m scripts.check_env

Verifies that configuration, Ollama (chat + embedding models), Chroma and PostgreSQL
work together before any application code depends on them. Prints no secrets.
"""

import os
import sys
import tempfile
import time
from collections.abc import Callable

# Chroma reads this from the process environment, not from our .env file.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings


class SkipCheck(Exception):
    """Raised when a check does not apply to the current configuration."""


results: list[str] = []


def run_check(name: str, check: Callable[[], str]) -> None:
    try:
        status, detail = "PASS", check()
    except SkipCheck as exc:
        status, detail = "SKIP", str(exc)
    except Exception as exc:  # noqa: BLE001 - report every failure and keep going
        status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
    results.append(status)
    print(f"[{status}] {name}: {detail}", flush=True)


def _with_tag(model: str) -> str:
    return model if ":" in model else f"{model}:latest"


def check_ollama_server(settings: Settings) -> str:
    if settings.llm_provider != "ollama" and settings.embedding_provider != "ollama":
        raise SkipCheck("no provider is set to ollama")
    base = settings.ollama_base_url.rstrip("/")
    version = httpx.get(f"{base}/api/version", timeout=5).json()["version"]
    installed = {m["name"] for m in httpx.get(f"{base}/api/tags", timeout=5).json()["models"]}
    wanted = []
    if settings.llm_provider == "ollama":
        wanted.append(settings.ollama_model)
    if settings.embedding_provider == "ollama":
        wanted.append(settings.embedding_model)
    missing = [m for m in wanted if _with_tag(m) not in installed]
    if missing:
        raise RuntimeError(f"models not pulled: {', '.join(missing)} (run: ollama pull <model>)")
    return f"Ollama {version} at {base}, models present: {', '.join(wanted)}"


def check_chat_model(settings: Settings) -> str:
    if settings.llm_provider != "ollama":
        raise SkipCheck(f"LLM_PROVIDER={settings.llm_provider} is checked in a later phase")
    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=settings.ollama_num_ctx,
        num_predict=40,
        client_kwargs={"timeout": settings.llm_timeout_seconds},
    )
    started = time.perf_counter()
    reply = llm.invoke("In one short sentence, confirm that you are working.")
    elapsed = time.perf_counter() - started
    text = str(reply.content).strip()
    if not text:
        raise RuntimeError("model returned an empty reply")
    return f"{elapsed:.1f}s (includes model load on first run) -> {text[:100]!r}"


def make_embeddings(settings: Settings):
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.llm_timeout_seconds},
    )


def check_embedding_model(settings: Settings) -> str:
    if settings.embedding_provider != "ollama":
        raise SkipCheck(f"EMBEDDING_PROVIDER={settings.embedding_provider} is checked in a later phase")
    vector = make_embeddings(settings).embed_query("What is the refund policy?")
    return f"{settings.embedding_model} returned a {len(vector)}-dimensional vector"


def check_chroma(settings: Settings) -> str:
    if settings.embedding_provider != "ollama":
        raise SkipCheck("needs the Ollama embedding model in this phase")
    from langchain_chroma import Chroma

    # A throwaway store in a temp folder, so the real data/chroma directory stays untouched.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = Chroma(
            collection_name="phase1_check",
            embedding_function=make_embeddings(settings),
            persist_directory=tmp,
        )
        store.add_texts(
            texts=[
                "Annual plans can be refunded within 30 days of purchase.",
                "The office is closed on national holidays.",
                "Passwords must be at least 12 characters long.",
            ],
            metadatas=[{"source": "policy.txt", "page": n} for n in (1, 2, 3)],
            ids=["chunk-1", "chunk-2", "chunk-3"],
        )
        doc, distance = store.similarity_search_with_score("How long do I have to get my money back?", k=1)[0]
    if "refunded" not in doc.page_content:
        raise RuntimeError(f"unexpected top result: {doc.page_content!r}")
    return f"stored 3 chunks, top result = page {doc.metadata['page']} (distance {distance:.3f})"


def check_database(settings: Settings) -> str:
    from sqlalchemy import text

    from app.db.session import get_engine

    # Uses the application's own engine (pooled URL, same connection options).
    with get_engine().connect() as conn:
        version = conn.execute(text("select version()")).scalar_one()
        host = conn.execute(text("select current_database()")).scalar_one()
    return f"{version.split(' on ')[0]}, database {host!r}"


def main() -> int:
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    try:
        settings = get_settings()
    except ValidationError as exc:
        print("[FAIL] configuration: backend/.env is incomplete or invalid:")
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"]).upper() or "(settings)"
            print(f"    {field}: {error['msg']}")
        return 1
    print("[PASS] configuration: backend/.env loaded")

    run_check("ollama server", lambda: check_ollama_server(settings))
    run_check("chat model", lambda: check_chat_model(settings))
    run_check("embedding model", lambda: check_embedding_model(settings))
    run_check("chroma round-trip", lambda: check_chroma(settings))
    run_check("postgresql", lambda: check_database(settings))

    failed = results.count("FAIL")
    print(f"\n{len(results) - failed}/{len(results)} checks passed or skipped.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
