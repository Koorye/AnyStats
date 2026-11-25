"""采集器注册表与统一执行入口。"""

from ..config import settings
from ..database import connect
from . import github, huggingface, modelscope, papers
from .base import log

COLLECTORS = {
    "huggingface": huggingface.collect,
    "modelscope": modelscope.collect,
    "paper": papers.collect,
    "github": github.collect,
}


def run_once(conn=None, only: list[str] | None = None) -> dict:
    """跑一轮采集；单源失败只记录，不影响其他源。返回各源结果。"""
    own_conn = conn is None
    if own_conn:
        conn = connect()
    results: dict[str, dict] = {}
    try:
        for name, fn in COLLECTORS.items():
            if only and name not in only:
                continue
            if not settings.source_active(name):
                results[name] = {"ok": True, "skipped": True, "count": 0}
                continue
            try:
                count = fn(conn, settings.SOURCES[name])
                results[name] = {"ok": True, "count": count}
            except Exception as exc:
                log.exception("%s 采集失败", name)
                results[name] = {"ok": False, "error": str(exc)[:500]}
    finally:
        if own_conn:
            conn.close()
    return results
