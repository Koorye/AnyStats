#!/usr/bin/env python3
"""手动采集入口：适合 crontab / systemd timer 部署（Web 服务内置定时器时可不用）。

用法：
    python scripts/sync.py                 # 采集所有已启用数据源
    python scripts/sync.py --source paper  # 只采论文引用
    python scripts/sync.py --source huggingface --source modelscope
"""

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.collectors.registry import run_once  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402

log = logging.getLogger("anystats.sync")


def main() -> int:
    parser = argparse.ArgumentParser(description="AnyStats 手动采集")
    parser.add_argument(
        "--source",
        action="append",
        choices=["huggingface", "modelscope", "paper", "github"],
        help="只采集指定数据源，可重复；默认全部",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=os.environ.get("ANYSTATS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    init_db()
    active = settings.active_sources()
    if not active:
        log.warning("没有已启用的数据源，请先编辑 config.yaml")
        return 0
    results = run_once(only=args.source)
    failed = [name for name, result in results.items() if not result.get("ok")]
    for name, result in results.items():
        status = "跳过" if result.get("skipped") else ("成功" if result.get("ok") else "失败")
        log.info("%s：%s %s", name, status, result.get("count", result.get("error", "")))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
