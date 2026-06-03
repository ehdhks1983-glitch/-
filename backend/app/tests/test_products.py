def test_admin_full_crud(client, admin_headers):
    created = client.post(
        "/api/products",
        headers=admin_headers,
        json={"code": "Centum-Talk", "name": "센텀토크", "prefix": "ct"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["prefix"] == "CT"  # normalised to upper
    assert body["code"] == "centum-talk"  # normalised to lower
    assert len(body["secret_key"]) > 10
    pid = body["id"]

    # duplicate code -> 409
    dup = client.post(
        "/api/products",
        headers=admin_headers,
        json={"code": "centum-talk", "name": "x", "prefix": "CX"},
    )
    assert dup.status_code == 409 and dup.json()["error_code"] == "code_exists"

    # duplicate prefix -> 409
    dup2 = client.post(
        "/api/products",
        headers=admin_headers,
        json={"code": "other", "name": "x", "prefix": "CT"},
    )
    assert dup2.status_code == 409 and dup2.json()["error_code"] == "prefix_exists"

    # patch
    patched = client.patch(
        f"/api/products/{pid}", headers=admin_headers, json={"name": "센텀토크2"}
    )
    assert patched.json()["name"] == "센텀토크2"

    # rotate secret
    old_secret = body["secret_key"]
    rotated = client.post(f"/api/products/{pid}/rotate-secret", headers=admin_headers)
    assert rotated.json()["secret_key"] != old_secret

    # soft delete removes it from the default listing
    assert client.delete(f"/api/products/{pid}", headers=admin_headers).status_code == 200
    listing = client.get("/api/products", headers=admin_headers).json()
    assert all(p["id"] != pid for p in listing)
    # but is visible with include_inactive
    full = client.get(
        "/api/products", headers=admin_headers, params={"include_inactive": True}
    ).json()
    assert any(p["id"] == pid for p in full)


def test_list_omits_secret(client, admin_headers, product):
    listing = client.get("/api/products", headers=admin_headers).json()
    assert listing and "secret_key" not in listing[0]


def test_staff_cannot_manage_products(client, staff_headers):
    resp = client.post(
        "/api/products",
        headers=staff_headers,
        json={"code": "x", "name": "y", "prefix": "XY"},
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "forbidden"
