"""手工登记表单的读写与基础聚合。"""

from sqlite3 import Connection
from typing import Optional

from ..config import settings
from ..schemas import SubmissionCreate

# 去重"主体"：优先邮箱；无邮箱则 姓名|国家|规范化单位。
# 去重"单位"：LOWER + TRIM，大小写/首尾空格差异合并为同一单位。
SUBJECT_VIEW = """
SELECT name, country, affiliation_type, organization,
       COALESCE(NULLIF(LOWER(TRIM(email)), ''),
                LOWER(TRIM(name)) || '|' || country || '|' || LOWER(TRIM(organization)))
           AS subject_key,
       LOWER(TRIM(organization)) AS org_key
FROM submissions
"""

EXPORT_COLUMNS = [
    "id",
    "name",
    "country",
    "affiliation_type",
    "organization",
    "info",
    "email",
    "project_version",
    "created_at",
    "source",
]


def create_submission(conn: Connection, data: SubmissionCreate) -> int:
    cur = conn.execute(
        """INSERT INTO submissions
               (name, country, affiliation_type, organization, info, email, project_version)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data.name,
            data.country,
            data.affiliation_type,
            data.organization,
            data.info,
            str(data.email).strip().lower() if data.email else None,
            settings.PROJECT_VERSION,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_submission(conn: Connection, submission_id: int):
    return conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()


def list_submissions(
    conn: Connection,
    *,
    page: int,
    page_size: int,
    country: Optional[str] = None,
    affiliation_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    where, params = [], []
    if country:
        where.append("country = ?")
        params.append(country.upper())
    if affiliation_type:
        where.append("affiliation_type = ?")
        params.append(affiliation_type)
    if date_from:
        where.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("created_at <= ?")
        params.append(date_to)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM submissions{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM submissions{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return rows, total


def export_rows(conn: Connection, **filters):
    rows, _ = list_submissions(conn, page=1, page_size=10**9, **filters)
    return rows


def _group_counts(conn: Connection, column: str) -> list[dict]:
    rows = conn.execute(
        f"SELECT {column} AS key, COUNT(*) AS count FROM submissions "
        f"GROUP BY {column} ORDER BY count DESC, key"
    ).fetchall()
    return [{"key": row["key"], "count": row["count"]} for row in rows]


def stats_summary(conn: Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    unique = conn.execute(
        "SELECT COUNT(DISTINCT subject_key), COUNT(DISTINCT org_key) FROM "
        f"({SUBJECT_VIEW})"
    ).fetchone()
    monthly = conn.execute(
        "SELECT substr(created_at, 1, 7) AS month, COUNT(*) AS count "
        "FROM submissions GROUP BY month ORDER BY month"
    ).fetchall()
    return {
        "total": total,
        "subjects_unique": unique[0],
        "organizations_unique": unique[1],
        "by_country": _group_counts(conn, "country"),
        "by_affiliation_type": _group_counts(conn, "affiliation_type"),
        "by_project_version": _group_counts(conn, "project_version"),
        "top_organizations": _group_counts(conn, "organization"),
        "monthly_trend": [dict(row) for row in monthly],
    }
