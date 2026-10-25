"""Application error types.

Each error carries a stable machine-readable code, an HTTP status and a message that is safe to
show to clients. Internal details (stack traces, provider responses) go to the logs only.
"""


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    default_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        self.message = message or self.default_message
        self.details = details  # optional machine-readable context, e.g. an existing document id
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    default_message = "The request is invalid."


class AuthenticationError(AppError):
    status_code = 401
    code = "not_authenticated"
    default_message = "Authentication is required."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"
    default_message = "You are not allowed to perform this action."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The resource already exists."


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    default_message = "The uploaded file is too large."


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file"
    default_message = "Only PDF and TXT files are supported."


class DocumentProcessingError(AppError):
    status_code = 422
    code = "document_unprocessable"
    default_message = "The document could not be processed."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests. Please wait and try again."


class ModelProviderError(AppError):
    status_code = 503
    code = "model_unavailable"
    default_message = "The language model is currently unavailable. Please try again later."


class ModelRateLimitedError(AppError):
    status_code = 429
    code = "model_rate_limited"
    default_message = "The AI provider's rate limit was reached. Please wait a minute and try again."


class ModelTimeoutError(AppError):
    status_code = 504
    code = "model_timeout"
    default_message = "The language model took too long to respond. Please try again."


class EmbeddingError(AppError):
    status_code = 503
    code = "embedding_unavailable"
    default_message = "The embedding model is currently unavailable. Please try again later."


class StorageError(AppError):
    status_code = 503
    code = "storage_unavailable"
    default_message = "File storage is currently unavailable. Please try again later."


class VectorStoreError(AppError):
    status_code = 503
    code = "vector_store_unavailable"
    default_message = "The document index is currently unavailable. Please try again later."
