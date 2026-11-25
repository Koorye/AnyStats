import os
from pathlib import Path

# 必须在导入 app 之前设置：config 在导入时读取配置路径
os.environ["ANYSTATS_CONFIG"] = str(Path(__file__).parent / "fixtures" / "config.test.yaml")
os.environ.pop("ANYSTATS_DB_PATH", None)

import pytest
from fastapi.testclient import TestClient

from app import config, security
from app.database import init_db
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config.settings, "SYNC_ENABLED", False)
    security.limiter.reset()
    init_db()
    with TestClient(app) as c:
        yield c
