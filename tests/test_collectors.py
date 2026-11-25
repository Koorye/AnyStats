from app import config
from app.collectors import registry
from app.collectors.hf_env import is_official_endpoint, resolve_hf_token


def test_source_activation_rules():
    hf = config.settings.SOURCES["huggingface"]
    assert config.settings.source_active("huggingface") is False  # 测试配置未填 org
    hf["enabled"], hf["org"] = True, "AnyOrg"
    assert config.settings.source_active("huggingface") is True
    hf["enabled"] = False
    assert config.settings.source_active("huggingface") is False
    hf["enabled"], hf["org"] = False, ""


def test_hf_endpoint_and_token_policy():
    assert is_official_endpoint("https://huggingface.co") is True
    assert is_official_endpoint("") is True
    assert is_official_endpoint("https://hf-mirror.com") is False
    # 镜像不发送令牌，官方端点才发送
    assert resolve_hf_token("hf_secret", "https://hf-mirror.com") is False
    assert resolve_hf_token("hf_secret", "https://huggingface.co") == "hf_secret"
    assert resolve_hf_token("", "https://huggingface.co") is False


def test_run_once_skips_disabled_sources():
    results = registry.run_once(only=["huggingface", "paper"])
    assert results["huggingface"]["skipped"] is True
    assert results["paper"]["skipped"] is True


def test_public_info_has_no_token():
    info = config.settings.public_info()
    assert "admin_token" not in str(info)
    assert info["sources"]["huggingface"]["label"] == "HuggingFace"
