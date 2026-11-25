from app import config
from app.crud import downloads, github, papers
from app.database import connect

from .test_api import post


def _seed_downloads():
    conn = connect()
    downloads.insert_snapshot(
        conn, "huggingface",
        [("org/pick_apple", 100, 2, None), ("org/open_door", 50, 1, None)],
    )
    downloads.insert_snapshot(conn, "modelscope", [("org/pick_apple", 30, 0, None)])


def test_downloads_api_and_dashboard(client):
    _seed_downloads()
    stats = client.get("/api/v1/stats/downloads").json()["data"]
    assert {item["source"]: item["downloads"] for item in stats["latest"]} == {
        "huggingface": 150, "modelscope": 30,
    }
    series = stats["trend"]["series"]
    assert series["huggingface"][-1]["downloads"] == 150
    assert series["modelscope"][-1]["downloads"] == 30

    sources = client.get("/api/v1/download-sources").json()["data"]["items"]
    assert {item["repo_id"] for item in sources} == {"org/pick_apple", "org/open_door"}

    dash = client.get("/api/v1/dashboard").json()["data"]
    assert dash["overview"]["downloads_latest"] == stats["latest"]
    top = {item["name"]: item for item in dash["downloads"]["top_datasets"]}
    assert top["pick_apple"]["total"] == 130  # 跨平台合并
    assert top["pick_apple"]["platforms"] == {"huggingface": 100, "modelscope": 30}
    assert top["open_door"]["total"] == 50
    assert dash["features"]["huggingface"]["has_data"] is True


def test_map_country_and_org_tree(client):
    post(client)
    post(client, name="Alice", email="alice@x.cn", country="US",
         organization="MIT", affiliation_type="university")
    post(client, name="Bob", email="bob@x.cn", country="US",
         organization="Acme", affiliation_type="company")
    dash = client.get("/api/v1/dashboard").json()["data"]
    by_country = {row["country"]: row for row in dash["by_country"]}
    assert by_country["CN"]["subjects"] == 1
    assert by_country["US"]["subjects"] == 2
    assert by_country["US"]["iso3"] == "USA"
    tree = {group["affiliation_type"]: group for group in dash["org_tree"]}
    assert tree["company"]["total_subjects"] == 1
    monthly = dash["registration_trend"]
    assert monthly and monthly[-1]["count"] == 3


def test_papers_section(client, monkeypatch):
    monkeypatch.setitem(config.settings.SOURCES["paper"], "enabled", True)
    monkeypatch.setitem(config.settings.SOURCES["paper"], "arxiv_id", "2511.17441")
    conn = connect()
    papers.set_meta(conn, "seed_paper", {"title": "Seed Paper", "url": "https://arxiv.org/abs/2511.17441"})
    papers.upsert_paper(conn, {
        "s2_id": "p1", "title": "A Citing Paper", "authors": ["A", "B"],
        "year": 2025, "venue": "ICRA", "citation_count": 7, "arxiv_id": "2501.00001",
        "fields": {"topics": ["robotics"]},
    })
    papers.upsert_paper(conn, {
        "s2_id": "p2", "title": "Another Paper", "authors": ["C"],
        "year": 2025, "venue": "ICRA", "citation_count": 3,
    })
    papers.save_snapshot(conn, "2026-01-01", seed_citations=10,
                         citing_papers=2, citing_citations=10)

    stats = client.get("/api/v1/papers/stats").json()["data"]
    assert stats["citing_papers"] == 2
    assert stats["seed"]["citation_count"] == 10
    assert stats["top_venues"][0] == {"venue": "ICRA", "count": 2}
    listed = client.get("/api/v1/papers?q=Citing").json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["authors"] == ["A", "B"]

    dash = client.get("/api/v1/dashboard").json()["data"]
    assert dash["overview"]["paper"]["seed_citations"] == 10
    assert dash["papers"]["citing_papers"] == 2
    assert dash["features"]["paper"]["has_data"] is True


def test_paper_insights_section(client, monkeypatch):
    monkeypatch.setitem(config.settings.SOURCES["paper"], "enabled", True)
    monkeypatch.setitem(config.settings.SOURCES["paper"], "arxiv_id", "2511.17441")
    monkeypatch.setitem(
        config.settings.SOURCES["paper"], "insights",
        {"enabled": True, "llm_api_key": "test-key", "project_keyword": "MyProject"},
    )
    conn = connect()
    papers.upsert_paper(conn, {
        "s2_id": "p3", "title": "Using MyProject", "authors": ["X"],
        "year": 2026, "venue": "CoRL", "citation_count": 2, "arxiv_id": "2601.00001",
    })
    conn.execute(
        """INSERT INTO paper_insights
               (s2_id, arxiv_id, role, usage, keywords_json, comments_json,
                analyzed_at, model)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "p3", "2601.00001", "training_data", "用 MyProject 训练 VLA 策略",
            '["vla", "bimanual manipulation"]',
            '[{"text": "MyProject is diverse.", "sentiment": "positive"}]',
            "2026-01-01T00:00:00Z", "test",
        ),
    )
    conn.commit()

    data = client.get("/api/v1/papers/insights").json()["data"]
    assert data["analyzed"] == 1
    assert data["roles"] == [{"role": "training_data", "count": 1}]
    assert data["comments"][0]["sentiment"] == "positive"
    assert data["usages"][0]["usage"] == "用 MyProject 训练 VLA 策略"
    assert data["sentiments"] == {"positive": 1}

    dash = client.get("/api/v1/dashboard").json()["data"]
    assert dash["features"]["insights"]["has_data"] is True
    assert dash["overview"]["insights"]["analyzed"] == 1


def test_github_section(client, monkeypatch):
    monkeypatch.setitem(config.settings.SOURCES["github"], "enabled", True)
    monkeypatch.setitem(config.settings.SOURCES["github"], "repo", "o/r")
    conn = connect()
    github.upsert_repo(conn, "o/r", {
        "stars": 12, "forks": 3, "watchers": 2, "open_issues": 1,
        "description": "demo", "topics": ["robotics"], "html_url": "https://github.com/o/r",
    })
    github.save_snapshot(conn, "o/r", "2026-01-01")
    github.replace_issues(conn, "o/r", [{
        "number": 7, "title": "Bug", "state": "open", "user": {"login": "dev"},
        "labels": [{"name": "bug"}], "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z", "html_url": "https://github.com/o/r/issues/7",
        "comments": 0,
    }])

    dash = client.get("/api/v1/dashboard").json()["data"]
    assert dash["overview"]["github"]["stars"] == 12
    assert dash["github"]["issues"][0]["title"] == "Bug"
    assert dash["github"]["snapshots"][0]["stars"] == 12
    assert dash["features"]["github"]["has_data"] is True
