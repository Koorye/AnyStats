"""采集器公共工具。"""

import logging
from datetime import datetime, timezone

log = logging.getLogger("anystats.sync")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
