"""AnyStats 入口：FastAPI 应用 + 内置每日采集线程（一键启动即全功能）。"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .dashboard_page import dashboard_html
from .database import init_db
from .pages import index_html, submit_html
from .routers import dashboard, downloads, github, papers, stats, submissions
from .scheduler import SyncScheduler

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(
    level=os.environ.get("ANYSTATS_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("anystats")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.ADMIN_TOKEN == "change-me":
        log.warning(
            "site.admin_token 仍为默认值 change-me：管理员接口（登记明细 / CSV / 原始快照）"
            "等同于公开，对外部署前请修改，或改用 ANYSTATS_ADMIN_TOKEN 环境变量"
        )
    scheduler = None
    if settings.SYNC_ENABLED:
        scheduler = SyncScheduler()
        scheduler.start()
        log.info("定时采集已启动：每天 %s（启动先采：%s）",
                 settings.SYNC_AT, settings.SYNC_ON_START)
    yield
    if scheduler is not None:
        scheduler.stop()


app = FastAPI(
    title=settings.SITE_TITLE,
    description=settings.SITE_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
)

origins = [item.strip() for item in settings.CORS_ORIGINS.split(",") if item.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (submissions, stats, downloads, dashboard, papers, github):
    app.include_router(module.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz", tags=["meta"])
def healthz():
    return {"status": "ok", "app": settings.SITE_TITLE, "version": settings.PROJECT_VERSION}


@app.get("/", include_in_schema=False)
def index():
    return HTMLResponse(index_html())


@app.get("/submit", include_in_schema=False)
def submit_page():
    return HTMLResponse(submit_html())


@app.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return HTMLResponse(dashboard_html())


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
