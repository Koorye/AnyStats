"""HuggingFace 端点/代理配置。

国内服务器直连 huggingface.co 常被 DNS 污染 + TLS 阻断，默认走 hf-mirror.com；
进程若继承 HTTP(S)_PROXY/ALL_PROXY（例如本机代理节点失效），代理链路访问镜像
同样报 TLS EOF。因此非代理模式下强制 huggingface_hub 使用 trust_env=False 的
httpx 客户端（只靠 NO_PROXY 时 ALL_PROXY 会抢先命中，NO_PROXY 被忽略）。
"""

import os


def endpoint_host(endpoint: str) -> str:
    return endpoint.split("//", 1)[-1].split("/", 1)[0].strip().lower()


def is_official_endpoint(endpoint: str) -> bool:
    host = endpoint_host(endpoint)
    return not host or host == "huggingface.co" or host.endswith(".huggingface.co")


def apply_hf_env(endpoint: str, use_proxy: bool) -> str | None:
    """调整进程环境变量，返回应传给 HfApi(endpoint=...) 的值（None = 官方默认）。"""
    endpoint = (endpoint or "").strip().rstrip("/")
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint
    host = endpoint_host(endpoint)
    if host and not use_proxy:
        hosts = [h.strip() for h in os.environ.get("NO_PROXY", "").split(",") if h.strip()]
        if host not in {h.lower() for h in hosts}:
            hosts.append(host)
        os.environ["NO_PROXY"] = ",".join(hosts)
        _force_direct_client()
    return endpoint or None


def _force_direct_client() -> None:
    try:
        import httpx
        from huggingface_hub import set_client_factory
    except Exception:
        return
    set_client_factory(
        lambda: httpx.Client(follow_redirects=True, timeout=None, trust_env=False)
    )


def resolve_hf_token(token: str, endpoint: str) -> str | bool:
    """只对官方端点发送令牌，避免第三方镜像拿到组织令牌。"""
    if not token:
        return False
    return token if is_official_endpoint(endpoint) else False
