"""论文引用（Semantic Scholar）的写入与统计。"""

import json
from collections import Counter
from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_paper(conn: Connection, rec: dict) -> None:
    """按 s2_id 幂等写入；已存在的论文只更新元数据与引用数。"""
    conn.execute(
        """INSERT INTO papers
               (s2_id, arxiv_id, doi, title, authors_json, year, publication_date,
                venue, citation_count, abstract, fields_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(s2_id) DO UPDATE SET
               arxiv_id = excluded.arxiv_id,
               doi = excluded.doi,
               title = excluded.title,
               authors_json = excluded.authors_json,
               year = excluded.year,
               publication_date = excluded.publication_date,
               venue = excluded.venue,
               citation_count = excluded.citation_count,
               abstract = excluded.abstract,
               fields_json = excluded.fields_json,
               updated_at = excluded.updated_at""",
        (
            rec.get("s2_id"),
            rec.get("arxiv_id"),
            rec.get("doi"),
            rec["title"],
            json.dumps(rec.get("authors") or [], ensure_ascii=False),
            rec.get("year"),
            rec.get("publication_date"),
            rec.get("venue"),
            int(rec.get("citation_count") or 0),
            rec.get("abstract"),
            json.dumps(rec.get("fields") or {}, ensure_ascii=False),
            now_iso(),
        ),
    )
    conn.commit()


def save_snapshot(
    conn: Connection,
    date: str,
    *,
    seed_citations: int,
    citing_papers: int,
    citing_citations: int,
) -> None:
    conn.execute(
        """INSERT INTO paper_snapshots (date, seed_citations, citing_papers, citing_citations)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
               seed_citations = excluded.seed_citations,
               citing_papers = excluded.citing_papers,
               citing_citations = excluded.citing_citations""",
        (date, seed_citations, citing_papers, citing_citations),
    )
    conn.commit()


def set_meta(conn: Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )
    conn.commit()


def get_meta(conn: Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM project_meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def list_papers(
    conn: Connection,
    *,
    page: int,
    page_size: int,
    year: Optional[int] = None,
    q: Optional[str] = None,
    role: Optional[str] = None,
    min_citations: Optional[int] = None,
):
    where, params = [], []
    if year:
        where.append("p.year = ?")
        params.append(year)
    if q:
        where.append("(p.title LIKE ? OR p.authors_json LIKE ? OR p.venue LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if role:
        where.append("i.role = ?")
        params.append(role)
    if min_citations is not None:
        where.append("p.citation_count >= ?")
        params.append(min_citations)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    base = " FROM papers p LEFT JOIN paper_insights i ON i.s2_id = p.s2_id"
    total = conn.execute(f"SELECT COUNT(*) {base}{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT p.id, p.s2_id, p.arxiv_id, p.doi, p.title, p.authors_json, p.year,
                   p.publication_date, p.venue, p.citation_count,
                   i.role, i.usage, i.keywords_json, i.comments_json
            {base}{clause}
            ORDER BY COALESCE(p.year, 0) DESC, p.citation_count DESC, p.id DESC
            LIMIT ? OFFSET ?""",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["authors"] = json.loads(item.pop("authors_json") or "[]")
        item["keywords"] = json.loads(item.pop("keywords_json") or "[]")
        comments = json.loads(item.pop("comments_json") or "[]")
        item["comments"] = comments
        item["comments_count"] = len(comments)
        item["url"] = _paper_url(item)
        items.append(item)
    return items, total


def _paper_url(item: dict) -> Optional[str]:
    if item.get("arxiv_id"):
        return f"https://arxiv.org/abs/{item['arxiv_id']}"
    if item.get("doi"):
        return f"https://doi.org/{item['doi']}"
    if item.get("s2_id"):
        return f"https://api.semanticscholar.org/paper/{item['s2_id']}"
    return None


def get_paper(conn: Connection, paper_id: int) -> Optional[dict]:
    """单篇论文详情：元数据 + 全文分析（role/usage/keywords/comments）。"""
    row = conn.execute(
        """SELECT p.*, i.role, i.usage, i.keywords_json, i.comments_json,
                  i.md_path, i.analyzed_at, i.model
           FROM papers p LEFT JOIN paper_insights i ON i.s2_id = p.s2_id
           WHERE p.id = ?""",
        (paper_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["authors"] = json.loads(item.pop("authors_json") or "[]")
    item["keywords"] = json.loads(item.pop("keywords_json") or "[]")
    item["comments"] = json.loads(item.pop("comments_json") or "[]")
    item["fields"] = json.loads(item.pop("fields_json") or "{}")
    item["url"] = _paper_url(item)
    return item


def list_snapshots(conn: Connection) -> dict:
    snapshots = [
        dict(row)
        for row in conn.execute(
            "SELECT date, seed_citations, citing_papers, citing_citations "
            "FROM paper_snapshots ORDER BY date"
        )
    ]
    return {"items": snapshots, "seed": get_meta(conn, "seed_paper", {})}


def insights_summary(conn: Connection, *, limit: int = 300) -> dict:
    """数据用途 / 他人评价 / 关键词聚合（来自 MinerU + 大模型分析）。"""
    rows = conn.execute(
        """SELECT pi.arxiv_id, pi.role, pi.usage, pi.keywords_json, pi.comments_json,
                  p.title, p.year
           FROM paper_insights pi
           JOIN papers p ON p.s2_id = pi.s2_id
           ORDER BY COALESCE(p.year, 0) DESC, pi.analyzed_at DESC"""
    ).fetchall()
    roles: Counter = Counter()
    keywords: Counter = Counter()
    usages: list[dict] = []
    comments: list[dict] = []
    for row in rows:
        if row["role"]:
            roles[row["role"]] += 1
        url = f"https://arxiv.org/abs/{row['arxiv_id']}" if row["arxiv_id"] else None
        if row["usage"]:
            usages.append(
                {
                    "title": row["title"],
                    "arxiv_id": row["arxiv_id"],
                    "year": row["year"],
                    "url": url,
                    "usage": row["usage"],
                }
            )
        try:
            row_keywords = json.loads(row["keywords_json"] or "[]")
        except Exception:
            row_keywords = []
        for keyword in row_keywords:
            if isinstance(keyword, str) and keyword.strip():
                keywords[keyword.strip().lower()] += 1
        try:
            row_comments = json.loads(row["comments_json"] or "[]")
        except Exception:
            row_comments = []
        for comment in row_comments:
            if not isinstance(comment, dict) or not comment.get("text"):
                continue
            sentiment = comment.get("sentiment") or "neutral"
            if sentiment not in ("positive", "neutral", "negative"):
                sentiment = "neutral"
            comments.append(
                {
                    "title": row["title"],
                    "arxiv_id": row["arxiv_id"],
                    "year": row["year"],
                    "url": url,
                    "text": comment["text"],
                    "sentiment": sentiment,
                }
            )
    sentiments: Counter = Counter(item["sentiment"] for item in comments)
    return {
        "analyzed": len(rows),
        "roles": [{"role": role, "count": count} for role, count in roles.most_common()],
        "keywords": [
            {"keyword": keyword, "count": count}
            for keyword, count in keywords.most_common(40)
        ],
        "usages": usages[:limit],
        "comments": comments[:limit],
        "sentiments": dict(sentiments),
    }


def stats_summary(conn: Connection) -> dict:
    total, cites = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(citation_count), 0) FROM papers"
    ).fetchone()
    by_year = [
        {"year": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT year, COUNT(*) FROM papers WHERE year IS NOT NULL "
            "GROUP BY year ORDER BY year"
        )
    ]
    top_venues = [
        {"venue": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT venue, COUNT(*) AS n FROM papers "
            "WHERE venue IS NOT NULL AND TRIM(venue) != '' "
            "GROUP BY venue ORDER BY n DESC, venue LIMIT 8"
        )
    ]
    top_cited = []
    for row in conn.execute(
        """SELECT title, authors_json, year, venue, citation_count, arxiv_id, doi, s2_id
           FROM papers ORDER BY citation_count DESC, id DESC LIMIT 8"""
    ):
        top_cited.append(
            {
                "title": row["title"],
                "authors": json.loads(row["authors_json"] or "[]"),
                "year": row["year"],
                "venue": row["venue"],
                "citation_count": row["citation_count"],
                "url": (
                    f"https://arxiv.org/abs/{row['arxiv_id']}" if row["arxiv_id"]
                    else (f"https://doi.org/{row['doi']}" if row["doi"]
                          else (f"https://api.semanticscholar.org/paper/{row['s2_id']}"
                                if row["s2_id"] else None))
                ),
            }
        )
    growth, acc = [], 0
    for item in by_year:
        acc += item["count"]
        growth.append({"year": item["year"], "papers": acc})
    snapshots = [
        dict(row)
        for row in conn.execute(
            "SELECT date, seed_citations, citing_papers, citing_citations "
            "FROM paper_snapshots ORDER BY date"
        )
    ]
    seed = get_meta(conn, "seed_paper", {}) or {}
    if snapshots:
        seed = {**seed, "citation_count": snapshots[-1]["seed_citations"]}
    return {
        "citing_papers": total,
        "citing_citations": cites,
        "seed": seed,
        "by_year": by_year,
        "top_venues": top_venues,
        "top_cited": top_cited,
        "growth_by_year": growth,
        "snapshots": snapshots,
        "latest_snapshot": snapshots[-1] if snapshots else None,
    }
