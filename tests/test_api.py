from app import config, security
from app.database import connect

ADMIN = {"X-Admin-Token": "test-admin-token"}

VALID = {
    "name": "张三",
    "country": "CN",
    "affiliation_type": "university",
    "organization": "某某大学机器人实验室",
    "email": "zhangsan@example.edu",
}


def post(client, **overrides):
    return client.post("/api/v1/submissions", json={**VALID, **overrides})


def test_pages_render(client):
    index = client.get("/")
    assert index.status_code == 200 and "AnyStats Test" in index.text
    submit = client.get("/submit")
    assert submit.status_code == 200 and 'name="country"' in submit.text
    assert "中国" in submit.text and 'value="US"' in submit.text
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200 and "/static/plotly.min.js" in dashboard.text
    assert client.get("/healthz").json()["status"] == "ok"


def test_meta_hides_secrets(client):
    data = client.get("/api/v1/meta").json()["data"]
    assert data["title"] == "AnyStats Test"
    assert data["sync"]["enabled"] is False
    assert "admin_token" not in data
    assert "test-admin-token" not in str(data)


def test_submission_and_dedup(client):
    assert post(client).json()["code"] == 0
    # 同邮箱 + 单位大小写不同：记录 2 条，主体/单位去重后各 1
    post(client, name="张三三", email="ZHANGSAN@example.edu")
    post(client, name="李四", email="lisi@x.cn",
         organization="Acme Robotics", affiliation_type="company")
    post(client, name="王五", email="wangwu@x.cn",
         organization="acme robotics", affiliation_type="company")

    summary = client.get("/api/v1/stats/summary").json()["data"]
    assert summary["total"] == 4
    assert summary["subjects_unique"] == 3
    assert summary["organizations_unique"] == 2
    assert summary["by_country"] == [{"key": "CN", "count": 4}]
    assert summary["monthly_trend"]


def test_honeypot_and_rate_limit(client, monkeypatch):
    assert post(client, website="http://spam").status_code == 400

    monkeypatch.setattr(security.limiter, "limit", 1)
    assert post(client).status_code == 200
    assert post(client).status_code == 429


def test_admin_endpoints_and_export(client):
    post(client)
    assert client.get("/api/v1/submissions").status_code == 401
    listing = client.get("/api/v1/submissions", headers=ADMIN).json()["data"]
    assert listing["total"] == 1
    detail = client.get(f"/api/v1/submissions/{listing['items'][0]['id']}", headers=ADMIN)
    assert detail.json()["data"]["name"] == "张三"
    assert client.get("/api/v1/submissions/9999", headers=ADMIN).status_code == 404

    export = client.get("/api/v1/stats/export", headers=ADMIN)
    assert export.status_code == 200
    assert export.content.startswith(b"\xef\xbb\xbf")  # BOM
    assert "name,country" in export.text

    assert client.get("/api/v1/downloads/metrics").status_code == 401
    assert client.get("/api/v1/downloads/metrics", headers=ADMIN).status_code == 200


def test_dashboard_auth_switch(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "DASHBOARD_AUTH", True)
    assert client.get("/api/v1/dashboard").status_code == 401
    resp = client.get("/api/v1/dashboard", headers=ADMIN)
    assert resp.status_code == 200 and "overview" in resp.json()["data"]


def test_ip_tracking_endpoints_removed(client):
    assert client.get("/api/v1/access-ips").status_code == 404
    assert client.post("/api/v1/track/visit", json={"path": "/"}).status_code == 404


def test_github_router_disabled_short_circuits(client):
    # 未配置 github 源时不发网络请求，直接返回 enabled=false
    data = client.get("/api/v1/github").json()["data"]
    assert data["enabled"] is False


def test_downloads_metrics_raw(client):
    from app.crud import downloads

    conn = connect()
    downloads.insert_snapshot(conn, "huggingface", [("org/a", 1, 0, None)])
    metrics = client.get("/api/v1/downloads/metrics", headers=ADMIN).json()["data"]
    assert metrics["total"] == 1
    assert metrics["items"][0]["repo_id"] == "org/a"
