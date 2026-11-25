import secrets
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import Header, HTTPException, Request

from .config import settings


class RateLimiter:
    """进程内滑动窗口限频（仅防刷，不记录 IP，不持久化）。"""

    def __init__(self, limit: int, window_seconds: int = 3600) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试")
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter(settings.RATE_LIMIT_PER_HOUR)


def client_ip(request: Request) -> str:
    """仅用于提交限频，不落库。"""
    if settings.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, settings.ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="管理员认证失败")
