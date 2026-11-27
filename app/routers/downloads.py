from sqlite3 import Connection

from fastapi import APIRouter, Depends, Query

from .. import crud
from ..config import settings
from ..database import get_db
from ..response import ok
from ..security import require_admin

router = APIRouter(prefix="/api/v1", tags=["downloads"])


@router.get("/download-sources", include_in_schema=False)
def list_sources(conn: Connection = Depends(get_db)):
    """下载渠道列表：配置的仓库 + 历史快照，附带最新下载量。"""
    return ok({"items": crud.downloads.list_sources(conn, settings.SOURCES)})


@router.get("/downloads/info", include_in_schema=False)
def download_info(
    source: str | None = Query(
        default=None,
        description="渠道过滤，如 huggingface / modelscope",
    ),
    q: str | None = Query(default=None, description="repo_id 关键字（不区分大小写）"),
    repo_id: str | None = Query(default=None, description="精确仓库 id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn: Connection = Depends(get_db),
):
    """公开：按仓库获取最新下载量信息（过滤 / 分页 / 按下载量倒序）。

    适合外部站点或脚本批量拉取下载量；历史快照仍通过
    `/api/v1/stats/downloads` 与 `/api/v1/downloads/metrics`（管理员）获取。
    """
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


@router.get("/downloads/metrics", include_in_schema=False)
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
