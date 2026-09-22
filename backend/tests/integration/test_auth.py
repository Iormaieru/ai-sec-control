from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.auth.service import create_user
from app.main import app

client = TestClient(app)


def _make_user(db: Session, *, username: str, password: str, role: UserRole = UserRole.USER) -> None:
    create_user(db, username=username, password=password, role=role)


def _login(username: str, password: str) -> str:
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_login_success_returns_jwt(db: Session) -> None:
    _make_user(db, username="alice", password="s3cret-pass")

    response = client.post("/auth/login", data={"username": "alice", "password": "s3cret-pass"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(db: Session) -> None:
    _make_user(db, username="bob", password="correct-pass")

    response = client.post("/auth/login", data={"username": "bob", "password": "wrong-pass"})

    assert response.status_code == 401


def test_login_unknown_user_rejected() -> None:
    response = client.post("/auth/login", data={"username": "ghost", "password": "whatever"})

    assert response.status_code == 401


def test_me_requires_valid_token(db: Session) -> None:
    _make_user(db, username="carol", password="carol-pass")
    token = _login("carol", "carol-pass")

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["username"] == "carol"


def test_me_rejects_missing_token() -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_register_rejects_non_admin(db: Session) -> None:
    _make_user(db, username="dave", password="dave-pass", role=UserRole.USER)
    token = _login("dave", "dave-pass")

    response = client.post(
        "/auth/register",
        json={"username": "new-user", "password": "whatever-pass"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_register_allows_admin_to_create_user(db: Session) -> None:
    _make_user(db, username="root-admin", password="admin-pass", role=UserRole.ADMIN)
    token = _login("root-admin", "admin-pass")

    response = client.post(
        "/auth/register",
        json={"username": "fresh-user", "password": "fresh-pass", "role": "user"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == "fresh-user"
    assert body["role"] == "user"

    login_response = client.post("/auth/login", data={"username": "fresh-user", "password": "fresh-pass"})
    assert login_response.status_code == 200


def test_register_rejects_duplicate_username(db: Session) -> None:
    _make_user(db, username="dup-admin", password="admin-pass", role=UserRole.ADMIN)
    token = _login("dup-admin", "admin-pass")

    response = client.post(
        "/auth/register",
        json={"username": "dup-admin", "password": "whatever-pass"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
