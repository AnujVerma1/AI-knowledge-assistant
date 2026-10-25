import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def create(db: Session, *, email: str, password_hash: str) -> User:
    user = User(email=email.lower(), password_hash=password_hash)
    db.add(user)
    db.flush()
    return user
