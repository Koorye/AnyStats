from sqlite3 import Connection

from fastapi import APIRouter, Depends, Header, Query

from .. import crud
from ..config import settings
from ..database import get_db
from ..response import ok
from ..scheduler import trigger_async
from ..security import require_admin

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def dashboard_guard(x_admin_token: str | None = Header(default=None)) -> None:
    """面板鉴权：config.site.dashboard_auth=false 时公开。"""
    if settings.DASHBOARD_AUTH:
        require_admin(x_admin_token)


@router.get("/dashboard")
def dashboard(
    days: int = Query(default=30, ge=1, le=365),
    _: None = Depends(dashboard_guard),
    conn: Connection = Depends(get_db),
):
    """面板数据（实时读库聚合）。"""
    return ok(crud.dashboard.compute_dashboard(conn, trend_days=days))


@router.get("/meta")
def meta():
    """站点信息与数据源状态（不含令牌）。"""
    return ok({**settings.public_info(), "sync": settings.sync_summary()})


@router.post("/admin/sync", include_in_schema=False)
def trigger_sync(_: None = Depends(require_admin)):
    """后台触发一轮采集（不阻塞请求）。"""
    return ok({"started": trigger_async()})
