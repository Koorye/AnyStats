# AnyStats

适用于任意开源项目 / 数据集 / 论文的**通用数据统计服务**：一个 `config.yaml` + 一条 `./start.sh`，即可得到
使用登记表单、公开统计面板、每日自动采集（HuggingFace / ModelScope 下载量、论文引用、GitHub 仓库指标）。

- **零改造复用**：项目名、组织、论文、GitHub 仓库全部在 `config.yaml` 中配置，不写死任何项目
- **一键启动**：自动创建虚拟环境、安装依赖、启动 Web 与内置每日采集线程，无需 cron / tmux / systemd
- **手工登记驱动的人群统计**：世界地图、国家分布、登记趋势、单位分布全部来自 `/submit` 表单，不做访问 IP 采集
- **按需启用数据源**：没配置的源自动跳过，面板对应板块自动隐藏
- **本地可视化**：Plotly 随包提供，无 CDN / 外网依赖；SQLite 单文件，备份即拷贝

## 快速开始

```bash
cd AnyStats
# 1) 编辑 config.yaml（至少改 site.title / site.admin_token / sources）
# 2) 一键启动（首次会自动创建 .venv 并安装依赖）
./start.sh
```

启动后：

| 页面 | 地址 |
|------|------|
| 统计面板 | http://127.0.0.1:8100/dashboard |
| 使用登记表单 | http://127.0.0.1:8100/submit |
| API 文档（Swagger） | http://127.0.0.1:8100/docs |
| 健康检查 | http://127.0.0.1:8100/healthz |

常用参数：

```bash
./start.sh --foreground      # 前台运行（Ctrl-C 退出，便于调试）
./start.sh --port 9000       # 临时改端口
./stop.sh && ./start.sh      # 修改 config.yaml 后重启生效
./stop.sh                    # 停止后台进程
tail -f .run/anystats.log    # 查看日志
```

Docker 启动：

```bash
docker compose up -d --build   # 端口 8100，挂载 ./config.yaml 与 ./data
```

## 配置说明（config.yaml）

```yaml
site:
  title: "AnyStats"                # 站点名（面板 / 表单 / API 文档）
  subtitle: "开源项目数据统计"
  description: "..."               # 首页与表单说明
  project_version: "1.0.0"         # 写入每条登记，便于区分版本
  admin_token: "change-me"         # 管理员令牌（生产必改）
  footer: "Powered by AnyStats"
  dashboard_auth: false            # true=面板需管理员令牌；false=公开

server:
  host: "0.0.0.0"
  port: 8100
  cors_origins: "*"                # 生产建议收敛为具体域名
  trust_proxy: false               # 反向代理后置 true（仅用于提交限频）

database:
  path: "data/anystats.db"

submit:
  title: "使用登记"
  description: "请在使用本项目前登记以下信息……"
  license_text: "我已阅读并同意本项目使用条款"
  org_example: "如：某某大学机器人实验室"

sync:
  enabled: true                    # 内置每日采集线程（随 Web 启动）
  daily_at: "03:00"                # 服务器本地时区
  run_on_start: true               # 启动时先采一轮

sources:
  huggingface:
    enabled: true
    org: ""                        # 组织名，自动枚举全部数据集
    repos: []                      # 额外仓库 ["org/dataset"]
    endpoint: "https://hf-mirror.com"   # 国内服务器默认镜像；可改官方
    use_proxy: false               # 镜像一般必须直连（代理链路易 TLS EOF）
    token: ""                      # 也叫 HF_TOKEN 环境变量；只发给官方端点
  modelscope:
    enabled: true
    org: ""
    repos: []
    token: ""                      # 也叫 MODELSCOPE_API_TOKEN
  paper:
    enabled: true
    arxiv_id: ""                   # 种子论文 arXiv ID，统计引用它的论文
    s2_api_key: ""                 # 也叫 S2_API_KEY（可选）
  github:
    enabled: true
    repo: ""                       # owner/name
    token: ""                      # 也叫 GITHUB_TOKEN（可选，提高限速）
    include_prs: false
    issue_limit: 50
```

### 配置示例

统计 `FlagOpen/RoboCOIN`：

```yaml
sources:
  huggingface: {enabled: true, org: "RoboCOIN"}
  modelscope:  {enabled: true, org: "RoboCOIN"}
  paper:       {enabled: true, arxiv_id: "2511.17441"}
  github:      {enabled: true, repo: "FlagOpen/RoboCOIN"}
```

只做下载量统计：把 `paper.enabled` / `github.enabled` 置 `false` 即可，面板会自动隐藏对应板块。

## 数据来源与统计口径

- **手工登记**（`submissions`）：姓名、国家、机构类型、单位、补充说明、邮箱。面板的去重主体数、世界地图、国家分布、月度趋势、单位分布全部来自这里。
  - 主体去重：优先邮箱（大小写不敏感）；无邮箱按 `姓名|国家|规范化单位`
  - 单位去重：`LOWER+TRIM` 合并大小写差异
- **下载量**（`download_metrics`）：每日每仓库一条快照；面板按"每源每日最后一条快照"聚合，同日多次采集不重复计数。整轮采集单事务写入，中途失败不会留下半份数据。
- **论文引用**（`papers` / `paper_snapshots`）：Semantic Scholar 拉取引用种子 arXiv 论文的全部论文，记录引用论文数、种子论文被引数、引用论文的年份 / 期刊分布与每日快照。
- **GitHub**（`github_repo` / `github_snapshots` / `github_issues`）：stars / forks / open issues 每日快照；issues 列表缓存 30 分钟。

> 本服务**不记录访问 IP**：没有任何访问埋点、IP 归属地解析或访客统计。提交接口仅在内存中按连接 IP 做限频（不落库），可在 `TRUST_PROXY` 配置下从 `X-Forwarded-For` 取真实来源。

## API

完整说明见 [docs/API.md](docs/API.md)，交互式文档 `/docs`。成功响应统一为
`{"code": 0, "message": "ok", "data": ...}`；管理员接口使用请求头 `X-Admin-Token`。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/healthz` | 公开 | 健康检查 |
| GET | `/api/v1/meta` | 公开 | 站点信息与数据源状态（不含令牌） |
| POST | `/api/v1/submissions` | 公开（限频） | 提交使用登记（`website` 为蜜罐字段） |
| GET | `/api/v1/submissions` | 管理员 | 登记明细（分页 + 过滤） |
| GET | `/api/v1/submissions/{id}` | 管理员 | 登记详情 |
| GET | `/api/v1/stats/summary` | 公开 | 聚合统计（主体 / 国家 / 下载 / 论文 / GitHub） |
| GET | `/api/v1/stats/downloads` | 公开 | 各源最新下载量与趋势 |
| GET | `/api/v1/stats/export` | 管理员 | CSV 导出（带 BOM） |
| GET | `/api/v1/download-sources` | 公开 | 下载渠道列表与最新值 |
| GET | `/api/v1/downloads/metrics` | 管理员 | 原始下载快照 |
| GET | `/api/v1/papers` | 公开 | 引用论文列表（year/q 过滤） |
| GET | `/api/v1/papers/stats` | 公开 | 引用统计（年份 / 期刊 / Top 被引 / 快照） |
| GET | `/api/v1/github` | 公开 | 仓库指标 + open issues |
| GET | `/api/v1/dashboard` | 见配置 | 面板全量数据 |
| POST | `/api/v1/admin/sync` | 管理员 | 后台触发一轮采集 |

## 手动采集 / 定时任务

服务内置每日采集（`sync` 配置），一般无需额外配置。若希望用 cron / systemd timer：

```bash
# 关掉内置采集：config.yaml -> sync.enabled: false
.venv/bin/python scripts/sync.py                      # 全部数据源
.venv/bin/python scripts/sync.py --source paper       # 只采论文引用
.venv/bin/python scripts/sync.py --source huggingface --source modelscope
```

crontab 示例（每天 03:00）：

```cron
0 3 * * * cd /path/to/AnyStats && .venv/bin/python scripts/sync.py >> .run/sync.log 2>&1
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `ANYSTATS_CONFIG` | 配置文件路径（默认 `<项目根>/config.yaml`） |
| `ANYSTATS_TITLE` | 覆盖 `site.title` |
| `ANYSTATS_ADMIN_TOKEN` | 覆盖 `site.admin_token` |
| `ANYSTATS_DB_PATH` | 覆盖 `database.path` |
| `ANYSTATS_HOST` / `ANYSTATS_PORT` | 覆盖监听地址 |
| `ANYSTATS_SYNC_ENABLED` / `ANYSTATS_SYNC_AT` / `ANYSTATS_SYNC_ON_START` | 覆盖定时采集 |
| `ANYSTATS_DASHBOARD_AUTH` | 覆盖面板鉴权开关 |
| `ANYSTATS_CORS_ORIGINS` / `ANYSTATS_TRUST_PROXY` / `ANYSTATS_RATE_LIMIT_PER_HOUR` | 覆盖服务参数 |
| `HF_TOKEN` / `HF_ENDPOINT` / `HF_USE_PROXY` | HuggingFace 令牌 / 端点 / 代理 |
| `MODELSCOPE_API_TOKEN` | ModelScope 令牌 |
| `S2_API_KEY` | Semantic Scholar 令牌（可选） |
| `GITHUB_TOKEN` | GitHub 令牌（可选） |
| `ANYSTATS_LOG_LEVEL` | 日志级别，默认 `INFO` |

## 适配到新项目

```bash
cp -r AnyStats MyProjectStats && cd MyProjectStats
rm -rf .venv .run data/anystats.db*     # 清掉示例运行数据
# 若目录由旧项目改造而来，data/ 下可能还留有旧数据库/日志，按需一并清理
# 编辑 config.yaml 的 site.* 与 sources.*
./start.sh
```

## 测试

```bash
.venv/bin/python -m pytest -q      # 或使用已装好依赖的 python
```

测试使用独立的测试配置与临时 SQLite，不会污染 `data/`。

## 目录结构

```
AnyStats/
├── config.yaml            # 唯一配置入口
├── start.sh / stop.sh     # 一键启动 / 停止
├── scripts/sync.py        # 手动采集（cron 备选）
├── app/
│   ├── main.py            # FastAPI 入口（lifespan 内启动采集线程）
│   ├── config.py          # 配置加载 + 环境变量覆盖
│   ├── database.py        # SQLite 表结构
│   ├── scheduler.py       # 内置每日采集线程
│   ├── pages.py           # 首页 / 登记表单
│   ├── dashboard_page.py  # 统计面板（Plotly）
│   ├── collectors/        # huggingface / modelscope / paper / github
│   ├── crud/              # 读写与聚合
│   ├── routers/           # REST API
│   └── static/            # plotly.min.js
├── tests/
├── docs/API.md
└── data/                  # SQLite 与运行数据（gitignore）
```

## 部署建议

- 面板与表单建议放在 HTTPS 反向代理（nginx / caddy）之后，并设置 `trust_proxy: true`
- SQLite 单文件：备份 `data/` 目录即可；WAL 模式下建议连同 `-wal` / `-shm` 一起拷贝
- 生产环境修改 `admin_token`，并收紧 `cors_origins`
- 多 worker 部署时，内存限频按进程独立计数；如需严格限流请在网关层处理
- 内置采集为进程内线程；多副本部署时请只让一个副本设置 `sync.enabled: true`
- 日志默认写 `.run/anystats.log`（后台模式），长期运行建议配 logrotate 或改用 systemd/journald
