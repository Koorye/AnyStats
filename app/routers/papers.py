from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from .. import crud
from ..database import get_db
from ..response import ok

router = APIRouter(prefix="/api/v1/papers", tags=["papers"])


@router.get("")
def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    year: int | None = None,
    q: str | None = Query(default=None, description="标题/作者/期刊关键词"),
    conn: Connection = Depends(get_db),
):
    """引用种子论文的论文列表（公开）。"""
    items, total = crud.papers.list_papers(
        conn, page=page, page_size=page_size, year=year, q=q
    )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/insights")
def papers_insights(conn: Connection = Depends(get_db)):
    """数据用途 / 他人评价 / 关键词（MinerU + 大模型分析结果）。"""
    return ok(crud.papers.insights_summary(conn))


@router.get("/stats")
def papers_stats(conn: Connection = Depends(get_db)):
    """学术影响统计：引用数、按年份、期刊、Top 被引。"""
    return ok(crud.papers.stats_summary(conn))
