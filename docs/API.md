# AnyStats API

Base URL：`/api/v1`（页面为 `/`、`/submit`、`/dashboard`、`/docs`）。

## 统一约定

**成功响应**

```json
{"code": 0, "message": "ok", "data": ...}
```

**失败响应**

```json
{"code": 404, "message": "论文不存在", "data": null}
```

参数校验失败：

```json
{"code": 422, "message": "参数校验失败",
 "data": {"errors": [{"loc": ["body", "name"], "msg": "不能为空白"}]}}
```

**分页**

所有列表接口统一返回：

```json
{"items": [...], "total": 100, "page": 1, "page_size": 20}
```

**缓存**：下载列表/总览/趋势、全站统计和面板聚合默认 30 秒进程内缓存；数据每天更新一次，前端轮询建议 30–60 秒。

**鉴权**

管理员接口使用请求头 `X-Admin-Token: <site.admin_token>`；未配置令牌的公开接口不需要。
时间均为 UTC ISO8601（如 `2026-11-27T05:25:03Z`）。

---

## 系统

### GET /healthz

```json
{"status": "ok", "app": "AnyStats", "version": "1.0.0"}
```

### GET /api/v1/meta

站点信息、数据源启用状态、目标配置与采集计划（不含任何令牌）。

```json
{
  "title": "AnyStats",
  "subtitle": "开源项目数据统计",
  "sources": {"huggingface": {"label": "HuggingFace", "active": true}},
  "targets": {"huggingface": "RoboCOIN", "paper": "2511.17441"},
  "sync": {"enabled": true, "daily_at": "03:00", "run_on_start": true}
}
```

### GET /api/v1/sync/status

各数据源配置状态与最近采集进度。

```json
{
  "scheduler": {"enabled": true, "daily_at": "03:00", "run_on_start": true},
  "sources": {
    "huggingface": {"label": "HuggingFace", "active": true,
                    "repos": 819, "downloads": 6827213,
                    "latest_fetched_at": "2026-11-27T05:25:03Z"},
    "paper": {"label": "论文引用", "active": true, "arxiv_id": "2511.17441",
              "papers": 131, "latest_snapshot": "2026-11-25"},
    "github": {"label": "GitHub", "active": true, "repo": "owner/name",
               "stars": 217, "latest_fetched_at": "2026-11-27T05:25:11Z"}
  }
}
```

### POST /api/v1/sync

管理员。后台触发一轮采集，立即返回 `{"started": true}`；已有任务时返回 `false`。

### GET /api/v1/dashboard

面板全量数据；`site.dashboard_auth: true` 时需要管理员令牌。

---

## 统计

### GET /api/v1/stats

全站总览：登记、下载、论文、洞察、GitHub。

### GET /api/v1/stats/submissions

登记聚合：总数、去重主体/单位、国家、机构类型、版本、Top 单位、月度趋势。

### GET /api/v1/stats/downloads?days=30

```json
{
  "summary": {"repos": 1639, "downloads": 98981434, "updated_at": "..."},
  "latest": [{"source": "huggingface", "downloads": 6874579}],
  "trend": {"days": 30, "series": {"huggingface": [{"date": "2026-11-27", "downloads": 6874579}]}}
}
```

### GET /api/v1/stats/papers

引用统计 + `insights` 全文洞察汇总（数据用途/评价/关键词）。

### GET /api/v1/stats/github

仓库最新指标、issues、每日快照。

---

## 登记

### POST /api/v1/submissions

公开；同 IP 每小时限频，`website` 为蜜罐字段（非空返回 400）。

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

### GET /api/v1/submissions

管理员；`page` / `page_size` / `country` / `affiliation_type` / `date_from` / `date_to`。

### GET /api/v1/submissions/stats

公开；登记聚合统计。

### GET /api/v1/submissions/countries

公开；按国家/地区去重主体与单位，含 ISO3。

### GET /api/v1/submissions/organizations

公开；机构类型 → 单位两级树。

### GET /api/v1/submissions/export

管理员；CSV（UTF-8 BOM），支持与列表相同的过滤参数。

### GET /api/v1/submissions/{id}

管理员；单条登记详情。

---

## 下载量

### GET /api/v1/downloads

按仓库获取最新下载量，按下载量倒序。

| 参数 | 默认 | 说明 |
|---|---|---|
| `source` | 空 | `huggingface` / `modelscope` |
| `q` | 空 | repo_id 关键字 |
| `repo_id` | 空 | 精确仓库 id |
| `page` / `page_size` | 1 / 50 | 分页，最大 200 |

```json
{
  "items": [{"source": "huggingface", "repo_id": "org/demo",
             "downloads": 1234, "likes": 12,
             "url": "https://huggingface.co/datasets/org/demo",
             "fetched_at": "2026-11-27T05:25:03Z"}],
  "total": 2, "total_downloads": 1300, "page": 1, "page_size": 50,
  "source_totals": [{"source": "huggingface", "repos": 2, "downloads": 1300,
                     "latest_fetched_at": "2026-11-27T05:25:03Z"}],
  "updated_at": "2026-11-27T05:25:03Z"
}
```

### GET /api/v1/downloads/sources

各渠道汇总：启用状态、组织、仓库数、配置仓库数、累计下载、最近采集时间。

### GET /api/v1/downloads/summary

全站下载总览（渠道、仓库数、下载量、更新时间）。

### GET /api/v1/downloads/trend?days=30

各渠道每日累计趋势 + 最新值。

### GET /api/v1/downloads/{source}/{repo_id}

单仓库详情：最新快照 + 每日历史（`days` 默认 30）。

```json
{
  "source": "huggingface", "repo_id": "org/demo",
  "latest": {"downloads": 1234, "likes": 12, "fetched_at": "...",
             "url": "https://huggingface.co/datasets/org/demo"},
  "history": [{"date": "2026-11-26", "downloads": 1200, "likes": 12}],
  "days": 30
}
```

### GET /api/v1/downloads/metrics

管理员；原始快照分页，支持 `source` 过滤。

### GET /api/v1/downloads/metrics/{id}

管理员；单条原始快照。

---

## 论文

### GET /api/v1/papers

公开；引用论文列表。

| 参数 | 说明 |
|---|---|
| `page` / `page_size` | 分页 |
| `year` | 发表年份 |
| `q` | 标题/作者/期刊关键词 |
| `role` | 用途角色：`training_data` / `base_data` / `benchmark` / `finetune_data` 等 |
| `min_citations` | 最小被引数 |

列表项包含 `role`、`usage`、`keywords`、`comments`、`comments_count`、`url`。

### GET /api/v1/papers/{id}

单篇详情：元数据 + 全文分析（role / usage / keywords / comments / md_path / analyzed_at / model）。

### GET /api/v1/papers/stats

引用统计：总数、累计被引、种子的被引、年份、期刊、Top 被引、快照、`insights` 汇总。

### GET /api/v1/papers/insights

数据用途 / 他人评价 / 关键词汇总：

```json
{
  "analyzed": 131,
  "roles": [{"role": "training_data", "count": 64}],
  "keywords": [{"keyword": "vla", "count": 23}],
  "usages": [{"title": "...", "url": "...", "usage": "..."}],
  "comments": [{"title": "...", "text": "...", "sentiment": "positive"}],
  "sentiments": {"positive": 25, "negative": 8, "neutral": 9}
}
```

### GET /api/v1/papers/snapshots

种子论文每日引用快照 + 种子论文元信息。

---

## GitHub

### GET /api/v1/github

仓库指标 + open issues + 每日快照。

### GET /api/v1/github/repo

仓库最新指标（stars / forks / watchers / open issues / topics 等）。

### GET /api/v1/github/issues

open issues 列表；`limit` 可选，默认取配置的 `issue_limit`。

### GET /api/v1/github/snapshots

每日 stars / forks / open issues 快照。

---

## 兼容别名

以下旧 URL 仍可用，但**保留旧的响应结构**且不会出现在 Swagger 中，建议新代码使用规范 URL：

| 旧 URL | 规范 URL |
|---|---|
| `/api/v1/stats/summary` | `/api/v1/stats` |
| `/api/v1/stats/export` | `/api/v1/submissions/export` |
| `/api/v1/download-sources` | `/api/v1/downloads/sources` |
| `/api/v1/downloads/info` | `/api/v1/downloads` |
| `/api/v1/admin/sync` | `/api/v1/sync` |

## 页面

| 路径 | 说明 |
|------|------|
| `/` | 入口页 |
| `/submit` | 使用登记表单 |
| `/dashboard` | 统计面板 |
| `/docs` | Swagger |
| `/redoc` | ReDoc |
