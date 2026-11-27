"""进程内 TTL 缓存：给只读聚合接口挡住重复扫描。

数据每天才更新一次；下载曲线/总览这类接口允许几十秒的缓存。
缓存按 DB 路径隔离，测试的多临时库不会互相污染。
"""

import threading
import time
from typing import Any, Callable

_TTL_LOCK = threading.Lock()
_KEY_LOCKS: dict[Any, threading.Lock] = {}
_CACHE: dict[Any, tuple[float, Any]] = {}
_MAX_KEYS = 1000


def cached(key: Any, ttl: float, producer: Callable[[], Any]) -> Any:
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]

    with _TTL_LOCK:
        lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    with lock:  # 同一 key 只让一个请求回源，其余等待结果
        hit = _CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]
        value = producer()
        if len(_CACHE) >= _MAX_KEYS:
            _CACHE.clear()
        _CACHE[key] = (time.monotonic(), value)
        return value


def clear() -> None:
    with _TTL_LOCK:
        _CACHE.clear()
        _KEY_LOCKS.clear()
