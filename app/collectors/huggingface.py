"""HuggingFace 数据集下载量采集（官方 huggingface_hub 包）。"""

from huggingface_hub import HfApi

from ..crud import downloads as crud_downloads
from .base import log
from .hf_env import apply_hf_env, resolve_hf_token


def collect(conn, cfg: dict) -> int:
    org, extra = cfg.get("org"), cfg.get("repos") or []
    endpoint = apply_hf_env(cfg.get("endpoint") or "", bool(cfg.get("use_proxy")))
    token = resolve_hf_token(cfg.get("token") or "", endpoint or "https://huggingface.co")
    api = HfApi(token=token, endpoint=endpoint)

    datasets = []
    if org:
        # expand 必须显式请求 downloadsAllTime，否则只返回近 30 天 downloads
        datasets.extend(
            api.list_datasets(author=org, expand=["downloadsAllTime", "downloads"])
        )
    for repo_id in extra:
        try:
            datasets.append(
                api.dataset_info(repo_id, expand=["downloadsAllTime", "downloads"])
            )
        except Exception as exc:
            log.error("huggingface/%s 信息获取失败：%s", repo_id, exc)

    rows = {}
    for ds in datasets:
        recent = getattr(ds, "downloads", 0) or 0
        all_time = getattr(ds, "downloads_all_time", None)
        rows[ds.id] = (
            int(all_time) if all_time is not None else int(recent),
            getattr(ds, "likes", None),
            {
                "downloads_recent": recent,
                "downloads_field": "all_time" if all_time is not None else "last_30_days",
            },
        )
    if not rows:
        raise RuntimeError("HuggingFace 未返回任何仓库，检查 org/repos 与端点配置")
    crud_downloads.insert_snapshot(
        conn, "huggingface", [(repo_id, *vals) for repo_id, vals in rows.items()]
    )
    log.info("huggingface: 采集 %s 个仓库（端点 %s）",
             len(rows), endpoint or "https://huggingface.co")
    return len(rows)
