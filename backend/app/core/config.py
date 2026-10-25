"""Application settings, loaded from environment variables (and backend/.env in development).

Every other module reads configuration through get_settings(); nothing else touches os.environ.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent

Provider = Literal["ollama", "openai_compatible"]

# Size of the pgvector column (see the document_chunks migration). nomic-embed-text produces
# 768 dimensions natively; hosted models are asked for 768 via EMBEDDING_DIMENSIONS.
PGVECTOR_DIMENSIONS = 768


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env.local (project root) is written by `neon env pull` / `neon checkout` with the
        # branch's DATABASE_URL values. backend/.env is listed last, so its values win.
        # Real environment variables (used in production) override both files.
        env_file=(PROJECT_DIR / ".env.local", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # App
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:5173"

    # Database: the pooled URL serves application traffic; migrations need a direct connection
    # because PgBouncer's transaction mode does not keep session state between statements.
    database_url: str
    database_url_unpooled: str | None = None

    # Auth
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=60, gt=0)

    # Chat model
    llm_provider: Provider = "ollama"
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_num_ctx: int = Field(default=4096, gt=0)
    hosted_llm_base_url: str | None = None
    hosted_llm_api_key: SecretStr | None = None
    hosted_llm_model: str | None = None

    # Embedding model
    embedding_provider: Provider = "ollama"
    embedding_model: str = "nomic-embed-text"
    hosted_embedding_base_url: str | None = None
    hosted_embedding_api_key: SecretStr | None = None
    # Ask a hosted model for shorter vectors (e.g. Gemini supports 768); None keeps its default.
    embedding_dimensions: int | None = Field(default=None, gt=0)

    # Vector store: chroma (local folder or Chroma Cloud) or pgvector (inside PostgreSQL)
    vector_store: Literal["chroma", "pgvector"] = "chroma"
    chroma_mode: Literal["local", "cloud"] = "local"
    chroma_persist_dir: Path = BACKEND_DIR / "data" / "chroma"
    chroma_collection: str = "documents"
    chroma_api_key: SecretStr | None = None
    chroma_tenant: str | None = None
    chroma_database: str | None = None

    # File storage
    # The AWS_* names are what Neon Object Storage injects (`neon env pull`); S3_* also work.
    storage_backend: Literal["local", "s3"] = "local"
    local_upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    s3_endpoint_url: str | None = Field(default=None, validation_alias=AliasChoices("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3"))
    s3_bucket: str | None = None
    s3_access_key_id: str | None = Field(default=None, validation_alias=AliasChoices("S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"))
    s3_secret_access_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
    )
    s3_region: str = Field(default="auto", validation_alias=AliasChoices("S3_REGION", "AWS_REGION"))

    # RAG tuning
    max_upload_mb: int = Field(default=10, gt=0)
    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)
    retrieval_top_k: int = Field(default=4, gt=0, le=20)
    min_relevance_score: float = Field(default=0.55, ge=-1, le=1)
    relevance_margin: float = Field(default=0.12, ge=0, le=2)
    history_window_messages: int = Field(default=6, ge=0)

    # Abuse control (requests per minute, per client IP for auth and per user otherwise)
    auth_rate_limit_per_minute: int = Field(default=10, gt=0)
    upload_rate_limit_per_minute: int = Field(default=10, gt=0)
    chat_rate_limit_per_minute: int = Field(default=10, gt=0)

    @field_validator("database_url", "database_url_unpooled")
    @classmethod
    def _use_psycopg_driver(cls, value: str | None) -> str | None:
        # Hosting providers hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver.
        if value is None:
            return None
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("chroma_persist_dir", "local_upload_dir")
    @classmethod
    def _resolve_against_backend_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if self.llm_provider == "openai_compatible":
            self._require(
                "LLM_PROVIDER=openai_compatible",
                "hosted_llm_base_url",
                "hosted_llm_api_key",
                "hosted_llm_model",
            )
        if self.embedding_provider == "openai_compatible":
            self._require(
                "EMBEDDING_PROVIDER=openai_compatible",
                "hosted_embedding_base_url",
                "hosted_embedding_api_key",
            )
        if self.vector_store == "chroma" and self.chroma_mode == "cloud":
            self._require("CHROMA_MODE=cloud", "chroma_api_key", "chroma_tenant", "chroma_database")
        if (
            self.vector_store == "pgvector"
            and self.embedding_provider == "openai_compatible"
            and self.embedding_dimensions != PGVECTOR_DIMENSIONS
        ):
            raise ValueError(f"VECTOR_STORE=pgvector stores {PGVECTOR_DIMENSIONS}-dimensional vectors: set EMBEDDING_DIMENSIONS={PGVECTOR_DIMENSIONS}")
        if self.storage_backend == "s3":
            self._require(
                "STORAGE_BACKEND=s3",
                "s3_endpoint_url",
                "s3_bucket",
                "s3_access_key_id",
                "s3_secret_access_key",
            )
        return self

    def _require(self, reason: str, *fields: str) -> None:
        missing = [name.upper() for name in fields if getattr(self, name) is None]
        if missing:
            raise ValueError(f"{reason} requires {', '.join(missing)}")

    @property
    def cookie_secure(self) -> bool:
        # Secure cookies are only sent over HTTPS; local development runs on plain HTTP.
        return self.app_env == "production"

    @property
    def migration_database_url(self) -> str:
        return self.database_url_unpooled or self.database_url

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
