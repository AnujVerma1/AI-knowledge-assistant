"""Test doubles that replace real model providers, so tests run offline and deterministically."""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

DIMENSIONS = 256


class BagOfWordsEmbeddings(Embeddings):
    """Hashes words into a fixed-size vector. Texts sharing words get a high cosine similarity."""

    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class FailingEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise ConnectionError("embedding server unreachable")

    def embed_query(self, text: str) -> list[float]:
        raise ConnectionError("embedding server unreachable")


class RaisingChatModel:
    """Stands in for a chat model whose provider fails."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        raise self.exc


class RecordingChatModel:
    """Returns a fixed reply and records the messages it was given."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list = []

    def invoke(self, messages):
        from langchain_core.messages import AIMessage

        self.calls.append(messages)
        return AIMessage(self.reply)
