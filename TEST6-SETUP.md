# test6 — opencode /diag 内网实验搭建说明

> 本分支 = opencode 分支（`.opencode/` agents + commands，含 `subtask: false` + 编排契约）+ 本说明 + test6 崩溃日志 + 隔离配置。  
> 目的：在内网验证 opencode 能否跑通 `/diag`（日志 → 代码行定位 + 证据链 + 独立 reviewer 审）。  
> 测试 case：react-native-screens #4151（native C++ SIGSEGV，`MountingCoordinator::pullTransaction` use-after-free）。  
> 已知答案：PR [#4413](https://github.com/software-mansion/react-native-screens/pull/4413)。

---

## 1. 前置条件

### 1.1 opencode
内网已装 opencode（`opencode` 命令可用）。

### 1.2 uv + CRG（代码调用图）
```bash
curl -LsSf https://astral.sh/install.sh | sh   # 装 uv
uv tool install code-review-graph                # 装 CRG
code-review-graph --version                     # 验证
```

### 1.3 logscope-triage CLI（日志压缩）
本仓 `tools/` 目录：
```bash
cd tools && uv tool install . && cd ..
logscope-triage --help    # 应有 --json
```

### 1.4 PATH
```bash
export PATH="$HOME/.local/bin:$PATH"   # 永久：写进 ~/.bashrc
```

---

## 2. 搭建 test6 codebase

两个仓（跨仓 case）：
- `react-native` v0.86.0（框架，崩点 `MountingCoordinator.cpp`）
- `react-native-screens` 4.24.0（库，根因 `RNSScreenRemovalListener` / `NativeProxy`）

### 2.1 clone + 统一 git

```bash
mkdir -p test6/codebase
cd test6/codebase

git clone --depth 1 --branch v0.86.0 https://github.com/facebook/react-native.git
git clone --depth 1 --branch 4.24.0 https://github.com/software-mansion/react-native-screens.git

# 撤嵌套 .git（CRG 用 git ls-files 枚举源文件，嵌套 .git 会导致 0 文件）
rm -rf react-native/.git react-native-screens/.git

# 统一仓
git init && git add -A && git commit -m "unified codebase for CRG (test6)"

# 验证
git ls-files | wc -l    # 应 ~9300+
cd ../..
```

> **内网无 GitHub？** 用内网 git mirror 或离线 bundle。tag：`v0.86.0`、`4.24.0`。

### 2.2 日志

本分支已含 `test6/log/rnscreens-pullTransaction-sigsegv.log`（来自 leon-zym/plogkit#54）。

### 2.3 隔离配置

本分支已含 `test6/opencode.json`——**复制到项目根目录**覆盖原 `opencode.json`：
```bash
cp test6/opencode.json opencode.json
```

此配置：
- `external_directory: deny`（/diag 只能读项目内文件，不能读仓外答案）
- `webfetch: deny` + `websearch: deny`（禁止联网搜答案）
- `bash` 放行 `git` / `code-review-graph` / `logscope-triage`
- `mcp.crg` 挂 CRG MCP server

---

## 3. CRG 建图（可选预建）

`/diag` 第一步会调 `code-graph` agent 自动建图。但大仓（9300+ 文件）可能慢。可先手动 CLI 建好：

```bash
code-review-graph build --repo test6/codebase
# ~99 秒（全量含 flows）
code-review-graph status --repo test6/codebase
# 应显示 ~70000 nodes / ~410000 edges
```

> 预建后 `/diag` 的 CRG 门检测 fresh → 跳过建图 → 不超时。

---

## 4. 跑 /diag

### 4.1 启动 opencode

```bash
# 确保在项目根目录（.opencode/ + opencode.json 在此）
opencode
```

> opencode 加载 `.opencode/`（agents + commands）+ `opencode.json`（权限 + MCP）+ `AGENTS.md`（项目指令）。

### 4.2 执行

```
/diag test6/log/rnscreens-pullTransaction-sigsegv.log test6/codebase
```

### 4.3 预期流程

opencode 的 `/diag` 是 `.md` command（`subtask: false` + 编排契约），**主会话编排**：

1. **CRG 门**：主会话 Task 调 `code-graph` → status 判新鲜；stale 则 `code-graph` 问用户 build/update/skip（opencode 有 question 工具）→ 选 build → Bash CLI 全量建图（不走 MCP，避 RPC 超时）→ 返 `{ok}`。
2. **压日志**：主会话 Task 调 `log-parser` → `logscope-triage` → digest。
3. **取上下文**：无 wiki → 跳过。
4. **code-tracer 写报告**：主会话 Task 调 `code-tracer` → 沿 CRG `callers_of` 反向回溯 → `file:line` 根因 + 证据链 → 写 `./diag-report.md`。
5. **reviewer 独立审**：主会话 Task 调 `code-tracer-reviewer` → 重跑 CRG/grep + 重读源码 → 返 `{verdict, findings}`。
6. **loop**（最多 3 次）：`verdict=revise` → code-tracer 修订 → reviewer 复审。
7. **收尾**：报告交人审。

### 4.4 关键配置（已在本分支的 .opencode/commands/ 里）

| 配置 | 值 | 原因 |
|---|---|---|
| `subtask: false`（5 命令 frontmatter） | 显式禁 subagent 调用 | opencode 默认可能把命令跑在子会话（子会话没 Task 工具、不能 spawn subagent） |
| 编排契约（5 命令正文开头） | 「你是主会话编排者。禁止把整条 workflow 委派给单个 subagent...」 | 消除「每步用 Task 调对应 subagent」的歧义（模型可能误读为「用一次 Task 把整条跑了」→ 委派给 build 子会话 → 断链） |

### 4.5 避免的坑

| 坑 | 症状 | 修法 |
|---|---|---|
| 父目录有旧 `.opencode/` | /diag 用旧版 command（subtask:true + 5-step），主会话进子会话断链 | 删父目录的 `.opencode/`（opencode 从 cwd 向上合并 .opencode，父级旧版会盖过子级） |
| 无 `subtask: false` | /diag 可能在子会话跑（子会话没 Task 工具） | 本分支已加 `subtask: false` |
| 无编排契约 | 模型把整条 workflow 塞一次 Task 调用 → 委派给 build 子会话 → 断链 | 本分支已加编排契约 |
| CRG 建图 0 文件 | codebase 下嵌套 .git 没撤 | 执行 §2.1 的 `rm -rf .git` + `git init` |
| CRG 建图超时 | 9300+ 文件全量建图超 opencode bash 超时 | 先手动 CLI 建好（§3） |

---

## 5. 已知答案 + 验证

### PR #4413 根因

`RNSScreenRemovalListener` owned by `NativeProxy`（fbjni HybridClass）→ Java GC finalizer 在不可预测时序销毁其 C++ 半 → JS 线程仍在迭代 `mountingOverrideDelegates_` → `weak_ptr::lock()` 对已回收控制块返回 non-null → 虚分发跳进回收堆 → SIGSEGV。

### 关键验证点

| 验证项 | 期望 |
|---|---|
| 崩点 | `MountingCoordinator.cpp:71`（`pullTransaction` 定义） |
| 调用链 #05→#00 | ShadowTree::mount → UIManager → Scheduler → FabricUIManagerBinding → pullTransaction |
| vtable 解引用点 | `:103` `shouldOverridePullTransaction()`（+524 偏移经 imdrak 反汇编确证 = `ldr x8,[x8]; blr x8`） |
| 真凶 delegate | `RNSScreenRemovalListener`（归 `NativeProxy` shared_ptr 持有） |
| 根因 | Java GC finalizer 跨线程 race + `weak_ptr::lock()` 对回收控制块返回 non-null |
| 修复 | listener 改进程级单例（永不被 GC 销毁 → weak_ptr 永远有效） |

### imdrak 独立确证（Jul 30）

- +524 = `ldr x8, [x8]; blr x8` = `shouldOverridePullTransaction()` 虚分发
- `weak_ptr::lock()` 返回 non-null（`tbz` 被取为 non-null）
- 4.25.2 + PR patch → 88/88 零崩（vs 未修 6/128 = 4.7% 崩率）

---

## 6. 可能的问题 + 排查

### 6.1 /diag 跑在子会话（不 Task 调 subagent，自己 inline 干一切）
**症状**：/diag 进了一个子会话，在里面 MCP 建/grep/自审，不 delegate。  
**原因**：父目录有旧 `.opencode/`（opencode 从 cwd 向上合并，父级旧版盖过）。  
**修法**：`rm -rf <父目录>/.opencode`，确保只有项目根的 `.opencode/`。

### 6.2 CRG 建图 0 文件
**症状**：`code-review-graph status` 显示 0 nodes。  
**原因**：codebase 下嵌套 `.git` 没撤 → `git ls-files` 返回 gitlink。  
**修法**：执行 §2.1 的 `rm -rf .git` + `git init`。

### 6.3 CRG 建图超时
**症状**：`/diag` 第一步 CRG 门超时中止。  
**修法**：先手动 CLI 建好（§3），再跑 `/diag`。

### 6.4 code-tracer 退 grep
**症状**：code-tracer 用 grep 而非 CRG `callers_of`。  
**原因**：CRG tree-sitter C++ 对带 `const` 限定/全限定名命中不稳。  
**预期**：code-tracer 退回 grep + 源码 Read 闭合证据链（不算失败）。

### 6.5 根因机制偏差
**症状**：code-tracer 推断「同线程重入」而非「Java GC finalizer 跨线程 race」。  
**原因**：崩溃日志只有 6 帧（#00-#05），缺前导帧 #06-#21（未公开），看不到 GC finalizer。  
**预期**：缺前导帧下推断重入是合理的（代码级最可能绕过点），但实际根因更底层（allocator 级 race）。

---

## 7. 分支内容

```
HiAgent/（opencode-test6-setup 分支）
├── .opencode/
│   ├── agents/              # 12 subagent（含 code-graph CRG 门 + code-tracer + reviewer + log-parser + wiki 生产者 + feature 流水线）
│   └── commands/            # 9 命令（diag/bug-trace/feature-design/flow-doc/arch-doc 有 subtask:false + 编排契约）
├── AGENTS.md                # opencode 项目指令（两层架构 + workflow 表 + Wiki 约定已搬进 producer）
├── opencode.json            # 项目配置（CRG MCP + 权限）——**跑前用 test6/opencode.json 覆盖（加 web-deny）**
├── README.md                # HiAgent 安装 + 使用说明
├── tools/                   # logscope-triage CLI 源
├── test6/
│   ├── log/
│   │   └── rnscreens-pullTransaction-sigsegv.log   # 崩溃日志
│   └── opencode.json        # 隔离配置（external_directory:deny + web-deny）——复制到项目根覆盖
└── TEST6-SETUP.md           # 本文档
```

> codebase（react-native + react-native-screens）需按 §2 自行 clone（~9300 文件，不入仓）。
