import time

from app.core.hmac_verify import build_signature


def _sig(secret, key, hwid, ts):
    return build_signature(secret, [key, hwid, str(ts)])


def _issue(client, headers, product, plan="monthly_30", **extra):
    body = {"product_id": product["id"], "plan_type": plan}
    body.update(extra)
    return client.post("/api/licenses/issue", headers=headers, json=body).json()


def _activate(client, product, key, hwid, ts=None, signature=None, client_version="1.0"):
    ts = ts if ts is not None else int(time.time())
    signature = signature if signature is not None else _sig(
        product["secret_key"], key, hwid, ts
    )
    return client.post(
        "/api/verify/activate",
        json={
            "license_key": key,
            "hwid": hwid,
            "product_code": product["code"],
            "client_version": client_version,
            "timestamp": ts,
            "signature": signature,
        },
    )


def _check(client, product, key, hwid, ts=None, signature=None):
    ts = ts if ts is not None else int(time.time())
    signature = signature if signature is not None else _sig(
        product["secret_key"], key, hwid, ts
    )
    return client.post(
        "/api/verify/check",
        json={
            "license_key": key,
            "hwid": hwid,
            "product_code": product["code"],
            "timestamp": ts,
            "signature": signature,
        },
    )


def test_activate_then_check_flow(client, admin_headers, product):
    key = _issue(client, admin_headers, product)["raw_key"]

    act = _activate(client, product, key, "HWID-AAA")
    assert act.status_code == 200, act.text
    data = act.json()
    assert data["valid"] is True
    assert data["plan_type"] == "monthly_30"
    assert data["max_hwid_count"] == 1
    assert data["days_remaining"] >= 29

    chk = _check(client, product, key, "HWID-AAA")
    assert chk.json()["valid"] is True
    assert chk.json()["status"] == "active"
    assert chk.json()["days_remaining"] >= 29


def test_invalid_signature_rejected(client, admin_headers, product):
    key = _issue(client, admin_headers, product)["raw_key"]
    resp = _activate(client, product, key, "H1", signature="deadbeef")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "invalid_signature"


def test_stale_timestamp_rejected(client, admin_headers, product):
    key = _issue(client, admin_headers, product)["raw_key"]
    old_ts = int(time.time()) - 10_000
    resp = _activate(client, product, key, "H1", ts=old_ts)
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "stale_timestamp"


def test_unknown_product_rejected(client, admin_headers, product):
    key = _issue(client, admin_headers, product)["raw_key"]
    ts = int(time.time())
    resp = client.post(
        "/api/verify/activate",
        json={
            "license_key": key,
            "hwid": "H1",
            "product_code": "does-not-exist",
            "timestamp": ts,
            "signature": _sig(product["secret_key"], key, "H1", ts),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "product_not_found"


def test_hwid_limit_enforced(client, admin_headers, product):
    key = _issue(client, admin_headers, product)["raw_key"]

    assert _activate(client, product, key, "HW-1").json()["valid"] is True
    # re-activating the same HWID is allowed
    assert _activate(client, product, key, "HW-1").json()["valid"] is True
    # a second, distinct HWID exceeds max_hwid_count=1
    second = _activate(client, product, key, "HW-2").json()
    assert second["valid"] is False
    assert "초과" in second["reason"]


def test_revoked_key_fails_verification(client, admin_headers, product):
    issued = _issue(client, admin_headers, product)
    client.post(f"/api/licenses/{issued['license_id']}/revoke", headers=admin_headers)
    resp = _activate(client, product, issued["raw_key"], "HZ")
    assert resp.json()["valid"] is False
    assert "revoked" in resp.json()["reason"]


def test_check_unregistered_hwid_is_invalid(client, admin_headers, product):
    key = _issue(client, admin_headers, product)["raw_key"]
    resp = _check(client, product, key, "NEVER-SEEN")
    assert resp.json()["valid"] is False


def test_hwid_release_frees_a_slot(client, admin_headers, product):
    issued = _issue(client, admin_headers, product)
    lid, key = issued["license_id"], issued["raw_key"]

    assert _activate(client, product, key, "OLD-HWID").json()["valid"] is True

    detail = client.get(f"/api/licenses/{lid}", headers=admin_headers).json()
    assert len(detail["activations"]) == 1
    activation_id = detail["activations"][0]["id"]

    released = client.delete(
        f"/api/licenses/{lid}/activations/{activation_id}", headers=admin_headers
    )
    assert released.status_code == 200

    # the freed slot lets a new HWID activate
    assert _activate(client, product, key, "NEW-HWID").json()["valid"] is True
