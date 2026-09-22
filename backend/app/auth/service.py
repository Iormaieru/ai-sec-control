from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.core.security import hash_password, verify_password


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session, *, username: str, password: str, full_name: str | None = None, role: UserRole = UserRole.USER
) -> User:
    user = User(
        username=username,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.commit()
    return user
