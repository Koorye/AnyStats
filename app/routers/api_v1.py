"""统一风格的 /api/v1 资源接口。

URL 约定：
  /api/v1/<resource>             资源列表（分页）
  /api/v1/<resource>/<id>        单个资源
  /api/v1/<resource>/<子资源>     资源下的统计/趋势/明细

所有成功响应统一为 {"code": 0, "message": "ok", "data": ...}；
分页数据统一为 data = {items, total, page, page_size}；
错误响应统一为 {"code": <HTTP 状态码>, "message": "...", "data": ...}。
"""

import csv
import io
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import crud
from ..collectors.github import ensure_issues_cached
from ..config import SOURCE_LABELS, settings
from ..countries import COUNTRY_NAMES
from ..database import get_db
from ..response import ok
from ..scheduler import trigger_async
from ..security import require_admin

router = APIRouter(prefix="/api/v1")

DOWNLOAD_SOURCES = ("huggingface", "modelscope")


def _github_overview(conn: Connection, *, refresh_issues: bool = False) -> dict | None:
    cfg = settings.SOURCES.get("github") or {}
    if not settings.source_active("github"):
        return None
    if refresh_issues:
        ensure_issues_cached(conn, cfg)
    repo = crud.github.get_repo(conn, cfg.get("repo"))
    if not repo:
        return None
    return {
        **repo,
        "issue_count": crud.github.issue_count(
            conn, cfg.get("repo"), include_prs=bool(cfg.get("include_prs"))
        ),
    }


def _download_sources(conn: Connection) -> list[dict]:
    stats = {item["source"]: item for item in crud.downloads.source_summary(conn)}
    items = []
    for name in DOWNLOAD_SOURCES:
        cfg = settings.SOURCES.get(name) or {}
        stat = stats.get(name) or {"repos": 0, "downloads": 0, "latest_fetched_at": None}
        items.append(
            {
                "source": name,
                "label": SOURCE_LABELS.get(name, name),
                "enabled": bool(cfg.get("enabled")),
                "active": settings.source_active(name),
                "org": cfg.get("org") or "",
                "repos": stat["repos"],
                "configured_repos": len(cfg.get("repos") or []),
                "downloads": stat["downloads"],
                "latest_fetched_at": stat["latest_fetched_at"],
            }
        )
    return items


# ---------------------------------------------------------------- 统计总览

@router.get("/stats", tags=["stats"])
def stats_overview(conn: Connection = Depends(get_db)):
    """全站统计总览：登记、下载、论文、洞察、GitHub。"""
    return ok(
        {
            "submissions": crud.submissions.stats_summary(conn),
            "downloads": crud.downloads.summary(conn),
            "papers": crud.papers.stats_summary(conn) if settings.source_active("paper") else None,
            "insights": crud.papers.insights_summary(conn) if settings.insights_active() else None,
            "github": _github_overview(conn),
            "sources": settings.public_info()["sources"],
            "sync": settings.sync_summary(),
        }
    )


@router.get("/stats/submissions", tags=["stats"])
def stats_submissions(conn: Connection = Depends(get_db)):
    """登记统计：主体/单位去重、国家、机构类型、版本、月度趋势。"""
    return ok(crud.submissions.stats_summary(conn))


@router.get("/stats/downloads", tags=["stats"])
def stats_downloads(
    days: int = Query(default=30, ge=1, le=365),
    conn: Connection = Depends(get_db),
):
    """下载统计：总览 + 各渠道最新值 + 每日趋势。"""
    return ok(
        {
            "summary": crud.downloads.summary(conn),
            "latest": crud.downloads.latest_by_source(conn),
            "trend": {"days": days, "series": crud.downloads.trend_series(conn, days=days)},
        }
    )


@router.get("/stats/papers", tags=["stats"])
def stats_papers(conn: Connection = Depends(get_db)):
    """论文统计：引用数、年份、期刊、Top 被引、快照 + 全文洞察汇总。"""
    data = crud.papers.stats_summary(conn)
    data["insights"] = crud.papers.insights_summary(conn)
    return ok(data)


@router.get("/stats/github", tags=["stats"])
def stats_github(conn: Connection = Depends(get_db)):
    """GitHub 统计：仓库最新指标 + issues 数 + 每日快照。"""
    overview = _github_overview(conn)
    return ok(
        {
            "repo": overview,
            "issues": crud.github.list_issues(
                conn,
                (settings.SOURCES.get("github") or {}).get("repo") or "",
                limit=int((settings.SOURCES.get("github") or {}).get("issue_limit") or 50),
                include_prs=bool((settings.SOURCES.get("github") or {}).get("include_prs")),
            ),
            "snapshots": crud.github.snapshots(
                conn, (settings.SOURCES.get("github") or {}).get("repo")
            ),
        }
    )


# ---------------------------------------------------------------- 登记

@router.get("/submissions/stats", tags=["submissions"])
def submissions_stats(conn: Connection = Depends(get_db)):
    """公开：登记聚合统计。"""
    return ok(crud.submissions.stats_summary(conn))


@router.get("/submissions/countries", tags=["submissions"])
def submissions_countries(conn: Connection = Depends(get_db)):
    """公开：按国家/地区去重主体与单位。"""
    items = crud.submissions.country_breakdown(conn)
    for item in items:
        item["country_name"] = COUNTRY_NAMES.get(item["country"], item["country"])
    return ok({"items": items, "total": len(items)})


@router.get("/submissions/organizations", tags=["submissions"])
def submissions_organizations(conn: Connection = Depends(get_db)):
    """公开：机构类型 -> 单位的两级分布。"""
    items = crud.submissions.org_tree(conn)
    return ok(
        {
            "items": items,
            "total": sum(len(group["organizations"]) for group in items),
        }
    )


@router.get("/submissions/export", tags=["submissions"])
def submissions_export(
    country: str | None = None,
    affiliation_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    _: None = Depends(require_admin),
    conn: Connection = Depends(get_db),
):
    """管理员：导出登记明细 CSV（UTF-8 BOM）。"""
    rows = crud.submissions.export_rows(
        conn,
        country=country,
        affiliation_type=affiliation_type,
        date_from=date_from,
        date_to=date_to,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(crud.submissions.EXPORT_COLUMNS)
    for row in rows:
        record = dict(row)
        writer.writerow(
            ["" if record.get(column) is None else record.get(column)
             for column in crud.submissions.EXPORT_COLUMNS]
        )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="submissions.csv"'},
    )


# ---------------------------------------------------------------- 下载

@router.get("/downloads", tags=["downloads"])
def downloads_list(
    source: str | None = Query(default=None, description="huggingface / modelscope"),
    q: str | None = Query(default=None, description="repo_id 关键字"),
    repo_id: str | None = Query(default=None, description="精确仓库 id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn: Connection = Depends(get_db),
):
    """公开：按仓库获取最新下载量（过滤 / 分页 / 按下载量倒序）。"""
    return ok(
        crud.downloads.download_info(
            conn,
            settings.SOURCES,
            source=source,
            q=q,
            repo_id=repo_id,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/downloads/sources", tags=["downloads"])
def downloads_sources(conn: Connection = Depends(get_db)):
    """公开：各下载渠道的仓库数、累计下载与最近采集时间。"""
    return ok({"items": _download_sources(conn)})


@router.get("/downloads/summary", tags=["downloads"])
def downloads_summary(conn: Connection = Depends(get_db)):
    """公开：全站下载总览（渠道、仓库数、下载量、更新时间）。"""
    return ok(crud.downloads.summary(conn))


@router.get("/downloads/trend", tags=["downloads"])
def downloads_trend(
    days: int = Query(default=30, ge=1, le=365),
    conn: Connection = Depends(get_db),
):
    """公开：各渠道每日累计下载趋势。"""
    return ok(
        {
            "days": days,
            "latest": crud.downloads.latest_by_source(conn),
            "series": crud.downloads.trend_series(conn, days=days),
        }
    )


@router.get("/downloads/metrics", tags=["downloads"])
def downloads_metrics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str | None = None,
    _: None = Depends(require_admin),
    conn: Connection = Depends(get_db),
):
    """管理员：下载量原始快照。"""
    rows, total = crud.downloads.list_metrics(
        conn, page=page, page_size=page_size, source=source
    )
    return ok(
        {
            "items": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/downloads/metrics/{metric_id}", tags=["downloads"])
def downloads_metric(
    metric_id: int,
    _: None = Depends(require_admin),
    conn: Connection = Depends(get_db),
):
    """管理员：单条下载快照。"""
    metric = crud.downloads.get_metric(conn, metric_id)
    if metric is None:
        raise HTTPException(status_code=404, detail="下载快照不存在")
    return ok(metric)


@router.get("/downloads/{source}/{repo_id:path}", tags=["downloads"])
def downloads_repo_detail(
    source: str,
    repo_id: str,
    days: int = Query(default=30, ge=1, le=365),
    conn: Connection = Depends(get_db),
):
    """公开：单个仓库的最新下载量 + 每日历史。"""
    latest = crud.downloads.get_repo_metric(conn, source, repo_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="下载快照不存在")
    latest["url"] = crud.downloads.repo_url(
        source, repo_id, settings.SOURCES.get(source)
    )
    return ok(
        {
            "source": source,
            "repo_id": repo_id,
            "latest": latest,
            "history": crud.downloads.repo_history(conn, source, repo_id, days=days),
            "days": days,
        }
    )


# ---------------------------------------------------------------- 论文

@router.get("/papers", tags=["papers"])
def papers_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    year: int | None = None,
    q: str | None = Query(default=None, description="标题/作者/期刊关键词"),
    role: str | None = Query(default=None, description="用途角色过滤"),
    min_citations: int | None = Query(default=None, ge=0),
    conn: Connection = Depends(get_db),
):
    """公开：引用论文列表（含用途角色、使用方式和评价数）。"""
    items, total = crud.papers.list_papers(
        conn,
        page=page,
        page_size=page_size,
        year=year,
        q=q,
        role=role,
        min_citations=min_citations,
    )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/papers/stats", tags=["papers"])
def papers_stats(conn: Connection = Depends(get_db)):
    """公开：论文引用统计与全文洞察汇总。"""
    data = crud.papers.stats_summary(conn)
    data["insights"] = crud.papers.insights_summary(conn)
    return ok(data)


@router.get("/papers/insights", tags=["papers"])
def papers_insights(conn: Connection = Depends(get_db)):
    """公开：数据用途 / 他人评价 / 关键词汇总。"""
    return ok(crud.papers.insights_summary(conn))


@router.get("/papers/snapshots", tags=["papers"])
def papers_snapshots(conn: Connection = Depends(get_db)):
    """公开：种子论文每日引用快照与种子论文元信息。"""
    return ok(crud.papers.list_snapshots(conn))


@router.get("/papers/{paper_id}", tags=["papers"])
def paper_detail(paper_id: int, conn: Connection = Depends(get_db)):
    """公开：单篇论文详情（元数据 + 全文分析）。"""
    paper = crud.papers.get_paper(conn, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    return ok(paper)


# ---------------------------------------------------------------- GitHub

@router.get("/github", tags=["github"])
def github_overview(conn: Connection = Depends(get_db)):
    """公开：仓库指标 + open issues + 每日快照。"""
    cfg = settings.SOURCES.get("github") or {}
    if not settings.source_active("github"):
        return ok({"enabled": False, "repo": None, "issues": [], "snapshots": []})
    data = _github_overview(conn, refresh_issues=True) or {"repo": cfg.get("repo")}
    return ok(
        {
            "enabled": True,
            "repo": data,
            "issues": crud.github.list_issues(
                conn,
                cfg.get("repo") or "",
                limit=int(cfg.get("issue_limit") or 50),
                include_prs=bool(cfg.get("include_prs")),
            ),
            "snapshots": crud.github.snapshots(conn, cfg.get("repo")),
        }
    )


@router.get("/github/repo", tags=["github"])
def github_repo(conn: Connection = Depends(get_db)):
    """公开：GitHub 仓库最新指标。"""
    return ok(_github_overview(conn))


@router.get("/github/issues", tags=["github"])
def github_issues(
    limit: int | None = Query(default=None, ge=1, le=500),
    conn: Connection = Depends(get_db),
):
    """公开：open issues 列表。"""
    cfg = settings.SOURCES.get("github") or {}
    if settings.source_active("github"):
        ensure_issues_cached(conn, cfg)
    repo = cfg.get("repo") or ""
    include_prs = bool(cfg.get("include_prs"))
    items = crud.github.list_issues(
        conn,
        repo,
        limit=limit or int(cfg.get("issue_limit") or 50),
        include_prs=include_prs,
    )
    return ok({"repo": repo, "items": items, "total": len(items)})


@router.get("/github/snapshots", tags=["github"])
def github_snapshots(conn: Connection = Depends(get_db)):
    """公开：GitHub 每日 stars/forks/issues 快照。"""
    repo = (settings.SOURCES.get("github") or {}).get("repo")
    return ok({"repo": repo, "items": crud.github.snapshots(conn, repo)})


# ---------------------------------------------------------------- 同步状态

@router.get("/sync/status", tags=["sync"])
def sync_status(conn: Connection = Depends(get_db)):
    """公开：各数据源配置、最近采集时间与进度。"""
    downloads = {item["source"]: item for item in crud.downloads.source_summary(conn)}
    paper_count, paper_latest = conn.execute(
        "SELECT COUNT(*), MAX(date) FROM paper_snapshots"
    ).fetchone()
    github_repo = crud.github.get_repo(
        conn, (settings.SOURCES.get("github") or {}).get("repo")
    )
    figures = {}
    for name, cfg in settings.SOURCES.items():
        entry = {
            "label": SOURCE_LABELS.get(name, name),
            "active": settings.source_active(name),
        }
        if name in DOWNLOAD_SOURCES:
            stat = downloads.get(name) or {}
            entry.update(
                {
                    "repos": stat.get("repos", 0),
                    "downloads": stat.get("downloads", 0),
                    "latest_fetched_at": stat.get("latest_fetched_at"),
                }
            )
        elif name == "paper":
            entry.update(
                {
                    "arxiv_id": cfg.get("arxiv_id"),
                    "papers": paper_count,
                    "latest_snapshot": paper_latest,
                }
            )
        elif name == "github":
            entry.update(
                {
                    "repo": cfg.get("repo"),
                    "stars": github_repo["stars"] if github_repo else None,
                    "latest_fetched_at": github_repo["fetched_at"] if github_repo else None,
                }
            )
        figures[name] = entry
    return ok({"scheduler": settings.sync_summary(), "sources": figures})


@router.post("/sync", tags=["sync"])
def sync_now(_: None = Depends(require_admin)):
    """管理员：后台触发一轮采集（立即返回，不阻塞请求）。"""
    return ok({"started": trigger_async()})
