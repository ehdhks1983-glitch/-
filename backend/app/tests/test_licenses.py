def _issue(client, headers, product, plan="monthly_30", **extra):
    body = {"product_id": product["id"], "plan_type": plan}
    body.update(extra)
    return client.post("/api/licenses/issue", headers=headers, json=body)


def test_issue_and_list_and_search(client, admin_headers, product):
    resp = _issue(client, admin_headers, product, customer_name="홍길동", memo="VIP")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["raw_key"].startswith("CW-M30-")
    assert body["expires_at"] is not None

    listing = client.get("/api/licenses", headers=admin_headers).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["hwid_max"] == 1 and item["hwid_used"] == 0
    assert item["product_code"] == "centum-writer"

    found = client.get(
        "/api/licenses", headers=admin_headers, params={"search": "홍길동"}
    ).json()
    assert found["total"] == 1
    none = client.get(
        "/api/licenses", headers=admin_headers, params={"search": "nobody"}
    ).json()
    assert none["total"] == 0


def test_unlimited_has_no_expiry_and_cannot_extend(client, admin_headers, product):
    body = _issue(client, admin_headers, product, plan="unlimited").json()
    assert body["expires_at"] is None
    ext = client.post(
        f"/api/licenses/{body['license_id']}/extend",
        headers=admin_headers,
        json={"days": 30},
    )
    assert ext.status_code == 400
    assert ext.json()["error_code"] == "cannot_extend_unlimited"


def test_custom_plan_requires_duration(client, admin_headers, product):
    resp = _issue(client, admin_headers, product, plan="custom")
    assert resp.status_code == 422
    ok = _issue(client, admin_headers, product, plan="custom", duration_days=45)
    assert ok.status_code == 201
    assert ok.json()["raw_key"].startswith("CW-C45-")


def test_revoke_and_extend(client, admin_headers, product):
    body = _issue(client, admin_headers, product, plan="trial_7").json()
    lid = body["license_id"]

    extended = client.post(
        f"/api/licenses/{lid}/extend", headers=admin_headers, json={"days": 7}
    )
    assert extended.status_code == 200

    revoked = client.post(f"/api/licenses/{lid}/revoke", headers=admin_headers)
    assert revoked.json()["status"] == "revoked"

    # cannot extend a revoked license
    again = client.post(
        f"/api/licenses/{lid}/extend", headers=admin_headers, json={"days": 7}
    )
    assert again.status_code == 400


def test_bulk_issue_json_and_csv(client, admin_headers, product):
    as_json = client.post(
        "/api/licenses/issue-bulk",
        headers=admin_headers,
        json={"product_id": product["id"], "plan_type": "trial_7", "count": 5},
    )
    assert as_json.status_code == 200
    payload = as_json.json()
    assert payload["count"] == 5
    assert len({k["raw_key"] for k in payload["keys"]}) == 5

    as_csv = client.post(
        "/api/licenses/issue-bulk?format=csv",
        headers=admin_headers,
        json={"product_id": product["id"], "plan_type": "trial_7", "count": 3},
    )
    assert as_csv.status_code == 200
    assert "text/csv" in as_csv.headers["content-type"]
    assert as_csv.text.count("CW-T07-") == 3


def test_staff_can_issue(client, staff_headers, product):
    resp = _issue(client, staff_headers, product, plan="trial_7")
    assert resp.status_code == 201


def test_memo_update(client, admin_headers, product):
    lid = _issue(client, admin_headers, product).json()["license_id"]
    updated = client.patch(
        f"/api/licenses/{lid}", headers=admin_headers, json={"memo": "갱신 메모"}
    )
    assert updated.json()["memo"] == "갱신 메모"
