"""ModelScope 数据集下载量采集（官方 modelscope-hub 包）。"""

from modelscope_hub import HubApi

from ..crud import downloads as crud_downloads
from .base import log


def collect(conn, cfg: dict) -> int:
    org, extra = cfg.get("org"), cfg.get("repos") or []
    api = HubApi(token=cfg.get("token") or None)

    infos = []
    if org:
        page, page_size = 1, 50  # 接口限制 page_size ≤ 50
        while True:
            res = api.list_repos("dataset", owner=org, page_number=page, page_size=page_size)
            items = getattr(res, "items", None) or []
            infos.extend(items)
            total = int(getattr(res, "total_count", 0) or getattr(res, "total", 0) or 0)
            if not items or (total and len(infos) >= total):
                break
            page += 1
    for repo_id in extra:
        try:
            infos.append(api.get_repo(repo_id, "dataset"))
        except Exception as exc:
            log.error("modelscope/%s 信息获取失败：%s", repo_id, exc)

    rows = {}
    for info in infos:
        repo_id = getattr(info, "repo_id", None) or getattr(info, "id", None)
        if not repo_id:
            continue
        rows[repo_id] = (
            int(getattr(info, "downloads", 0) or 0),
            getattr(info, "likes", None),
            None,
        )
    if not rows:
        raise RuntimeError("ModelScope 未返回任何仓库，检查 org/repos 配置")
    crud_downloads.insert_snapshot(
        conn, "modelscope", [(repo_id, *vals) for repo_id, vals in rows.items()]
    )
    log.info("modelscope: 采集 %s 个仓库", len(rows))
    return len(rows)
