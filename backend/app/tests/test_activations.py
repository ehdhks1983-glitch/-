import time

from app.core.hmac_verify import build_signature


def _activate(client, product, key, hwid):
    ts = int(time.time())
    sig = build_signature(product["secret_key"], [key, hwid, str(ts)])
    return client.post(
        "/api/verify/activate",
        json={
            "license_key": key,
            "hwid": hwid,
            "product_code": product["code"],
            "timestamp": ts,
            "signature": sig,
        },
    )


def _issue(client, headers, product, plan="unlimited"):
    return client.post(
        "/api/licenses/issue",
        headers=headers,
        json={"product_id": product["id"], "plan_type": plan},
    ).json()


def test_list_activations_and_conflict_detection(client, admin_headers, product):
    # raise the product's HWID cap so we can bind two licenses to one HWID
    client.patch(
        f"/api/products/{product['id']}", headers=admin_headers, json={"max_hwid_count": 5}
    )
    product["max_hwid_count"] = 5

    key1 = _issue(client, admin_headers, product)["raw_key"]
    key2 = _issue(client, admin_headers, product)["raw_key"]

    # same HWID on two different licenses -> conflict
    assert _activate(client, product, key1, "SHARED-HWID").json()["valid"] is True
    assert _activate(client, product, key2, "SHARED-HWID").json()["valid"] is True
    # a distinct, non-conflicting activation
    assert _activate(client, product, key1, "SOLO-HWID").json()["valid"] is True

    listing = client.get("/api/activations", headers=admin_headers).json()
    assert listing["total"] == 3
    shared = [a for a in listing["items"] if a["hwid"] == "SHARED-HWID"]
    solo = [a for a in listing["items"] if a["hwid"] == "SOLO-HWID"]
    assert len(shared) == 2 and all(a["is_conflict"] for a in shared)
    assert len(solo) == 1 and solo[0]["is_conflict"] is False

    only_conflicts = client.get(
        "/api/activations", headers=admin_headers, params={"conflicts_only": True}
    ).json()
    assert only_conflicts["total"] == 2
    assert all(a["is_conflict"] for a in only_conflicts["items"])


def test_activations_requires_auth(client):
    assert client.get("/api/activations").status_code == 401
