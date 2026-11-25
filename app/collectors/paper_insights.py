"""论文全文分析：MinerU 解析 PDF -> markdown -> 大模型抽取「数据用途 / 他人评价 / 关键词」。

流程（每篇新论文）：
  1. 下载 arXiv PDF 地址提交 MinerU（vlm 模型）；
  2. 轮询任务，下载结果 zip，解出 full.md，缓存到 data/mineru/{arxiv_id}.md；
  3. 把论文中项目名（如 MyProject）出现的上下文 + 标题交给 DeepSeek；
  4. 抽取 role（数据用途类别）/ usage（具体用法）/ comments（评价与情感）/ keywords；
  5. 写入 paper_insights 表。

已有 markdown 缓存的论文不会重复调用 MinerU；已有分析结果的论文默认跳过。
"""

import io
import json
import logging
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import ROOT

MINERU_BASE = "https://mineru.net/api/v4"

ROLES = (
    "related_work", "concept_reference", "base_data", "training_data",
    "finetune_data", "benchmark", "comparison_baseline", "extension", "other",
)
SENTIMENTS = ("positive", "neutral", "negative")

log = logging.getLogger("anystats.insights")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cache_dir(cfg: dict) -> Path:
    path = Path(cfg.get("cache_dir") or "data/mineru")
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_regex(keyword: str) -> re.Pattern:
    """MyProject -> /my\\s?project/i，兼容论文中的 MyProject / My Project / myproject。"""
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", keyword or "")
    if not parts:
        return re.compile(re.escape(keyword or ""), re.IGNORECASE)
    return re.compile(r"\s?".join(re.escape(part) for part in parts), re.IGNORECASE)


# ---------------------------------------------------------------- MinerU

def _headers(mineru_token: str) -> dict:
    return {"Authorization": f"Bearer {mineru_token}"}


def _submit_task(client: httpx.Client, token: str, arxiv_id: str) -> str | None:
    for attempt, wait in enumerate((5, 30, 90), 1):
        try:
            resp = client.post(
                f"{MINERU_BASE}/extract/task",
                headers=_headers(token),
                json={"url": f"https://arxiv.org/pdf/{arxiv_id}", "model_version": "vlm"},
                timeout=60,
            )
            if resp.status_code == 429:
                log.warning("MinerU 提交限流，%ss 后第 %s 次重试", wait, attempt)
                time.sleep(wait)
                continue
            body = resp.json()
            if not isinstance(body, dict) or body.get("code") != 0:
                log.warning("MinerU 提交失败 %s: %s", arxiv_id, body)
                return None
            return body["data"]["task_id"]
        except Exception as exc:
            log.warning("MinerU 提交异常 %s: %s", arxiv_id, exc)
            time.sleep(wait)
    return None


def _poll_task(client: httpx.Client, token: str, task_id: str, timeout_s: int = 900) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = client.get(
                f"{MINERU_BASE}/extract/task/{task_id}",
                headers=_headers(token),
                timeout=30,
            )
            data = resp.json().get("data") or {}
            state = data.get("state")
            if state == "done":
                return data.get("full_zip_url")
            if state == "failed":
                log.warning("MinerU 任务失败 %s: %s", task_id, data.get("err_msg"))
                return None
        except Exception as exc:
            log.warning("MinerU 轮询异常 %s: %s", task_id, exc)
        time.sleep(8)
    log.warning("MinerU 任务超时 %s", task_id)
    return None


def _download_md(client: httpx.Client, zip_url: str) -> str | None:
    for attempt in range(3):
        try:
            resp = client.get(zip_url, timeout=180, follow_redirects=True)
            if resp.status_code != 200:
                time.sleep(5)
                continue
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    if name.endswith("full.md"):
                        return zf.read(name).decode("utf-8", errors="ignore")
            log.warning("MinerU zip 内无 full.md: %s", zip_url)
            return None
        except Exception as exc:
            log.warning("MinerU 结果下载重试 %s/3: %s", attempt + 1, exc)
            time.sleep(8)
    return None


def _ensure_markdown(client: httpx.Client, cfg: dict, rows, refresh: bool) -> dict[str, Path]:
    """确保论文 markdown 已落盘，返回 {arxiv_id: 本地路径}。"""
    cache = _cache_dir(cfg)
    tasks_file = cache / "tasks.json"
    try:
        known_tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
    except Exception:
        known_tasks = {}

    have: dict[str, Path] = {}
    todo: list[tuple[str, Path]] = []
    for row in rows:
        arxiv_id = row["arxiv_id"]
        if not arxiv_id:
            continue
        path = cache / f"{arxiv_id}.md"
        if path.exists() and path.stat().st_size > 500 and not refresh:
            have[arxiv_id] = path
        else:
            todo.append((arxiv_id, path))

    if not todo:
        log.info("Markdown 缓存齐全（%s 篇）", len(have))
        return have
    token = cfg.get("mineru_token") or ""
    if not token:
        log.warning("缺少 MinerU 令牌，%s 篇论文没有全文缓存，跳过", len(todo))
        return have

    tasks: list[tuple[str, str]] = []
    for arxiv_id, _path in todo:
        task_id = known_tasks.get(arxiv_id) or _submit_task(client, token, arxiv_id)
        if task_id:
            known_tasks[arxiv_id] = task_id
            tasks_file.write_text(json.dumps(known_tasks, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
            tasks.append((arxiv_id, task_id))
        time.sleep(1.5)
    log.info("MinerU 任务就绪 %s/%s", len(tasks), len(todo))

    for index, (arxiv_id, task_id) in enumerate(tasks, 1):
        zip_url = _poll_task(client, token, task_id)
        if not zip_url:
            continue
        markdown = _download_md(client, zip_url)
        if not markdown:
            continue
        path = cache / f"{arxiv_id}.md"
        path.write_text(markdown, encoding="utf-8")
        have[arxiv_id] = path
        log.info("[%s/%s] %s -> %s (%s KB)", index, len(tasks), arxiv_id, path,
                 len(markdown) // 1024)
    return have


# ---------------------------------------------------------------- LLM

def _context(md_text: str, keyword: str) -> str:
    fragments = []
    for match in _project_regex(keyword).finditer(md_text):
        start = max(0, match.start() - 350)
        fragment = re.sub(r"\s+", " ", md_text[start:match.end() + 450]).strip()
        if fragment not in fragments:
            fragments.append(fragment)
        if len(fragments) >= 10:
            break
    return "\n---\n".join(fragments)[:7000]


def extract(client: httpx.Client, cfg: dict, title: str, md_text: str) -> dict | None:
    project = cfg.get("project_keyword") or "the project"
    context = _context(md_text, project)
    prompt = (
        "你是论文信息抽取助手。基于论文全文解析结果，抽取以下信息，只输出一个 JSON：\n"
        '{"role": "related_work|concept_reference|base_data|training_data|finetune_data|'
        'benchmark|comparison_baseline|extension|other", '
        '"usage": "一句话：本文具体如何使用 ' + project + '（用了哪些数据/子集/数量、'
        '训练还是评测、如何混合等；仅引用则空串）", '
        '"comments": [{"text": "论文中对 ' + project + ' 的评价原文摘录", '
        '"sentiment": "positive|neutral|negative"}], '
        '"keywords": ["6-10 个核心技术关键词"]}\n'
        "规则：\n"
        "1) role 取最强用途：training_data=直接训练集；finetune_data=微调；base_data=二次构建数据；"
        "benchmark=评测基准；comparison_baseline=对比基线；extension=其直接扩展；"
        "related_work=仅相关工作提及；concept_reference=概念/动机参考；other=其余。\n"
        "2) usage 必须是具体用法（子集名称/数据量/任务/训练或评测方式），泛泛提及则填空串。\n"
        "3) comments 只摘录论文中真实出现的评价语句（0-3 条，保留原文语言），不要编造；"
        "指出局限/不足为 negative，称赞规模/多样性/质量为 positive。\n"
        "4) keywords 为 6-10 个小写英文技术短语（如 vla、world model、diffusion policy、"
        "bimanual），不要 robot/deep learning 等通用词。\n\n"
        f"标题：{title}\n\n项目相关段落：\n{context}\n"
    )
    resp = client.post(
        f"{cfg['llm_base']}/chat/completions",
        headers={"Authorization": f"Bearer {cfg['llm_api_key']}"},
        json={
            "model": cfg.get("llm_model") or "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 16000,
        },
        timeout=180,
    )
    content = (resp.json()["choices"][0]["message"].get("content") or "")
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        out = json.loads(match.group(0))
    except Exception:
        return None

    role = out.get("role") if out.get("role") in ROLES else "other"
    usage = (out.get("usage") or "").strip() or None
    comments = []
    for item in (out.get("comments") or []):
        if not isinstance(item, dict) or not item.get("text"):
            continue
        sentiment = item.get("sentiment")
        if sentiment not in SENTIMENTS:
            sentiment = "neutral"
        comments.append({"text": str(item["text"])[:400], "sentiment": sentiment})
    keywords = []
    for keyword in (out.get("keywords") or []):
        if isinstance(keyword, str) and keyword.strip():
            keywords.append(keyword.strip().lower())
    return {
        "role": role,
        "usage": usage,
        "comments": comments[:3],
        "keywords": list(dict.fromkeys(keywords))[:10],
    }


def _save(conn, row, out: dict, cfg: dict, md_path: Path) -> None:
    try:
        display_path = str(md_path.relative_to(ROOT))
    except ValueError:
        display_path = str(md_path)
    conn.execute(
        """INSERT INTO paper_insights
               (s2_id, arxiv_id, role, usage, keywords_json, comments_json,
                md_path, analyzed_at, model)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(s2_id) DO UPDATE SET
               arxiv_id = excluded.arxiv_id,
               role = excluded.role,
               usage = excluded.usage,
               keywords_json = excluded.keywords_json,
               comments_json = excluded.comments_json,
               md_path = excluded.md_path,
               analyzed_at = excluded.analyzed_at,
               model = excluded.model""",
        (
            row["s2_id"], row["arxiv_id"], out["role"], out["usage"],
            json.dumps(out["keywords"], ensure_ascii=False),
            json.dumps(out["comments"], ensure_ascii=False),
            display_path, _now(), cfg.get("llm_model") or "",
        ),
    )
    conn.commit()


# ---------------------------------------------------------------- 入口

def collect(conn, cfg: dict | None = None, *, limit: int | None = None,
            only: str | None = None, force: bool = False,
            refresh_md: bool = False, parse_only: bool = False) -> int:
    """增量分析新论文。返回成功入库（或 parse_only 时解析）的篇数。"""
    cfg = cfg or {}
    if not cfg.get("enabled"):
        return 0
    if not cfg.get("project_keyword"):
        log.warning("未配置 paper.insights.project_keyword，跳过论文全文分析")
        return 0
    if not cfg.get("llm_api_key") and not parse_only:
        log.warning("未配置大模型 key，跳过论文全文分析")
        return 0

    where = ["p.arxiv_id IS NOT NULL", "p.arxiv_id != ''"]
    params: list = []
    if only:
        where.append("p.title LIKE ?")
        params.append(f"%{only}%")
    if not force:
        where.append("i.s2_id IS NULL")
    rows = conn.execute(
        f"""SELECT p.s2_id, p.arxiv_id, p.title
            FROM papers p LEFT JOIN paper_insights i ON i.s2_id = p.s2_id
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(p.year, 0) DESC, p.id DESC""",
        params,
    ).fetchall()
    cap = limit if limit is not None else int(cfg.get("max_papers_per_run") or 5)
    if cap:
        rows = rows[:cap]
    if not rows:
        log.info("论文全文分析：没有待处理论文")
        return 0
    log.info("论文全文分析：待处理 %s 篇", len(rows))

    with httpx.Client(timeout=180, follow_redirects=True) as client:
        md_map = _ensure_markdown(client, cfg, rows, refresh_md)
        if parse_only:
            log.info("parse-only：已解析 %s 篇", len(md_map))
            return len(md_map)
        done = 0
        for row in rows:
            path = md_map.get(row["arxiv_id"])
            if not path:
                log.warning("无 markdown，跳过：%s", row["title"][:50])
                continue
            md_text = path.read_text(encoding="utf-8", errors="ignore")
            out = None
            for attempt in range(2):
                try:
                    out = extract(client, cfg, row["title"], md_text)
                    if out:
                        break
                except Exception as exc:
                    log.warning("大模型抽取失败 %s（第 %s 次）: %s",
                                row["arxiv_id"], attempt + 1, exc)
                time.sleep(8)
            if not out:
                log.warning("抽取失败：%s", row["title"][:50])
                continue
            _save(conn, row, out, cfg, path)
            done += 1
            log.info("✓ %s | %s | 用法 %s | 评价 %s 条 | 关键词 %s",
                     row["arxiv_id"], out["role"],
                     "有" if out["usage"] else "无",
                     len(out["comments"]), len(out["keywords"]))
            time.sleep(0.5)
    log.info("论文全文分析完成：%s/%s 篇", done, len(rows))
    return done
