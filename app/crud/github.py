"""GitHub 仓库指标、每日快照与 open issues 缓存。"""

import json
from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def upsert_repo(conn: Connection, repo: str, data: dict) -> None:
    conn.execute(
        """INSERT INTO github_repo
               (repo, stars, forks, watchers, open_issues, description, homepage,
                language, topics_json, html_url, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(repo) DO UPDATE SET
               stars = excluded.stars,
               forks = excluded.forks,
               watchers = excluded.watchers,
               open_issues = excluded.open_issues,
               description = excluded.description,
               homepage = excluded.homepage,
               language = excluded.language,
               topics_json = excluded.topics_json,
               html_url = excluded.html_url,
               fetched_at = excluded.fetched_at""",
        (
            repo,
            int(data.get("stars") or 0),
            int(data.get("forks") or 0),
            int(data.get("watchers") or 0),
            int(data.get("open_issues") or 0),
            data.get("description"),
            data.get("homepage"),
            data.get("language"),
            json.dumps(data.get("topics") or [], ensure_ascii=False),
            data.get("html_url"),
            now_iso(),
        ),
    )
    conn.commit()


def save_snapshot(conn: Connection, repo: str, date: Optional[str] = None) -> None:
    row = conn.execute(
        "SELECT stars, forks, open_issues FROM github_repo WHERE repo = ?", (repo,)
    ).fetchone()
    if not row:
        return
    conn.execute(
        """INSERT INTO github_snapshots (date, repo, stars, forks, open_issues)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(date, repo) DO UPDATE SET
               stars = excluded.stars,
               forks = excluded.forks,
               open_issues = excluded.open_issues""",
        (date or today_utc(), repo, row["stars"], row["forks"], row["open_issues"]),
    )
    conn.commit()


def replace_issues(conn: Connection, repo: str, issues: list[dict]) -> int:
    conn.execute("DELETE FROM github_issues WHERE repo = ?", (repo,))
    fetched_at = now_iso()
    conn.executemany(
        """INSERT OR REPLACE INTO github_issues
               (number, repo, title, state, user, labels_json, created_at, updated_at,
                html_url, comments, is_pr, body_preview, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                int(item["number"]),
                repo,
                item.get("title") or "",
                item.get("state"),
                (item.get("user") or {}).get("login"),
                json.dumps([label.get("name") for label in (item.get("labels") or [])
                            if label.get("name")], ensure_ascii=False),
                item.get("created_at"),
                item.get("updated_at"),
                item.get("html_url"),
                int(item.get("comments") or 0),
                1 if "pull_request" in item else 0,
                (item.get("body") or "").strip().replace("\r", "")[:400],
                fetched_at,
            )
            for item in issues
        ],
    )
    conn.commit()
    return len(issues)


def get_repo(conn: Connection, repo: Optional[str] = None) -> Optional[dict]:
    if repo:
        row = conn.execute("SELECT * FROM github_repo WHERE repo = ?", (repo,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM github_repo ORDER BY fetched_at DESC LIMIT 1").fetchone()
    if not row:
        return None
    item = dict(row)
    item["topics"] = json.loads(item.pop("topics_json") or "[]")
    return item


def latest_issue_fetch(conn: Connection, repo: str) -> Optional[float]:
    row = conn.execute(
        "SELECT MAX(CAST(fetched_at AS REAL)) FROM github_issues WHERE repo = ?", (repo,)
    ).fetchone()
    return row[0] if row else None


def list_issues(conn: Connection, repo: str, *, limit: int = 50, include_prs: bool = False) -> list[dict]:
    clause = "" if include_prs else " AND is_pr = 0"
    rows = conn.execute(
        f"SELECT * FROM github_issues WHERE repo = ?{clause} "
        "ORDER BY created_at DESC LIMIT ?",
        (repo, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["labels"] = json.loads(item.pop("labels_json") or "[]")
        items.append(item)
    return items


def snapshots(conn: Connection, repo: Optional[str] = None) -> list[dict]:
    if repo:
        rows = conn.execute(
            "SELECT date, stars, forks, open_issues FROM github_snapshots "
            "WHERE repo = ? ORDER BY date",
            (repo,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, stars, forks, open_issues FROM github_snapshots ORDER BY date"
        ).fetchall()
    return [dict(row) for row in rows]


def stats(conn: Connection, repo: Optional[str], *, issue_limit: int = 50,
          include_prs: bool = False) -> Optional[dict]:
    if not repo:
        return None
    data = get_repo(conn, repo)
    if not data:
        return None
    data["issues"] = list_issues(conn, repo, limit=issue_limit, include_prs=include_prs)
    data["snapshots"] = snapshots(conn, repo)
    return data
