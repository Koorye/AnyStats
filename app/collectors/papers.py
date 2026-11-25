"""论文引用采集：Semantic Scholar，统计引用种子 arXiv 论文的全部论文。"""

import time

import httpx

from ..crud import papers as crud_papers
from .base import log, today_utc

S2_BASE = "https://api.semanticscholar.org/graph/v1"
CITATION_FIELDS = (
    "title,authors,year,venue,publicationDate,externalIds,citationCount,"
    "abstract,fieldsOfStudy,s2FieldsOfStudy,publicationTypes"
)
SEED_FIELDS = "title,citationCount,year,venue,publicationDate,externalIds,authors"


class SemanticScholar:
    def __init__(self, api_key: str = "") -> None:
        self.client = httpx.Client(timeout=30, follow_redirects=True)
        self.headers = {"x-api-key": api_key} if api_key else {}

    def get(self, path: str, **params) -> dict:
        params = {key: value for key, value in params.items() if value is not None}
        last_error = ""
        for attempt in range(4):
            resp = self.client.get(f"{S2_BASE}{path}", params=params, headers=self.headers)
            if resp.status_code == 429:
                try:
                    wait = int(resp.headers.get("retry-after", 0) or 0)
                except ValueError:
                    wait = 0
                wait = min(max(wait, 5 * (attempt + 1)), 60)
                log.warning("Semantic Scholar 限流，%ss 后重试（%s/4）", wait, attempt + 1)
                time.sleep(wait)
                last_error = "429 Too Many Requests"
                continue
            if resp.status_code == 404:
                raise RuntimeError(f"Semantic Scholar 未收录该论文：{path}")
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Semantic Scholar 持续限流：{last_error}")


def collect(conn, cfg: dict) -> int:
    arxiv_id = (cfg.get("arxiv_id") or "").strip()
    if not arxiv_id:
        raise RuntimeError("paper.arxiv_id 未配置")
    api = SemanticScholar(cfg.get("s2_api_key") or "")

    seed = api.get(f"/paper/arXiv:{arxiv_id}", fields=SEED_FIELDS)
    ext = seed.get("externalIds") or {}
    crud_papers.set_meta(
        conn,
        "seed_paper",
        {
            "title": seed.get("title"),
            "arxiv_id": arxiv_id,
            "doi": ext.get("DOI"),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "venue": seed.get("venue"),
            "year": seed.get("year"),
            "citation_count": int(seed.get("citationCount") or 0),
            "authors": [a.get("name") for a in (seed.get("authors") or []) if a.get("name")],
        },
    )

    offset, limit, total, count = 0, 100, 0, 0
    while True:
        data = api.get(
            f"/paper/arXiv:{arxiv_id}/citations",
            fields=CITATION_FIELDS,
            offset=offset,
            limit=limit,
        )
        total = int(data.get("total") or 0)
        for item in data.get("data") or []:
            paper = item.get("citingPaper") or {}
            if not paper.get("title") or not paper.get("paperId"):
                continue
            ids = paper.get("externalIds") or {}
            topics = [
                topic.get("displayName")
                for topic in (paper.get("s2FieldsOfStudy") or [])
                if topic.get("displayName")
            ]
            crud_papers.upsert_paper(
                conn,
                {
                    "s2_id": paper.get("paperId"),
                    "arxiv_id": ids.get("ArXiv"),
                    "doi": ids.get("DOI"),
                    "title": paper["title"],
                    "authors": [
                        author.get("name")
                        for author in (paper.get("authors") or [])
                        if author.get("name")
                    ],
                    "year": paper.get("year"),
                    "publication_date": paper.get("publicationDate"),
                    "venue": paper.get("venue") or None,
                    "citation_count": int(paper.get("citationCount") or 0),
                    "abstract": paper.get("abstract"),
                    "fields": {
                        "fos": paper.get("fieldsOfStudy") or [],
                        "topics": topics,
                    },
                },
            )
            count += 1
        offset = int(data.get("next") or 0)
        if not offset or (total and offset >= total):
            break
        time.sleep(1.2)  # 无密钥时限速约 1 req/s

    citing_citations = int(
        conn.execute("SELECT COALESCE(SUM(citation_count), 0) FROM papers").fetchone()[0]
    )
    crud_papers.save_snapshot(
        conn,
        today_utc(),
        seed_citations=int(seed.get("citationCount") or 0),
        citing_papers=total or count,
        citing_citations=citing_citations,
    )
    log.info(
        "paper: 种子论文被引 %s，引用论文 %s 篇（本次更新 %s）",
        seed.get("citationCount"), total or count, count,
    )
    return total or count
