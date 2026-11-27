"""下载量快照的写入与聚合（HuggingFace / ModelScope 通用）。"""

import json
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection
from typing import Optional

DEFAULT_URL_TEMPLATES = {
    "huggingface": "https://huggingface.co/datasets/{repo_id}",
    "modelscope": "https://modelscope.cn/datasets/{repo_id}",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_metric(
    conn: Connection,
    *,
    source: str,
    repo_id: str,
    downloads: int,
    likes: Optional[int] = None,
    extra_json: Optional[str] = None,
    fetched_at: Optional[str] = None,
) -> None:
    conn.execute(
        "INSERT INTO download_metrics (source, repo_id, downloads, likes, extra_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source, repo_id, downloads, likes, extra_json, fetched_at or now_iso()),
    )
    conn.commit()


def insert_snapshot(conn: Connection, source: str, rows: list[tuple]) -> int:
    """整轮快照单事务落库，避免中途失败留下半份数据。

    rows: [(repo_id, downloads, likes, extra_dict|None), ...]
    """
    fetched_at = now_iso()
    conn.executemany(
        "INSERT INTO download_metrics (source, repo_id, downloads, likes, extra_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (source, repo_id, int(downloads), likes,
             json.dumps(extra, ensure_ascii=False) if extra else None, fetched_at)
            for repo_id, downloads, likes, extra in rows
        ],
    )
    conn.commit()
    return len(rows)


def latest_per_repo(conn: Connection) -> dict[tuple[str, str], dict]:
    """每个 (source, repo_id) 的最新一条快照。"""
    rows = conn.execute(
        "SELECT source, repo_id, downloads, likes, fetched_at "
        "FROM download_metrics ORDER BY id"
    ).fetchall()
    latest: dict[tuple[str, str], dict] = {}
    for row in rows:
        latest[(row["source"], row["repo_id"])] = dict(row)
    return latest


def repo_url(source: str, repo_id: str, cfg: Optional[dict] = None) -> Optional[str]:
    template = ((cfg or {}).get("url_template") or DEFAULT_URL_TEMPLATES.get(source))
    return template.format(repo_id=repo_id) if template else None


def list_sources(conn: Connection, sources: dict) -> list[dict]:
    """渠道列表 = 配置的仓库 + 历史快照中出现过的仓库，附带最新下载量。"""
    items: dict[tuple[str, str], dict] = {}

    def _slot(source: str, repo_id: str) -> dict:
        return items.setdefault(
            (source, repo_id),
            {
                "source": source,
                "repo_id": repo_id,
                "url": repo_url(source, repo_id, sources.get(source)),
                "latest_downloads": None,
                "latest_fetched_at": None,
            },
        )

    for source, cfg in sources.items():
        for repo_id in cfg.get("repos") or []:
            _slot(source, repo_id)
    for (source, repo_id), snap in latest_per_repo(conn).items():
        item = _slot(source, repo_id)
        item["latest_downloads"] = snap["downloads"]
        item["latest_fetched_at"] = snap["fetched_at"]
    return sorted(items.values(), key=lambda x: (x["source"], x["repo_id"]))


def latest_by_source(conn: Connection) -> list[dict]:
    """各渠道最新累计下载量（同渠道多仓库求和）。"""
    totals: dict[str, int] = {}
    for (_source, _repo), snap in latest_per_repo(conn).items():
        source = snap["source"]
        totals[source] = totals.get(source, 0) + snap["downloads"]
    return [{"source": source, "downloads": total} for source, total in sorted(totals.items())]


def download_info(
    conn: Connection,
    sources: dict,
    *,
    source: Optional[str] = None,
    q: Optional[str] = None,
    repo_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """按仓库查询最新下载量（公开接口）：过滤、分页、按下载量倒序。

    - source：huggingface / modelscope 等渠道过滤
    - q：repo_id 关键字（不区分大小写）
    - repo_id：精确仓库 id
    """
    items: list[dict] = []
    needle = q.strip().lower() if q else None
    for (src, rid), snap in latest_per_repo(conn).items():
        if source and src != source:
            continue
        if repo_id and rid != repo_id:
            continue
        if needle and needle not in rid.lower():
            continue
        items.append(
            {
                "source": src,
                "repo_id": rid,
                "downloads": int(snap["downloads"] or 0),
                "likes": snap.get("likes"),
                "url": repo_url(src, rid, sources.get(src)),
                "fetched_at": snap.get("fetched_at"),
            }
        )
    items.sort(key=lambda item: (-item["downloads"], item["repo_id"]))

    total = len(items)
    total_downloads = sum(item["downloads"] for item in items)
    updated_at = max((item["fetched_at"] or "" for item in items), default="") or None
    start = (page - 1) * page_size
    paged = items[start:start + page_size]

    grouped: dict[str, dict] = {}
    for item in items:
        entry = grouped.setdefault(
            item["source"],
            {"source": item["source"], "repos": 0, "downloads": 0, "latest_fetched_at": None},
        )
        entry["repos"] += 1
        entry["downloads"] += item["downloads"]
        if item["fetched_at"] and (
            entry["latest_fetched_at"] is None
            or item["fetched_at"] > entry["latest_fetched_at"]
        ):
            entry["latest_fetched_at"] = item["fetched_at"]

    return {
        "items": paged,
        "total": total,
        "total_downloads": total_downloads,
        "page": page,
        "page_size": page_size,
        "source_totals": sorted(grouped.values(), key=lambda item: item["source"]),
        "updated_at": updated_at,
    }


def source_summary(conn: Connection) -> list[dict]:
    """按渠道汇总最新快照：仓库数 / 累计下载 / 最近采集时间。"""
    grouped: dict[str, dict] = {}
    for (_source, _repo), snap in latest_per_repo(conn).items():
        entry = grouped.setdefault(
            snap["source"],
            {"source": snap["source"], "repos": 0, "downloads": 0, "latest_fetched_at": None},
        )
        entry["repos"] += 1
        entry["downloads"] += int(snap["downloads"] or 0)
        if snap["fetched_at"] and (
            entry["latest_fetched_at"] is None
            or snap["fetched_at"] > entry["latest_fetched_at"]
        ):
            entry["latest_fetched_at"] = snap["fetched_at"]
    return sorted(grouped.values(), key=lambda item: item["source"])


def summary(conn: Connection) -> dict:
    """下载量总览：渠道汇总 + 总仓库数 / 总下载量 / 最近更新时间。"""
    sources = source_summary(conn)
    return {
        "sources": sources,
        "repos": sum(item["repos"] for item in sources),
        "downloads": sum(item["downloads"] for item in sources),
        "updated_at": max((item["latest_fetched_at"] or "" for item in sources), default="") or None,
    }


def get_repo_metric(conn: Connection, source: str, repo_id: str) -> Optional[dict]:
    """单个仓库的最新一条快照。"""
    row = conn.execute(
        "SELECT source, repo_id, downloads, likes, extra_json, fetched_at "
        "FROM download_metrics WHERE source = ? AND repo_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (source, repo_id),
    ).fetchone()
    return dict(row) if row else None


def repo_history(conn: Connection, source: str, repo_id: str, days: int = 30) -> list[dict]:
    """单个仓库按天去重后的历史快照（每日取最后一条）。"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT substr(fetched_at, 1, 10) AS date, downloads, likes, fetched_at "
        "FROM download_metrics WHERE source = ? AND repo_id = ? AND fetched_at >= ? "
        "ORDER BY id",
        (source, repo_id, since),
    ).fetchall()
    by_day: dict[str, dict] = {}
    for row in rows:
        by_day[row["date"]] = {
            "date": row["date"],
            "downloads": int(row["downloads"] or 0),
            "likes": row["likes"],
            "fetched_at": row["fetched_at"],
        }
    return [by_day[day] for day in sorted(by_day)]


def get_metric(conn: Connection, metric_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM download_metrics WHERE id = ?", (metric_id,)
    ).fetchone()
    return dict(row) if row else None


def trend_series(conn: Connection, days: int = 30) -> dict[str, list[dict]]:
    """每日每仓取最后一条快照（同日多次采集不重复计入），再按渠道逐日汇总。"""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT substr(fetched_at, 1, 10) AS day, source, repo_id, downloads "
        "FROM download_metrics WHERE fetched_at >= ? ORDER BY id",
        (since,),
    ).fetchall()
    last_of_day: dict[tuple[str, str, str], int] = {}
    for row in rows:
        last_of_day[(row["day"], row["source"], row["repo_id"])] = row["downloads"]

    summed: dict[str, dict[str, int]] = {}
    for (day, source, _repo), downloads in last_of_day.items():
        summed.setdefault(source, {}).setdefault(day, 0)
        summed[source][day] += downloads
    return {
        source: [{"date": day, "downloads": value} for day, value in sorted(by_day.items())]
        for source, by_day in summed.items()
    }


def list_metrics(
    conn: Connection,
    *,
    page: int,
    page_size: int,
    source: Optional[str] = None,
):
    where, params = [], []
    if source:
        where.append("source = ?")
        params.append(source)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM download_metrics{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM download_metrics{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return rows, total
