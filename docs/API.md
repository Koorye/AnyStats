# AnyStats API

所有成功响应统一为：

```json
{"code": 0, "message": "ok", "data": ...}
```

校验失败返回 `422` + 字段级错误；管理员接口需请求头 `X-Admin-Token: <site.admin_token>`。

## 元信息

### GET /healthz

```json
{"status": "ok", "app": "AnyStats", "version": "1.0.0"}
```

### GET /api/v1/meta

站点信息、数据源启用状态与采集计划（不含任何令牌）。

```json
{
  "code": 0, "message": "ok",
  "data": {
    "title": "AnyStats",
    "subtitle": "开源项目数据统计",
    "sources": {"huggingface": {"label": "HuggingFace", "active": true}},
    "targets": {"huggingface": "RoboCOIN", "paper": "2511.17441"},
    "sync": {"enabled": true, "daily_at": "03:00", "run_on_start": true}
  }
}
```

## 使用登记

### POST /api/v1/submissions

公开；同 IP 每小时限频（`ANYSTATS_RATE_LIMIT_PER_HOUR`，默认 10），`website` 为蜜罐字段（非空直接 400）。

```json
{
  "name": "张三",
  "country": "CN",
  "affiliation_type": "university",
  "organization": "某某大学机器人实验室",
  "info": "选填",
  "email": "zhangsan@example.edu"
}
```

`affiliation_type`：`university` / `institute` / `company` / `personal` / `other`。

### GET /api/v1/submissions?page=1&page_size=20&country=CN&affiliation_type=university&date_from=2026-01-01&date_to=2026-12-31

管理员。返回 `{items, total, page, page_size}`。

### GET /api/v1/submissions/{id}

管理员。单条登记详情。

### GET /api/v1/stats/export?country=CN

管理员。导出 CSV（UTF-8 BOM，Excel 可直接打开）。

## 统计

### GET /api/v1/stats/summary

公开聚合（不含个人信息）：

```json
{
  "total": 100,
  "subjects_unique": 80,
  "organizations_unique": 40,
  "by_country": [{"key": "CN", "count": 50}],
  "by_affiliation_type": [{"key": "university", "count": 60}],
  "by_project_version": [{"key": "1.0.0", "count": 100}],
  "top_organizations": [{"key": "某大学", "count": 10}],
  "monthly_trend": [{"month": "2026-01", "count": 5}],
  "downloads": {"latest": [{"source": "huggingface", "downloads": 123}]},
  "paper": {"citing_papers": 12, "citing_citations": 40, "seed_citations": 33},
  "github": {"repo": "owner/name", "stars": 100, "forks": 10, "open_issues": 3}
}
```

### GET /api/v1/stats/downloads?days=30

```json
{
  "latest": [{"source": "huggingface", "downloads": 123}],
  "trend": {"days": 30, "series": {"huggingface": [{"date": "2026-01-01", "downloads": 100}]}}
}
```

趋势口径：每源每日取最后一条快照，同仓库多平台分别汇总。

### GET /api/v1/download-sources

渠道列表：配置中的 `repos` + 历史快照仓库，含 `url` / `latest_downloads` / `latest_fetched_at`。

### GET /api/v1/downloads/metrics?page=1&page_size=20&source=huggingface

管理员。原始快照。

## 论文引用

### GET /api/v1/papers?page=1&page_size=20&year=2025&q=robot

引用种子论文的论文列表，按年份、被引降序。

### GET /api/v1/papers/stats

```json
{
  "citing_papers": 12,
  "citing_citations": 40,
  "seed": {"title": "RoboCOIN ...", "url": "https://arxiv.org/abs/2511.17441", "citation_count": 33},
  "by_year": [{"year": 2025, "count": 8}],
  "top_venues": [{"venue": "ICRA", "count": 3}],
  "top_cited": [{"title": "...", "citation_count": 9, "url": "..."}],
  "growth_by_year": [{"year": 2025, "papers": 8}],
  "snapshots": [{"date": "2026-01-01", "seed_citations": 33,
                 "citing_papers": 12, "citing_citations": 40}]
}
```

### GET /api/v1/papers/insights

来自 MinerU 全文解析 + 大模型抽取（`paper_insights` 表）：数据用途分布、具体使用方式、他人评价（带情感）、技术关键词。未配置 `paper.insights` 时返回空结构。

```json
{
  "analyzed": 12,
  "roles": [{"role": "training_data", "count": 6}],
  "keywords": [{"keyword": "vla", "count": 8}],
  "usages": [{"title": "...", "arxiv_id": "2601.00001", "year": 2026,
              "url": "https://arxiv.org/abs/2601.00001",
              "usage": "一句话概括论文具体如何使用本项目"}],
  "comments": [{"title": "...", "text": "论文评价原文", "sentiment": "positive"}],
  "sentiments": {"positive": 3, "negative": 1, "neutral": 2}
}
```

- `role`：`training_data` / `base_data` / `finetune_data` / `benchmark` / `comparison_baseline` / `related_work` / `concept_reference` / `extension` / `other`
- `comments[].sentiment`：`positive` / `neutral` / `negative`

## GitHub

### GET /api/v1/github

仓库指标 + open issues（issues 缓存 30 分钟，失败沿用旧缓存）。

```json
{
  "enabled": true, "repo": "owner/name", "stars": 100, "forks": 10,
  "open_issues": 3, "description": "...", "language": "Python",
  "topics": ["robotics"], "html_url": "https://github.com/owner/name",
  "issues": [{"number": 1, "title": "...", "user": "dev",
              "labels": ["bug"], "created_at": "2026-01-01T00:00:00Z"}],
  "snapshots": [{"date": "2026-01-01", "stars": 100, "forks": 10, "open_issues": 3}]
}
```

### GET /api/v1/github/issues

仅返回 issue 列表 `{repo, items}`。

## 面板

### GET /api/v1/dashboard?days=30

面板全量数据。`site.dashboard_auth: true` 时需要管理员令牌。

包含 `site` / `overview` / `downloads` / `registration_trend` / `by_country` /
`country_names` / `org_tree` / `papers` / `github` / `features` / `computed_at`。

### POST /api/v1/admin/sync

管理员。后台触发一轮采集，立即返回 `{"started": true}`；已有任务运行时返回 `false`。

## 数据页面

| 路径 | 说明 |
|------|------|
| `/` | 入口页 |
| `/submit` | 使用登记表单 |
| `/dashboard` | 统计面板 |
| `/docs` | Swagger |
| `/redoc` | ReDoc |
