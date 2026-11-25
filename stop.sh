#!/usr/bin/env bash
# 停止 AnyStats（由 start.sh 后台启动的进程）
set -euo pipefail
cd "$(dirname "$0")"
PID_FILE=".run/anystats.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "未找到 PID 文件，AnyStats 可能未在后台运行"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in $(seq 1 15); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$PID" 2>/dev/null; then
    echo "进程未退出，强制结束"
    kill -9 "$PID" 2>/dev/null || true
  fi
  echo "AnyStats 已停止（PID $PID）"
else
  echo "进程 $PID 不存在，清理 PID 文件"
fi
rm -f "$PID_FILE"
