"""内置定时采集：随 Web 服务一起启动，每天 SYNC_AT 采一轮（无需额外进程）。"""

import logging
import threading
from datetime import datetime, timedelta

from .collectors.registry import run_once
from .config import settings

log = logging.getLogger("anystats.sync")
_lock = threading.Lock()


def run_sync(only: list[str] | None = None) -> dict:
    """同步执行一轮采集（带进程内互斥）。"""
    if not _lock.acquire(blocking=False):
        log.warning("已有采集任务在执行，本次跳过")
        return {"skipped": True}
    try:
        return run_once(only=only)
    finally:
        _lock.release()


def trigger_async(only: list[str] | None = None) -> bool:
    """后台触发一轮采集；已在执行时返回 False。"""
    if _lock.locked():
        return False
    threading.Thread(target=run_sync, kwargs={"only": only},
                     name="anystats-sync", daemon=True).start()
    return True


class SyncScheduler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="anystats-scheduler")
        self._stop_event = threading.Event()
        self._last_run_date = None

    def run(self) -> None:
        if settings.SYNC_ON_START:
            self._run("启动时")
        while not self._stop_event.wait(30):
            now = datetime.now()
            hour, minute = (int(part) for part in settings.SYNC_AT.split(":"))
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if (self._last_run_date != now.date()
                    and scheduled <= now < scheduled + timedelta(minutes=10)):
                self._run("每日定时")

    def _run(self, reason: str) -> None:
        self._last_run_date = datetime.now().date()
        log.info("开始采集（%s）", reason)
        results = run_sync()
        failed = [name for name, result in results.items() if not result.get("ok")]
        log.info("采集完成：%s%s", results, f"；失败源 {failed}" if failed else "")

    def stop(self) -> None:
        self._stop_event.set()
