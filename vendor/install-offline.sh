#!/bin/bash
# 离线安装 uv + CRG + logscope-triage（无外网）
# 用法：bash vendor/install-offline.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WHEELS="$SCRIPT_DIR/wheels"
UV_BIN="$SCRIPT_DIR/uv"

echo "=== 1. 装 uv ==="
if ! command -v uv &>/dev/null; then
  mkdir -p ~/.local/bin
  cp "$UV_BIN" ~/.local/bin/uv
  chmod +x ~/.local/bin/uv
  echo "uv 已装到 ~/.local/bin/uv"
else
  echo "uv 已在 PATH"
fi
export PATH="$HOME/.local/bin:$PATH"

echo "=== 2. 装 CRG (code-review-graph) ==="
if ! command -v code-review-graph &>/dev/null; then
  uv tool install code-review-graph --no-index --find-links "$WHEELS"
  echo "code-review-graph 已装"
else
  echo "code-review-graph 已在 PATH"
fi

echo "=== 3. 装 logscope-triage ==="
if ! command -v logscope-triage &>/dev/null; then
  cd "$PROJECT_ROOT/tools"
  uv tool install . --no-index --find-links "$WHEELS"
  cd "$PROJECT_ROOT"
  echo "logscope-triage 已装"
else
  echo "logscope-triage 已在 PATH"
fi

echo "=== 4. 验证 ==="
uv --version
code-review-graph --version
logscope-triage --help | head -1
echo "=== 全部就绪 ==="
