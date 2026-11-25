"""面板聚合：一次算好前端需要的全部数据。"""

from datetime import datetime, timezone
from sqlite3 import Connection

from ..config import SOURCE_LABELS, settings
from ..countries import COUNTRY_NAMES, ISO2_TO_ISO3
from . import downloads, github, papers
from .submissions import SUBJECT_VIEW


def _overview(conn: Connection) -> dict:
    row = conn.execute(
        f"""SELECT COUNT(*) AS submissions_total,
                   COUNT(DISTINCT subject_key) AS subjects_unique,
                   COUNT(DISTINCT org_key) AS organizations_unique,
                   COUNT(DISTINCT country) AS countries
            FROM ({SUBJECT_VIEW})"""
    ).fetchone()
    return {
        "submissions_total": row["submissions_total"],
        "subjects_unique": row["subjects_unique"],
        "organizations_unique": row["organizations_unique"],
        "countries": row["countries"],
        "downloads_latest": downloads.latest_by_source(conn),
    }


def _by_country(conn: Connection) -> list[dict]:
    rows = conn.execute(
        f"""SELECT country,
                   COUNT(DISTINCT subject_key) AS subjects,
                   COUNT(DISTINCT org_key) AS organizations
            FROM ({SUBJECT_VIEW})
            GROUP BY country ORDER BY subjects DESC, country"""
    ).fetchall()
    return [
        {**dict(row), "iso3": ISO2_TO_ISO3.get(row["country"])}
        for row in rows
    ]


def _registration_trend(conn: Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS count "
        "FROM submissions GROUP BY month ORDER BY month"
    ).fetchall()
    return [dict(row) for row in rows]


def _org_tree(conn: Connection) -> list[dict]:
    """两级结构：一级机构类型，二级该类型下的具体单位。"""
    rows = conn.execute(
        f"""SELECT affiliation_type, org_key, MAX(organization) AS organization,
                   COUNT(DISTINCT subject_key) AS subjects
            FROM ({SUBJECT_VIEW})
            GROUP BY affiliation_type, org_key"""
    ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["affiliation_type"], []).append(
            {"organization": row["organization"], "subjects": row["subjects"]}
        )
    tree = []
    for affiliation, orgs in grouped.items():
        orgs.sort(key=lambda item: -item["subjects"])
        tree.append(
            {
                "affiliation_type": affiliation,
                "total_subjects": sum(item["subjects"] for item in orgs),
                "organizations": orgs,
            }
        )
    tree.sort(key=lambda group: -group["total_subjects"])
    return tree


def _top_datasets(conn: Connection, sources: dict, limit: int = 20) -> list[dict]:
    """跨渠道按仓库短名合并，得到最受欢迎数据集 Top N。"""
    totals: dict[str, dict] = {}
    for (source, repo_id), snap in downloads.latest_per_repo(conn).items():
        short = repo_id.split("/", 1)[-1]
        entry = totals.setdefault(
            short.lower(),
            {"name": short, "total": 0, "platforms": {}, "repos": []},
        )
        entry["platforms"][source] = entry["platforms"].get(source, 0) + snap["downloads"]
        entry["total"] += snap["downloads"]
        entry["repos"].append(
            {
                "source": source,
                "repo_id": repo_id,
                "downloads": snap["downloads"],
                "url": downloads.repo_url(source, repo_id, sources.get(source)),
            }
        )
    ranked = sorted(totals.values(), key=lambda item: -item["total"])
    return ranked[:limit]


def _active_sources(conn: Connection) -> dict:
    """哪些数据源实际有内容，供面板决定展示哪些板块。"""
    counts = {
        row["source"]: row["n"]
        for row in conn.execute(
            "SELECT source, COUNT(DISTINCT repo_id) AS n FROM download_metrics GROUP BY source"
        )
    }
    paper_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    github_count = conn.execute("SELECT COUNT(*) FROM github_repo").fetchone()[0]
    has_data = {
        "huggingface": counts.get("huggingface", 0) > 0,
        "modelscope": counts.get("modelscope", 0) > 0,
        "paper": paper_count > 0,
        "github": github_count > 0,
    }
    return {
        name: {
            "label": SOURCE_LABELS.get(name, name),
            "active": settings.source_active(name),
            "has_data": has_data.get(name, False),
        }
        for name in settings.SOURCES
    }


def compute_dashboard(conn: Connection, *, trend_days: int = 30) -> dict:
    gh_cfg = settings.SOURCES.get("github") or {}
    gh = None
    if settings.source_active("github"):
        gh = github.stats(
            conn,
            gh_cfg.get("repo"),
            issue_limit=int(gh_cfg.get("issue_limit") or 50),
            include_prs=bool(gh_cfg.get("include_prs")),
        )
    paper_stats = papers.stats_summary(conn) if settings.source_active("paper") else None
    overview = _overview(conn)
    if paper_stats is not None:
        overview["paper"] = {
            "citing_papers": paper_stats["citing_papers"],
            "citing_citations": paper_stats["citing_citations"],
            "seed_citations": (paper_stats.get("seed") or {}).get("citation_count", 0),
        }
    if gh is not None:
        overview["github"] = {
            "repo": gh["repo"],
            "stars": gh["stars"],
            "forks": gh["forks"],
            "open_issues": gh["open_issues"],
        }
    return {
        "site": settings.public_info(),
        "overview": overview,
        "downloads": {
            "latest": downloads.latest_by_source(conn),
            "trend": {"days": trend_days, "series": downloads.trend_series(conn, days=trend_days)},
            "top_datasets": _top_datasets(conn, settings.SOURCES),
            "sources": downloads.list_sources(conn, settings.SOURCES),
        },
        "registration_trend": _registration_trend(conn),
        "by_country": _by_country(conn),
        "country_names": {code: COUNTRY_NAMES.get(code, code) for code in COUNTRY_NAMES},
        "org_tree": _org_tree(conn),
        "papers": paper_stats,
        "github": gh,
        "features": _active_sources(conn),
        "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
