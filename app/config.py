"""AnyStats 配置加载。

唯一配置文件是项目根目录的 config.yaml（本地文件，已 gitignore；模板为
config.example.yaml）；所有字段都能用环境变量覆盖，方便 Docker / 多实例部署。
测试可通过 ANYSTATS_CONFIG 指向测试配置。
"""

import copy
import os
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"

SOURCE_LABELS = {
    "huggingface": "HuggingFace",
    "modelscope": "ModelScope",
    "paper": "论文引用",
    "github": "GitHub",
}


def _env(name: str, default: Any = None) -> Any:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(value)


class Settings:
    """config.yaml 的运行时视图（纯属性，便于测试 monkeypatch）。"""

    def __init__(self, config_path: Optional[str] = None) -> None:
        path = Path(_env("ANYSTATS_CONFIG", config_path or DEFAULT_CONFIG_PATH))
        if not path.is_absolute():
            path = ROOT / path
        self.CONFIG_PATH = str(path)
        if not path.exists():
            raise FileNotFoundError(
                f"未找到配置文件 {path}；请复制 config.yaml 或设置 ANYSTATS_CONFIG"
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._raw = raw

        site = raw.get("site") or {}
        server = raw.get("server") or {}
        database = raw.get("database") or {}
        submit = raw.get("submit") or {}
        sync = raw.get("sync") or {}
        sources = raw.get("sources") or {}

        # ---------- 站点 ----------
        self.SITE_TITLE = str(_env("ANYSTATS_TITLE", site.get("title", "AnyStats")))
        self.SITE_SUBTITLE = str(site.get("subtitle", "开源项目数据统计"))
        self.SITE_DESCRIPTION = str(site.get("description", ""))
        self.PROJECT_VERSION = str(site.get("project_version", "1.0.0"))
        self.ADMIN_TOKEN = str(_env("ANYSTATS_ADMIN_TOKEN", site.get("admin_token", "change-me")))
        self.FOOTER = str(site.get("footer", ""))
        self.DASHBOARD_AUTH = _as_bool(_env("ANYSTATS_DASHBOARD_AUTH", site.get("dashboard_auth")), False)

        # ---------- 服务 ----------
        self.HOST = str(_env("ANYSTATS_HOST", server.get("host", "0.0.0.0")))
        self.PORT = int(_env("ANYSTATS_PORT", server.get("port", 8100)))
        self.CORS_ORIGINS = str(_env("ANYSTATS_CORS_ORIGINS", server.get("cors_origins", "*")))
        self.TRUST_PROXY = _as_bool(_env("ANYSTATS_TRUST_PROXY", server.get("trust_proxy")), False)
        self.RATE_LIMIT_PER_HOUR = int(_env("ANYSTATS_RATE_LIMIT_PER_HOUR", 10))

        # ---------- 数据库 ----------
        db_path = str(_env("ANYSTATS_DB_PATH", database.get("path", "data/anystats.db")))
        self.DB_PATH = str(db_path if os.path.isabs(db_path) else ROOT / db_path)

        # ---------- 登记表单 ----------
        self.SUBMIT_TITLE = str(submit.get("title", "使用登记"))
        self.SUBMIT_DESCRIPTION = str(
            submit.get("description", "请在使用本项目前登记以下信息，带 * 为必填项。")
        )
        self.SUBMIT_LICENSE_TEXT = str(submit.get("license_text", "我已阅读并同意本项目使用条款"))
        self.SUBMIT_ORG_EXAMPLE = str(submit.get("org_example", "如：某某大学机器人实验室"))

        # ---------- 定时采集 ----------
        self.SYNC_ENABLED = _as_bool(_env("ANYSTATS_SYNC_ENABLED", sync.get("enabled", True)), True)
        self.SYNC_AT = str(_env("ANYSTATS_SYNC_AT", sync.get("daily_at", "03:00")))
        self.SYNC_ON_START = _as_bool(_env("ANYSTATS_SYNC_ON_START", sync.get("run_on_start", True)), True)
        try:
            hour, minute = (int(part) for part in self.SYNC_AT.split(":"))
        except ValueError:
            raise ValueError(f"sync.daily_at 需要 HH:MM 格式，当前为 {self.SYNC_AT!r}") from None
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError(f"sync.daily_at 时间越界：{self.SYNC_AT!r}")

        # ---------- 数据源 ----------
        self.SOURCES = self._build_sources(sources)

    # ------------------------------------------------------------------
    @staticmethod
    def _build_sources(raw: dict) -> dict:
        hf = copy.deepcopy(raw.get("huggingface") or {})
        ms = copy.deepcopy(raw.get("modelscope") or {})
        paper = copy.deepcopy(raw.get("paper") or {})
        github = copy.deepcopy(raw.get("github") or {})

        hf.update(
            enabled=_as_bool(hf.get("enabled"), True),
            org=str(hf.get("org") or "").strip(),
            repos=[str(r).strip() for r in _as_list(hf.get("repos")) if str(r).strip()],
            endpoint=str(_env("HF_ENDPOINT", hf.get("endpoint") or "")).strip().rstrip("/"),
            use_proxy=_as_bool(_env("HF_USE_PROXY", hf.get("use_proxy")), False),
            token=str(_env("HF_TOKEN", hf.get("token") or "")),
        )
        ms.update(
            enabled=_as_bool(ms.get("enabled"), True),
            org=str(ms.get("org") or "").strip(),
            repos=[str(r).strip() for r in _as_list(ms.get("repos")) if str(r).strip()],
            token=str(_env("MODELSCOPE_API_TOKEN", _env("MS_TOKEN", ms.get("token") or ""))),
        )
        paper.update(
            enabled=_as_bool(paper.get("enabled"), True),
            arxiv_id=str(paper.get("arxiv_id") or "").strip(),
            s2_api_key=str(_env("S2_API_KEY", paper.get("s2_api_key") or "")),
        )
        insights = copy.deepcopy(paper.get("insights") or {})
        paper["insights"] = {
            "enabled": _as_bool(insights.get("enabled"), False),
            "project_keyword": str(insights.get("project_keyword") or ""),
            "mineru_token": str(_env("MINERU_TOKEN", insights.get("mineru_token") or "")),
            "llm_api_key": str(_env("DEEPSEEK_API_KEY", insights.get("llm_api_key") or "")),
            "llm_base": str(_env("DEEPSEEK_BASE", insights.get("llm_base")
                                 or "https://api.deepseek.com")).rstrip("/"),
            "llm_model": str(_env("DEEPSEEK_MODEL", insights.get("llm_model")
                                  or "deepseek-v4-flash")),
            "cache_dir": str(insights.get("cache_dir") or "data/mineru"),
            "max_papers_per_run": int(insights.get("max_papers_per_run") or 5),
        }
        github.update(
            enabled=_as_bool(github.get("enabled"), True),
            repo=str(github.get("repo") or "").strip(),
            token=str(_env("GITHUB_TOKEN", github.get("token") or "")),
            include_prs=_as_bool(github.get("include_prs"), False),
            issue_limit=int(github.get("issue_limit") or 50),
        )
        return {
            "huggingface": hf,
            "modelscope": ms,
            "paper": paper,
            "github": github,
        }

    # ------------------------------------------------------------------
    def source_active(self, name: str) -> bool:
        """该数据源是否已启用且配置了目标（否则采集跳过、面板隐藏）。"""
        cfg = self.SOURCES.get(name) or {}
        if not cfg.get("enabled"):
            return False
        if name in {"huggingface", "modelscope"}:
            return bool(cfg.get("org") or cfg.get("repos"))
        if name == "paper":
            return bool(cfg.get("arxiv_id"))
        if name == "github":
            return bool(cfg.get("repo"))
        return False

    def active_sources(self) -> list[str]:
        return [name for name in self.SOURCES if self.source_active(name)]

    def insights_active(self) -> bool:
        """全文用途/评价分析是否可用（启用 + 项目名 + 大模型 key）。"""
        cfg = (self.SOURCES.get("paper") or {}).get("insights") or {}
        return bool(self.source_active("paper") and cfg.get("enabled")
                    and cfg.get("project_keyword") and cfg.get("llm_api_key"))

    def public_info(self) -> dict:
        """给前端的安全配置（不含令牌）。"""
        return {
            "title": self.SITE_TITLE,
            "subtitle": self.SITE_SUBTITLE,
            "description": self.SITE_DESCRIPTION,
            "version": self.PROJECT_VERSION,
            "footer": self.FOOTER,
            "dashboard_auth": self.DASHBOARD_AUTH,
            "sources": {
                name: {
                    "label": SOURCE_LABELS.get(name, name),
                    "active": self.source_active(name),
                }
                for name in self.SOURCES
            },
            "targets": {
                "huggingface": self.SOURCES["huggingface"].get("org")
                or ", ".join(self.SOURCES["huggingface"].get("repos") or []),
                "modelscope": self.SOURCES["modelscope"].get("org")
                or ", ".join(self.SOURCES["modelscope"].get("repos") or []),
                "paper": self.SOURCES["paper"].get("arxiv_id"),
                "github": self.SOURCES["github"].get("repo"),
            },
        }

    def sync_summary(self) -> dict:
        return {
            "enabled": self.SYNC_ENABLED,
            "daily_at": self.SYNC_AT,
            "run_on_start": self.SYNC_ON_START,
        }


settings = Settings()
