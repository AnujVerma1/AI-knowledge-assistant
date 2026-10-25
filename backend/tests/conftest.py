import os

# Test settings take priority over backend/.env. Set before any app module reads configuration.
os.environ["APP_ENV"] = "test"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
# Unit and API tests never call real model providers or remote storage, whatever backend/.env says.
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["EMBEDDING_PROVIDER"] = "ollama"
os.environ["VECTOR_STORE"] = "chroma"
os.environ["STORAGE_BACKEND"] = "local"
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-validation")
# The fake bag-of-words embeddings produce lower similarities than a real embedding model.
os.environ["MIN_RELEVANCE_SCORE"] = "0.05"

import pytest

from app.rag.vector_store import ChromaVectorStore
from tests.fakes import BagOfWordsEmbeddings


@pytest.fixture
def vector_store(tmp_path) -> ChromaVectorStore:
    import chromadb
    from chromadb.config import Settings as ChromaClientSettings

    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"), settings=ChromaClientSettings(anonymized_telemetry=False))
    return ChromaVectorStore(client, "test_documents", BagOfWordsEmbeddings())
