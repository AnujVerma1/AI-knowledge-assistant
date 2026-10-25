from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, ConflictError
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import users as users_repo

_EMAIL_TAKEN = "An account with this email already exists."


def register(db: Session, *, email: str, password: str) -> User:
    if users_repo.get_by_email(db, email) is not None:
        raise ConflictError(_EMAIL_TAKEN)
    try:
        user = users_repo.create(db, email=email, password_hash=hash_password(password))
        db.commit()
    except IntegrityError as exc:  # two registrations for the same email at the same moment
        db.rollback()
        raise ConflictError(_EMAIL_TAKEN) from exc
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = users_repo.get_by_email(db, email)
    # Same message for unknown email and wrong password, so attackers cannot probe for accounts.
    if not verify_password(password, user.password_hash if user else None):
        raise AuthenticationError("Incorrect email or password.")
    return user
