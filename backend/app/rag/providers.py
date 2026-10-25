"""The only module that knows which model provider is in use.

Everything else asks for a chat model or an embeddings object and works with LangChain's
common interfaces. There is deliberately no automatic fallback between providers: a failure
is reported instead of silently switching to a (possibly paid) alternative.
"""

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.core.config import Settings
from app.core.errors import AppError, EmbeddingError, ModelProviderError, ModelRateLimitedError, ModelTimeoutError

# nomic-embed-text is trained with task prefixes and retrieves noticeably better when they are used.
_TASK_PREFIXES = {"nomic-embed-text": ("search_document: ", "search_query: ")}

# Hosted embedding APIs cap how many texts one request may contain.
_HOSTED_EMBEDDING_BATCH = 100


def classify_provider_error(exc: BaseException, default: type[AppError] = ModelProviderError) -> AppError:
    """Map any provider SDK exception to a safe application error (checks the whole cause chain)."""
    current: BaseException | None = exc
    while current is not None:
        if getattr(current, "status_code", None) == 429 or "ratelimit" in type(current).__name__.lower():
            return ModelRateLimitedError()
        if isinstance(current, TimeoutError) or "timeout" in type(current).__name__.lower():
            return ModelTimeoutError()
        current = current.__cause__ or current.__context__
    return default()


def get_chat_model(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            num_ctx=settings.ollama_num_ctx,
            client_kwargs={"timeout": settings.llm_timeout_seconds},
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.hosted_llm_model,
        base_url=settings.hosted_llm_base_url,
        api_key=settings.hosted_llm_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )


def get_embeddings(settings: Settings) -> Embeddings:
    if settings.embedding_provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        inner: Embeddings = OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.llm_timeout_seconds},
        )
    else:
        from langchain_openai import OpenAIEmbeddings

        inner = OpenAIEmbeddings(
            model=settings.embedding_model,
            base_url=settings.hosted_embedding_base_url,
            api_key=settings.hosted_embedding_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
            # Non-OpenAI endpoints do not understand OpenAI's pre-tokenized input.
            check_embedding_ctx_length=False,
            chunk_size=_HOSTED_EMBEDDING_BATCH,
            dimensions=settings.embedding_dimensions,
        )
    document_prefix, query_prefix = _TASK_PREFIXES.get(settings.embedding_model.split(":")[0], ("", ""))
    return GuardedEmbeddings(inner, document_prefix=document_prefix, query_prefix=query_prefix)


class GuardedEmbeddings(Embeddings):
    """Adds model-specific task prefixes and turns any provider failure into EmbeddingError."""

    def __init__(self, inner: Embeddings, *, document_prefix: str = "", query_prefix: str = "") -> None:
        self._inner = inner
        self._document_prefix = document_prefix
        self._query_prefix = query_prefix

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return self._inner.embed_documents([self._document_prefix + t for t in texts])
        except Exception as exc:
            raise classify_provider_error(exc, default=EmbeddingError) from exc

    def embed_query(self, text: str) -> list[float]:
        try:
            return self._inner.embed_query(self._query_prefix + text)
        except Exception as exc:
            raise classify_provider_error(exc, default=EmbeddingError) from exc
