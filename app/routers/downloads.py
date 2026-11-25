from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from .. import crud
from ..config import settings
from ..database import get_db
from ..response import ok
from ..security import require_admin

router = APIRouter(prefix="/api/v1", tags=["downloads"])


@router.get("/download-sources")
def list_sources(conn: Connection = Depends(get_db)):
    """下载渠道列表：配置的仓库 + 历史快照，附带最新下载量。"""
    return ok({"items": crud.downloads.list_sources(conn, settings.SOURCES)})


@router.get("/downloads/metrics")
def list_metrics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str | None = None,
    _: None = Depends(require_admin),
    conn: Connection = Depends(get_db),
):
    """下载量原始快照明细（管理员）。"""
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
