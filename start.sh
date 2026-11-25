#!/usr/bin/env bash
# AnyStats 一键启动：自动建虚拟环境、装依赖、启动 Web（含内置每日采集）
# 用法：./start.sh [--foreground] [--port 8100]
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"
RUN_DIR="$ROOT/.run"
LOG_FILE="$RUN_DIR/anystats.log"
PID_FILE="$RUN_DIR/anystats.pid"
FOREGROUND=0
PORT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --foreground|-f) FOREGROUND=1; shift ;;
    --port) PORT_OVERRIDE="$2"; shift 2 ;;
    -h|--help) echo "用法：./start.sh [--foreground] [--port 8100]"; exit 0 ;;
    *) echo "未知参数：$1"; exit 1 ;;
  esac
done

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 $PYTHON，请先安装 Python 3.10+"
  exit 1
fi

if [[ ! -f "$ROOT/config.yaml" ]]; then
  echo "缺少 config.yaml，请先复制并按需修改配置"
  exit 1
fi

# 1) 虚拟环境 + 依赖（requirements 未变化时跳过安装）
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "==> 创建虚拟环境 $VENV"
  "$PYTHON" -m venv "$VENV"
fi
REQ_HASH="$("$PYTHON" -c "import hashlib;print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())")"
STAMP="$VENV/.requirements.sha256"
if [[ ! -f "$STAMP" || "$(cat "$STAMP")" != "$REQ_HASH" ]]; then
  echo "==> 安装依赖"
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -q -r requirements.txt
  echo "$REQ_HASH" > "$STAMP"
fi

# 2) 读取监听地址
HOST="$("$VENV/bin/python" -c "from app.config import settings;print(settings.HOST)")"
PORT="${PORT_OVERRIDE:-$("$VENV/bin/python" -c "from app.config import settings;print(settings.PORT)")}"
URL="http://127.0.0.1:${PORT}"

# 3) 已在运行则直接提示
mkdir -p "$RUN_DIR" "$ROOT/data"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "AnyStats 已在运行（PID $(cat "$PID_FILE")）：$URL"
  exit 0
fi

if [[ "$FOREGROUND" == "1" ]]; then
  echo "==> 前台启动：$URL （Ctrl-C 退出）"
  exec "$VENV/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
fi

# 4) 后台启动 + 健康检查
echo "==> 后台启动 uvicorn（日志：$LOG_FILE）"
nohup "$VENV/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT" \
  >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

for _ in $(seq 1 30); do
  if "$VENV/bin/python" -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1] + '/healthz', timeout=2).read()" "$URL" >/dev/null 2>&1; then
    echo ""
    echo "✅ AnyStats 已启动"
    echo "   面板：$URL/dashboard"
    echo "   登记：$URL/submit"
    echo "   文档：$URL/docs"
    echo "   日志：$LOG_FILE"
    echo "   停止：./stop.sh"
    exit 0
  fi
  sleep 1
done

echo "启动超时，请查看日志：tail -n 80 $LOG_FILE"
exit 1
