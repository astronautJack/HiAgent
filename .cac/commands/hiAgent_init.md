---
description: 显示 HiAgent 安装步骤（用户手动到终端跑）。
---
向用户显示以下 HiAgent 安装步骤，让用户复制到终端手动执行：

---

**HiAgent 安装步骤**（在终端手动跑）：

```bash
# 1. 拿到本仓
git clone <本仓地址> HiAgent && cd HiAgent

# 2. 装 uv（CRG + logscope-triage 用）
curl -LsSf https://astral.sh/install.sh | sh

# 3. 装 CRG（代码图）
uv tool install code-review-graph

# 4. 装 logscope-triage CLI（本仓 Python CLI）
cd tools && uv tool install . && cd ..

# 5. 确保 ~/.local/bin 在 PATH
export PATH="$HOME/.local/bin:$PATH"   # 永久：写进 ~/.bashrc

# 6. 验证
code-review-graph --version            # 应出版本号
logscope-triage --help                 # 应有 --json / --log-format

# 7. 启动 CodeAgent
codeagent
```

装完重启 CodeAgent 让 `settings.json` 的 CRG MCP 生效。改完 `.cac/` 或 `settings.json` 后也要重启。
