"""SQLite 数据层：建表、连接。所有表都围绕"通用项目统计"设计。"""

import os
import sqlite3
from typing import Iterator

from .config import settings

SCHEMA = """
-- 手工登记（世界地图 / 国家 / 趋势 / 单位分布的数据来源）
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    affiliation_type TEXT NOT NULL,
    organization TEXT NOT NULL,
    info TEXT,
    email TEXT,
    project_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source TEXT NOT NULL DEFAULT 'form'
);
CREATE INDEX IF NOT EXISTS idx_submissions_country ON submissions(country);
CREATE INDEX IF NOT EXISTS idx_submissions_affiliation ON submissions(affiliation_type);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);

-- 下载量快照（HuggingFace / ModelScope）
CREATE TABLE IF NOT EXISTS download_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    downloads INTEGER NOT NULL,
    likes INTEGER,
    extra_json TEXT,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_download_metrics_lookup
    ON download_metrics(source, repo_id, fetched_at);
CREATE INDEX IF NOT EXISTS idx_download_metrics_fetched
    ON download_metrics(fetched_at);
CREATE INDEX IF NOT EXISTS idx_download_metrics_latest
    ON download_metrics(source, repo_id, id);

-- 引用种子论文的论文（Semantic Scholar）
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    s2_id TEXT UNIQUE,
    arxiv_id TEXT,
    doi TEXT,
    title TEXT NOT NULL,
    authors_json TEXT,
    year INTEGER,
    publication_date TEXT,
    venue TEXT,
    citation_count INTEGER NOT NULL DEFAULT 0,
    abstract TEXT,
    fields_json TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);

-- 论文全文分析结果（MinerU + 大模型）：数据用途 / 评价 / 关键词
CREATE TABLE IF NOT EXISTS paper_insights (
    s2_id TEXT PRIMARY KEY,
    arxiv_id TEXT,
    role TEXT,
    usage TEXT,
    keywords_json TEXT,
    comments_json TEXT,
    md_path TEXT,
    analyzed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    model TEXT
);
CREATE INDEX IF NOT EXISTS idx_paper_insights_role ON paper_insights(role);

-- 每日论文快照：种子论文被引 / 引用论文数 / 引用论文总被引
CREATE TABLE IF NOT EXISTS paper_snapshots (
    date TEXT PRIMARY KEY,
    seed_citations INTEGER NOT NULL DEFAULT 0,
    citing_papers INTEGER NOT NULL DEFAULT 0,
    citing_citations INTEGER NOT NULL DEFAULT 0
);

-- 项目元信息（如种子论文标题、URL）
CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- GitHub 仓库实时指标
CREATE TABLE IF NOT EXISTS github_repo (
    repo TEXT PRIMARY KEY,
    stars INTEGER NOT NULL DEFAULT 0,
    forks INTEGER NOT NULL DEFAULT 0,
    watchers INTEGER NOT NULL DEFAULT 0,
    open_issues INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    homepage TEXT,
    language TEXT,
    topics_json TEXT,
    html_url TEXT,
    fetched_at TEXT
);

-- GitHub 每日快照
CREATE TABLE IF NOT EXISTS github_snapshots (
    date TEXT NOT NULL,
    repo TEXT NOT NULL,
    stars INTEGER NOT NULL DEFAULT 0,
    forks INTEGER NOT NULL DEFAULT 0,
    open_issues INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, repo)
);

-- GitHub open issues 缓存
CREATE TABLE IF NOT EXISTS github_issues (
    number INTEGER PRIMARY KEY,
    repo TEXT,
    title TEXT NOT NULL,
    state TEXT,
    user TEXT,
    labels_json TEXT,
    created_at TEXT,
    updated_at TEXT,
    html_url TEXT,
    comments INTEGER DEFAULT 0,
    is_pr INTEGER DEFAULT 0,
    body_preview TEXT,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_github_issues_repo ON github_issues(repo);
"""


def connect() -> sqlite3.Connection:
    # FastAPI 的同步依赖与 sync 端点可能在不同线程执行；
    # 每个请求独立连接，允许跨线程顺序使用（不共享连接）。
    conn = sqlite3.connect(settings.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db() -> None:
    parent = os.path.dirname(settings.DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = connect()
    try:
        # WAL 是数据库级持久设置，初始化时设置一次即可；
        # 每个连接都执行 journal_mode 写 PRAGMA 会在并发下争锁。
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
