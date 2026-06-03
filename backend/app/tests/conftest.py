import os

# Configure the environment before app modules (and their cached settings) load.
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables)
from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(session_factory):
    def _make(email: str, password: str, role: UserRole = UserRole.staff) -> int:
        db = session_factory()
        user = User(
            email=email.lower(),
            hashed_password=hash_password(password),
            name=email,
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        uid = user.id
        db.close()
        return uid

    return _make


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client, make_user):
    make_user("admin@test.local", "adminpass123", UserRole.admin)
    return _login(client, "admin@test.local", "adminpass123")


@pytest.fixture()
def staff_headers(client, make_user):
    make_user("staff@test.local", "staffpass123", UserRole.staff)
    return _login(client, "staff@test.local", "staffpass123")


@pytest.fixture()
def product(client, admin_headers):
    """Creates a product (max_hwid_count=1) and returns its body incl. secret_key."""
    resp = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "code": "centum-writer",
            "name": "센텀라이터",
            "prefix": "CW",
            "max_hwid_count": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
