"""GitHub 仓库指标 + open issues 采集。"""

import time

import httpx

from ..crud import github as crud_github
from .base import log, today_utc

API = "https://api.github.com"


def _headers(token: str = "") -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AnyStats",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repo(client: httpx.Client, repo: str, headers: dict) -> dict:
    resp = client.get(f"{API}/repos/{repo}", headers=headers)
    if resp.status_code == 404:
        raise RuntimeError(f"GitHub 仓库不存在或无权限：{repo}")
    if resp.status_code == 403:
        raise RuntimeError("GitHub API 限流，配置 token 可提高额度")
    resp.raise_for_status()
    data = resp.json()
    return {
        "stars": data.get("stargazers_count") or 0,
        "forks": data.get("forks_count") or 0,
        "watchers": data.get("subscribers_count") or data.get("watchers_count") or 0,
        "open_issues": data.get("open_issues_count") or 0,
        "description": data.get("description"),
        "homepage": data.get("homepage"),
        "language": data.get("language"),
        "topics": data.get("topics") or [],
        "html_url": data.get("html_url"),
    }


def fetch_issues(
    client: httpx.Client,
    repo: str,
    headers: dict,
    *,
    include_prs: bool = False,
    cap: int = 500,
) -> list[dict]:
    issues: list[dict] = []
    page = 1
    while len(issues) < cap:
        resp = client.get(
            f"{API}/repos/{repo}/issues",
            params={"state": "open", "per_page": 100, "page": page},
            headers=headers,
        )
        if resp.status_code == 403:
            raise RuntimeError("GitHub issues 接口限流，配置 token 可提高额度")
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for item in batch:
            if not include_prs and "pull_request" in item:
                continue
            issues.append(item)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.2)
    return issues[:cap]


def collect(conn, cfg: dict) -> int:
    repo = (cfg.get("repo") or "").strip()
    if not repo:
        raise RuntimeError("github.repo 未配置")
    headers = _headers(cfg.get("token") or "")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        data = fetch_repo(client, repo, headers)
        crud_github.upsert_repo(conn, repo, data)
        crud_github.save_snapshot(conn, repo, today_utc())
        issues = fetch_issues(
            client,
            repo,
            headers,
            include_prs=bool(cfg.get("include_prs")),
            cap=max(int(cfg.get("issue_limit") or 50) * 4, 200),
        )
        crud_github.replace_issues(conn, repo, issues)
    log.info("github: %s 星标 %s / forks %s / open issues %s",
             repo, data["stars"], data["forks"], len(issues))
    return len(issues)


def ensure_issues_cached(conn, cfg: dict, ttl: int = 1800) -> int:
    """API 请求时按 TTL 刷新 issues；缓存有效返回 -1。"""
    repo = (cfg.get("repo") or "").strip()
    if not repo:
        return -1
    last = crud_github.latest_issue_fetch(conn, repo)
    if last and time.time() - last < ttl:
        return -1
    headers = _headers(cfg.get("token") or "")
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            issues = fetch_issues(
                client,
                repo,
                headers,
                include_prs=bool(cfg.get("include_prs")),
                cap=max(int(cfg.get("issue_limit") or 50) * 4, 200),
            )
        if issues:
            crud_github.replace_issues(conn, repo, issues)
        return len(issues)
    except Exception as exc:
        log.warning("github issues 刷新失败（沿用缓存）：%s", exc)
        return -1
