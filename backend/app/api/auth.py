from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import CurrentUser, SessionDep, SettingsDep, client_ip, get_token_claims
from app.core.config import Settings
from app.core.rate_limit import rate_limiter
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, TokenClaims, create_session_token
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(response: Response, user: User, settings: Settings) -> AuthResponse:
    session = create_session_token(user.id, settings)
    max_age = settings.access_token_expire_minutes * 60
    common = {"max_age": max_age, "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(ACCESS_COOKIE, session.token, httponly=True, path="/api", **common)
    # Readable by the frontend on purpose: it must copy this value into the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE, session.csrf_token, httponly=False, path="/", **common)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.post("/register", status_code=201, response_model=AuthResponse)
def register(body: RegisterRequest, request: Request, response: Response, db: SessionDep, settings: SettingsDep):
    rate_limiter.check(f"auth:{client_ip(request)}", settings.auth_rate_limit_per_minute)
    user = auth_service.register(db, email=body.email, password=body.password)
    return _start_session(response, user, settings)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: SessionDep, settings: SettingsDep):
    rate_limiter.check(f"auth:{client_ip(request)}", settings.auth_rate_limit_per_minute)
    user = auth_service.authenticate(db, email=body.email, password=body.password)
    return _start_session(response, user, settings)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    """Clears the session cookies. The JWT itself stays valid until it expires (stateless tokens)."""
    response.delete_cookie(ACCESS_COOKIE, path="/api")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me", response_model=AuthResponse)
def me(user: CurrentUser, claims: Annotated[TokenClaims, Depends(get_token_claims)]):
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=claims.csrf_token)
