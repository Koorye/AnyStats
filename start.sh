#!/usr/bin/env bash
# AnyStats 一键启动（前台）：自动创建虚拟环境、安装依赖、启动 Web 与内置采集线程。
# 用法：./start.sh [--port 8100]
# 停止：Ctrl-C（tmux / systemd 中由各自方式管理）
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"
PORT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT_OVERRIDE="$2"; shift 2 ;;
    --foreground|-f) shift ;;  # 兼容旧参数；现在始终前台运行
    -h|--help) echo "用法：./start.sh [--port 8100]"; exit 0 ;;
    *) echo "未知参数：$1"; exit 1 ;;
  esac
done

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 $PYTHON，请先安装 Python 3.10+"
  exit 1
fi

if [[ ! -f "$ROOT/config.yaml" ]]; then
  if [[ -f "$ROOT/config.example.yaml" ]]; then
    cp "$ROOT/config.example.yaml" "$ROOT/config.yaml"
    echo "==> 未找到 config.yaml，已从 config.example.yaml 生成，请按需修改后重启"
  else
    echo "缺少 config.yaml 与 config.example.yaml，请从仓库重新获取配置模板"
    exit 1
  fi
fi

# 虚拟环境 + 依赖（requirements 未变化时跳过安装）
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

mkdir -p "$ROOT/data"

# 读取监听地址
HOST="$("$VENV/bin/python" -c "from app.config import settings;print(settings.HOST)")"
PORT="${PORT_OVERRIDE:-$("$VENV/bin/python" -c "from app.config import settings;print(settings.PORT)")}"

echo "==> AnyStats 启动：http://127.0.0.1:${PORT}"
echo "    面板：${PORT}/dashboard  表单：/submit  文档：/docs"
echo "    停止：Ctrl-C（tmux 中使用 tmux kill-session）"
exec "$VENV/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
