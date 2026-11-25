"""采集器注册表与统一执行入口。"""

from ..config import settings
from ..database import connect
from . import github, huggingface, modelscope, paper_insights, papers
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

        # 论文全文分析独立于 S2 引用采集：S2 限流时仍继续分析已有论文
        if (not only or "paper" in only) and settings.insights_active():
            try:
                cfg = (settings.SOURCES.get("paper") or {}).get("insights") or {}
                count = paper_insights.collect(conn, cfg)
                results["paper_insights"] = {"ok": True, "count": count}
            except Exception as exc:
                log.exception("paper_insights 分析失败")
                results["paper_insights"] = {"ok": False, "error": str(exc)[:500]}
    finally:
        if own_conn:
            conn.close()
    return results
