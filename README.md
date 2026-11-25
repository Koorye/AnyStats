# AnyStats

适用于任意开源项目 / 数据集 / 论文的**通用数据统计服务**：一个 `config.yaml` + 一条 `./start.sh`，即可得到
使用登记表单、公开统计面板、每日自动采集（HuggingFace / ModelScope 下载量、论文引用、GitHub 仓库指标）。

- **零改造复用**：项目名、组织、论文、GitHub 仓库全部在 `config.yaml` 中配置，不写死任何项目
- **一键启动**：自动创建虚拟环境、安装依赖、启动 Web 与内置每日采集线程，无需 cron / tmux / systemd
- **手工登记驱动的人群统计**：世界地图、国家分布、登记趋势、单位分布全部来自 `/submit` 表单，不做访问 IP 采集
- **按需启用数据源**：没配置的源自动跳过，面板对应板块自动隐藏
- **本地可视化**：Plotly 随包提供，无 CDN / 外网依赖；SQLite 单文件，备份即拷贝

## 安装与启动

AnyStats 不是 pip 包：**安装 = 获取代码 + 安装 Python 依赖**。下面三种方式任选其一。

### 环境要求

| 依赖 | 要求 | 说明 |
|---|---|---|
| 操作系统 | Linux / macOS / WSL2 | `start.sh` 是 bash 脚本；Windows 原生请用「方式二」 |
| Python | 3.10 及以上（含 venv） | 已在 3.14 验证；Docker 镜像基于 3.12；Debian/Ubuntu 可能需额外安装 `python3-venv` |
| 网络 | 能访问 PyPI 与所用数据源 | 国内网络建议给 pip 配镜像（见下） |
| Docker | Docker Engine + Compose v2（可选） | 仅「方式三」需要 |

不需要 Node.js、Redis 或外部数据库；数据默认存放在单文件 SQLite `data/anystats.db`。

### 方式一：一键脚本（推荐）

```bash
git clone https://github.com/Koorye/AnyStats.git
cd AnyStats
cp config.example.yaml config.yaml   # 首次创建本地配置（config.yaml 已 gitignore）
# 编辑 config.yaml：至少改 site.admin_token 与 sources.*
./start.sh
```

`start.sh` 发现缺少 `config.yaml` 时也会自动从模板复制一份。首次运行会创建 `.venv/` 并按 `requirements.txt` 安装依赖（约 1–3 分钟），随后后台启动 Web 与内置采集线程；看到 `✅ AnyStats 已启动` 即安装完成。不配数据源也能正常启动，只是面板没有对应数据。

国内网络下载依赖慢或超时，可指定 PyPI 镜像：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple ./start.sh
```

其他系统差异：

```bash
chmod +x start.sh stop.sh          # 从 zip 解压后丢失执行权限时
sudo apt install python3-venv      # Debian/Ubuntu 报 ensurepip is not available 时
PYTHON=python3.12 ./start.sh       # 机器上有多个 Python，指定用哪个
```

### 方式二：手动安装（自己接管进程）

不使用 `start.sh`、想交给自己的进程管理器时：

```bash
cp config.example.yaml config.yaml   # 本地配置（含令牌，已 gitignore）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Windows（PowerShell）没有 bash 脚本，可走同样步骤（未做完整测试，生产建议 Linux 或 Docker）：

```powershell
Copy-Item config.example.yaml config.yaml
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
```

### 方式三：Docker

```bash
cp config.example.yaml config.yaml   # 含令牌，已从镜像构建上下文排除
docker compose up -d --build         # 端口 8100，挂载 ./config.yaml（只读）与 ./data
```

- `./config.yaml` 必须存在；改完配置用 `docker compose restart` 生效
- 数据库与运行数据持久化在 `./data`；容器以 root 运行，宿主机上 `data/` 新文件的属主为 root
- `config.yaml` 含令牌，已被 `.gitignore` 和 `.dockerignore` 排除，不会提交也不会打进镜像；容器通过只读挂载读取它
- 日志：`docker compose logs -f`；停止：`docker compose down`

### 启动后

| 页面 | 地址 |
|------|------|
| 统计面板 | http://127.0.0.1:8100/dashboard |
| 使用登记表单 | http://127.0.0.1:8100/submit |
| API 文档（Swagger） | http://127.0.0.1:8100/docs |
| 健康检查 | http://127.0.0.1:8100/healthz |

常用命令：

```bash
./start.sh --foreground      # 前台运行（Ctrl-C 退出，便于调试）
./start.sh --port 9000       # 临时改端口（不改 config.yaml）
./stop.sh                    # 停止后台进程
./stop.sh && ./start.sh      # 修改 config.yaml 后重启生效
tail -f .run/anystats.log    # 查看日志（仅后台模式）
```

服务默认监听 `0.0.0.0:8100`，同一局域网可直接访问；公网部署请先改掉 `admin_token` 并置于 HTTPS 反向代理之后（见「部署建议」）。

### 安装校验

```bash
curl http://127.0.0.1:8100/healthz
# {"status":"ok","app":"AnyStats","version":"1.0.0"}
```

数据源采集失败（未配 token、镜像/网络不通、429 限流等）**不影响安装**：只在日志中报错，对应面板板块隐藏或留空。可访问 `/api/v1/meta` 查看各数据源是否生效（`sources.*.active`）。

### 安装常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `python3: command not found` | 没装 Python 或不在 PATH | 安装 Python 3.10+；或 `PYTHON=/path/to/python3 ./start.sh` |
| `ensurepip is not available` / `No module named venv` | 缺少 venv 组件 | Debian/Ubuntu：`sudo apt install python3-venv`；其他发行版安装对应的 python venv/pip 组件 |
| `Permission denied: ./start.sh` | 解压后丢了执行位 | `chmod +x start.sh stop.sh`，或 `bash start.sh` |
| pip 下载超时 / SSL 错误 | PyPI 访问受限 | 设 `PIP_INDEX_URL=<镜像地址>/simple` 后重跑 |
| `启动超时，请查看日志` | 端口被占、依赖缺失或导入失败 | `tail -n 80 .run/anystats.log`，常见 `Address already in use` / `ModuleNotFoundError` |
| 启动即报 YAML / 配置错误 | `config.yaml` 缩进或取值不合法 | 按「配置说明」检查；`sync.daily_at` 需 `HH:MM` |
| 依赖装坏、想重装 | 半途中断留下残缺 `.venv` | `rm -rf .venv && ./start.sh` |
| 端口 8100 被占用 | 已有其他服务 | `./start.sh --port 9000`，或改 `server.port` |
| 页面打不开、进程不在 | 后台进程被终端/系统回收 | 重新 `./start.sh`；长期运行用 systemd（见「部署建议」） |
| HuggingFace 采集报 `ConnectionError` / `SSLError` | 官方 API 不可达（镜像只代理文件下载） | 设 `use_proxy: true`，或换可访问的 `endpoint`；见「关于 HuggingFace 镜像」 |
| 启动日志提示 `admin_token 仍为默认值` | 未改默认管理员令牌 | 改 `site.admin_token` 或设 `ANYSTATS_ADMIN_TOKEN` |
| `Semantic Scholar 持续限流` / 429 | 共享 IP 池或 key 配额被限流 | 采集会自动重试 4 次（约 50 秒）；失败时保留上次数据，可稍后手动触发 `POST /api/v1/admin/sync` |

## 配置说明（config.example.yaml → config.yaml）

仓库只跟踪模板 `config.example.yaml`。`config.yaml` 是本地文件（含令牌），已被 `.gitignore` 忽略，不会提交。首次使用先复制：

```bash
cp config.example.yaml config.yaml
```

改完配置重启生效；后续 `git pull` 不会覆盖已有的 `config.yaml`。

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
    endpoint: "https://hf-mirror.com"   # 镜像只加速文件下载，/api 会回源官方
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
    s2_api_key: ""                 # 也叫 S2_API_KEY；真实令牌写 config.yaml（不入库）
  github:
    enabled: true
    repo: ""                       # owner/name
    token: ""                      # 也叫 GITHUB_TOKEN（可选，提高限速）
    include_prs: false
    issue_limit: 50
```

> **关于 HuggingFace 镜像**：`hf-mirror.com` 只加速文件下载，`/api/*` 元数据请求会 308 重定向回 `huggingface.co`。因此采集数据集列表仍要求官方 API 可达；服务器访问不了官方 API 时，请设置 `use_proxy: true`（走代理），或把 `endpoint` 换成可用的镜像 / 网关地址。

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
- **下载量**（`download_metrics`）：每次采集每个仓库写一条快照；面板按"每源每日最后一条快照"聚合，同日多次采集不重复计数。整轮采集单事务写入，中途失败不会留下半份数据。
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

所有变量都可以覆盖 `config.yaml` 中的对应配置，适合 Docker / 多实例 / systemd 部署。优先级：**进程环境变量 > config.yaml**。

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
rm -rf .venv .run data/anystats.db* config.yaml   # 清掉依赖、运行数据与旧配置
cp config.example.yaml config.yaml                # 从干净模板重建本地配置
# 编辑 config.yaml 的 site.* 与 sources.*
./start.sh
```

## 测试

```bash
.venv/bin/python -m pytest -q      # 或使用已装好依赖的 python
```

测试使用 `tests/fixtures/config.test.yaml` 与 pytest 临时目录，不会写入正式库 `data/anystats.db`。

## 目录结构

```
AnyStats/
├── config.example.yaml    # 配置模板（入库）
├── config.yaml            # 本地配置（gitignore，可写令牌）
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

### 用 systemd 托管

`start.sh` 适合开发与小规模部署，不会开机自启。需要长期运行时建议交给 systemd（依赖按「方式二」先装好）：

```ini
# /etc/systemd/system/anystats.service
[Unit]
Description=AnyStats
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/AnyStats
ExecStart=/opt/AnyStats/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now anystats
journalctl -u anystats -f
```

把 `User` / `WorkingDirectory` 换成实际用户与仓库路径，并确保该用户对代码目录和 `data/` 有读写权限；启用 systemd 前先 `./stop.sh`，避免同一端口和数据库跑两份进程。
