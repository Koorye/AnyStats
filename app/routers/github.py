from sqlite3 import Connection

from fastapi import APIRouter, Depends

from .. import crud
from ..collectors.github import ensure_issues_cached
from ..config import settings
from ..database import get_db
from ..response import ok

router = APIRouter(prefix="/api/v1/github", tags=["github"])


@router.get("", include_in_schema=False)
def github_overview(conn: Connection = Depends(get_db)):
    """仓库指标 + open issues（issues 30 分钟缓存，失败时沿用旧缓存）。"""
    cfg = settings.SOURCES.get("github") or {}
    if not settings.source_active("github"):
        return ok({"enabled": False, "repo": None, "issues": []})
    ensure_issues_cached(conn, cfg)
    data = crud.github.stats(
        conn,
        cfg.get("repo"),
        issue_limit=int(cfg.get("issue_limit") or 50),
        include_prs=bool(cfg.get("include_prs")),
    )
    return ok({"enabled": True, **(data or {"repo": cfg.get("repo"), "issues": []})})


@router.get("/issues", include_in_schema=False)
def github_issues(conn: Connection = Depends(get_db)):
    cfg = settings.SOURCES.get("github") or {}
    ensure_issues_cached(conn, cfg)
    return ok(
        {
            "repo": cfg.get("repo"),
            "items": crud.github.list_issues(
                conn,
                cfg.get("repo") or "",
                limit=int(cfg.get("issue_limit") or 50),
                include_prs=bool(cfg.get("include_prs")),
            ),
        }
    )
