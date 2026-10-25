"""Password hashing and session tokens.

Session design: a short-lived JWT is stored in an HttpOnly cookie, so page JavaScript (and any
injected script) cannot read it. Because browsers attach cookies automatically, state-changing
requests also need a CSRF token: it is embedded in the JWT and handed to the frontend in a
separate readable cookie; the frontend echoes it in the X-CSRF-Token header. A malicious site
can make the browser send the cookies but cannot read them to forge the header.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import AuthenticationError

ACCESS_COOKIE = "access_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
_ALGORITHM = "HS256"

_password_hash = PasswordHash.recommended()  # Argon2id
# Verified against when an email is unknown, so login takes the same time either way.
_DUMMY_HASH = _password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


@dataclass(frozen=True)
class SessionToken:
    token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    csrf_token: str


def create_session_token(user_id: uuid.UUID, settings: Settings) -> SessionToken:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    csrf_token = secrets.token_urlsafe(32)
    payload = {"sub": str(user_id), "iat": now, "exp": expires_at, "csrf": csrf_token, "type": "access"}
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)
    return SessionToken(token=token, csrf_token=csrf_token, expires_at=expires_at)


def decode_session_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[_ALGORITHM],  # never accept the algorithm named by the token itself
            options={"require": ["sub", "exp", "iat", "csrf"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Your session has expired. Please log in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError() from exc
    if payload.get("type") != "access":
        raise AuthenticationError()
    try:
        return TokenClaims(user_id=uuid.UUID(payload["sub"]), csrf_token=payload["csrf"])
    except (ValueError, TypeError) as exc:
        raise AuthenticationError() from exc
