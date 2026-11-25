import csv
import io
from datetime import datetime, timezone
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import crud
from ..config import settings
from ..database import get_db
from ..response import ok
from ..security import require_admin

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


def _paper_brief(conn: Connection) -> dict | None:
    if not settings.source_active("paper"):
        return None
    data = crud.papers.stats_summary(conn)
    return {
        "citing_papers": data["citing_papers"],
        "citing_citations": data["citing_citations"],
        "seed_citations": (data.get("seed") or {}).get("citation_count"),
    }


def _github_brief(conn: Connection) -> dict | None:
    cfg = settings.SOURCES.get("github") or {}
    if not settings.source_active("github"):
        return None
    repo = crud.github.get_repo(conn, cfg.get("repo"))
    if not repo:
        return None
    return {
        "repo": repo["repo"],
        "stars": repo["stars"],
        "forks": repo["forks"],
        "open_issues": repo["open_issues"],
    }


@router.get("/summary")
def summary(conn: Connection = Depends(get_db)):
    """公开聚合统计：只含数字，不含个人信息。"""
    data = crud.submissions.stats_summary(conn)
    data["downloads"] = {"latest": crud.downloads.latest_by_source(conn)}
    data["paper"] = _paper_brief(conn)
    data["github"] = _github_brief(conn)
    return ok(data)


@router.get("/downloads")
def downloads_stats(days: int = Query(default=30, ge=1, le=365),
                    conn: Connection = Depends(get_db)):
    """下载量趋势：每源每日取最后一条快照，避免同日多次采集重复计数。"""
    return ok(
        {
            "latest": crud.downloads.latest_by_source(conn),
            "trend": {"days": days, "series": crud.downloads.trend_series(conn, days=days)},
        }
    )


@router.get("/export")
def export(
    format: str = "csv",
    country: str | None = None,
    affiliation_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    _: None = Depends(require_admin),
    conn: Connection = Depends(get_db),
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="当前仅支持 format=csv")
    rows = crud.submissions.export_rows(
        conn,
        country=country,
        affiliation_type=affiliation_type,
        date_from=date_from,
        date_to=date_to,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(crud.submissions.EXPORT_COLUMNS)
    for row in rows:
        record = dict(row)
        writer.writerow(
            ["" if record.get(col) is None else record.get(col)
             for col in crud.submissions.EXPORT_COLUMNS]
        )
    filename = f"anystats_export_{datetime.now(timezone.utc):%Y%m%d}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),  # BOM：Excel 直接打开不乱码
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
