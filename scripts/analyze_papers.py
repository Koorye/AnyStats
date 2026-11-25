#!/usr/bin/env python3
"""手动运行/补跑论文全文分析（MinerU + 大模型）。

日常由每日采集自动增量执行；本脚本用于补跑、单篇重跑或只解析 PDF。

用法：
    .venv/bin/python scripts/analyze_papers.py                 # 增量（最多 max_papers_per_run 篇）
    .venv/bin/python scripts/analyze_papers.py --all           # 增量，不限制本轮数量
    .venv/bin/python scripts/analyze_papers.py --only VISTA    # 只处理标题含该子串的论文
    .venv/bin/python scripts/analyze_papers.py --only VISTA --force   # 强制重跑
    .venv/bin/python scripts/analyze_papers.py --only VISTA --parse-only  # 只让 MinerU 落盘 markdown
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.collectors.paper_insights import collect  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import connect, init_db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="论文全文分析：MinerU 解析 + 大模型抽取数据用途/评价/关键词"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="本轮最多处理几篇（默认取 config 的 max_papers_per_run）")
    parser.add_argument("--all", action="store_true", help="不限制本轮数量")
    parser.add_argument("--only", help="只处理标题含该子串的论文")
    parser.add_argument("--force", action="store_true", help="已有分析结果的也重跑")
    parser.add_argument("--refresh-md", action="store_true", help="忽略 markdown 缓存重新调 MinerU")
    parser.add_argument("--parse-only", action="store_true", help="只解析 PDF 落盘，不做大模型分析")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = (settings.SOURCES.get("paper") or {}).get("insights") or {}
    if not cfg.get("enabled"):
        print("paper.insights.enabled 未开启，请先编辑 config.yaml")
        return 1
    if not cfg.get("project_keyword"):
        print("缺少 paper.insights.project_keyword（要分析的项目名）")
        return 1
    if not args.parse_only and not cfg.get("llm_api_key"):
        print("缺少 paper.insights.llm_api_key，无法做分析")
        return 1

    init_db()
    conn = connect()
    try:
        limit = 0 if args.all else args.limit
        done = collect(
            conn,
            cfg,
            limit=limit,
            only=args.only,
            force=args.force,
            refresh_md=args.refresh_md,
            parse_only=args.parse_only,
        )
        print(f"完成：{done} 篇")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
