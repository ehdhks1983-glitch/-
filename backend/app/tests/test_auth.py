def test_login_success_and_me(client, admin_headers):
    resp = client.get("/api/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@test.local"
    assert body["role"] == "admin"


def test_login_wrong_password(client, make_user):
    make_user("u@test.local", "rightpass123")
    resp = client.post(
        "/api/auth/login", json={"email": "u@test.local", "password": "wrongpass"}
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "invalid_credentials"


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "unauthorized"


def test_invalid_token_rejected(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "invalid_token"


def test_refresh_flow(client, make_user):
    make_user("r@test.local", "pass123456")
    tokens = client.post(
        "/api/auth/login", json={"email": "r@test.local", "password": "pass123456"}
    ).json()

    ok = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    # an access token must not be accepted by the refresh endpoint
    bad = client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert bad.status_code == 401
    assert bad.json()["error_code"] == "invalid_token"


def test_error_schema_shape(client):
    resp = client.get("/api/auth/me")
    body = resp.json()
    assert set(body.keys()) >= {"error_code", "message"}
