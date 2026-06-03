def test_summary_counts(client, admin_headers, product):
    client.post(
        "/api/licenses/issue",
        headers=admin_headers,
        json={"product_id": product["id"], "plan_type": "monthly_30"},
    )
    resp = client.get("/api/stats/summary", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_active"] >= 1
    assert data["issued_today"] >= 1
    assert any(p["product_code"] == "centum-writer" for p in data["by_product"])


def test_revenue_points(client, admin_headers, product):
    for _ in range(3):
        client.post(
            "/api/licenses/issue",
            headers=admin_headers,
            json={"product_id": product["id"], "plan_type": "trial_7"},
        )
    resp = client.get(
        "/api/stats/revenue", headers=admin_headers, params={"granularity": "day"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["granularity"] == "day"
    assert sum(p["count"] for p in data["points"]) == 3


def test_stats_requires_auth(client):
    assert client.get("/api/stats/summary").status_code == 401
