# CRG 与 Drain3 使用策略

## Code Review Graph

CRG 的 mutation 和 query 有不同的时延/失败特征，因此明确分流。

### CLI：状态与 mutation

| 场景 | 命令 | HiAgent 策略 |
|---|---|---|
| 机器状态 | `status --json` | 比较 `built_at_commit/current_sha`，禁止解析表格文本 |
| 首次建图 | `build --repo` | 小仓同步；大仓由 `hiagent-crg` 启动 Windows 后台进程 |
| 日常变更 | `update --repo` | 增量解析，包括 coder 改完后的 working tree |
| 重算派生数据 | `postprocess --repo` | 只在需要重算 flows/communities/FTS 时使用 |
| 持续维护 | `watch` / `daemon` | 可选运维，不由普通 workflow 改用户配置 |
| 排除噪声 | `.code-review-graphignore` | 排除 tracked generated/vendor/snapshot |
| 外置图库 | `--data-dir` | 网络盘或工作树不可写时采用 |

大仓建图不调用 MCP `build_or_update_graph_tool`。MCP/agent RPC 超时会杀掉请求，而后台 CLI 与会话分离，可以持续写图和日志。

CRG 2.3.x 的 build/update 没有 include-untracked 选项。HiAgent 不用 `git add` 污染用户暂存区：CLI 会返回未跟踪源码提示，审查阶段直接读取这些文件；用户将其纳入版本控制后再 refresh。

### MCP：只读、带预算查询

- 首选 `get_minimal_context_tool` 建立约 100 token 的入口。
- 精确符号关系用 `query_graph_tool`。
- 模糊入口用 `semantic_search_nodes_tool`，结果仍需读源码。
- 长链用 `traverse_graph_tool` 并设置 depth/token budget。
- 诊断用 flows、impact、affected flows。
- 代码设计用 architecture/communities/hub/bridge/knowledge gaps。
- 代码审查用 review context、detect changes、suggested questions。

settings 中不暴露 MCP mutation、embedding、apply-refactor 和 CRG wiki 写入工具，既减少工具上下文，也避免绕过项目门禁。

## Drain3

Drain3 是在线模板挖掘器，不是根因判断器。HiAgent 将其职责限制在“压缩与新模式检测”。

### 预处理

Harmony 三类数据先结构化：hilog、HiSysEvent JSON、native/ArkTS fault frame。hilog 只把 message 喂给 Drain3，时间、PID、TID 不参与模板，避免无意义分裂。

### Masking

默认掩码 IP、UUID、十六进制值和邮箱。掩码提升模板质量，同时避免参数值进入 LLM digest。`extract_parameters()` 只输出参数类型。

### Learn 与 inference

- `learn`：调用 `add_log_message()`，允许创建/更新模板并通过文件持久化。适合日常积累基线。
- `inference`：调用 `match()`，不改变已有模板；未匹配内容标成新信号。适合已有健康基线后的故障对比。

profile 默认按代码仓稳定复用并经过文件名清理，防止路径穿越。

### 计数与内存

Drain3 snapshot 保存的是跨运行累计 cluster size。HiAgent 另行维护 `run_count`，对外的 `clusters[].count` 只代表当前日志。

默认 `max_clusters=2000`，达到上限后由 Drain3 LRU 淘汰旧模板，避免持续学习导致内存与状态文件无界增长。digest 进一步限制 clusters、events、frames 和 key lines，原始日志始终留在文件中按行取证。

### 调参

配置位置为 `%USERPROFILE%\.logscope\config.json`。常用参数：

- `sim_th` 越高，匹配越严格，通常产生更多模板簇。
- `depth` 控制固定深度搜索树。
- `max_children` 控制内部节点分支。
- `max_clusters` 控制 LRU 容量。
- `extra_delimiters` 用于业务日志的额外分词。
- `masking` 用 `{regex_pattern, mask_with}` 扩展业务变量掩码。

改参数后应使用固定日志 fixture 比较簇数、claimed error 和关键锚点，不能凭感觉上线。

## 上游资料

- Code Review Graph 官方仓库：<https://github.com/tirth8205/code-review-graph>
- Code Review Graph CLI/MCP 命令参考：<https://github.com/tirth8205/code-review-graph/blob/main/docs/COMMANDS.md>
- Drain3 官方仓库：<https://github.com/logpai/Drain3>

当前实现按上述上游接口设计；升级依赖版本前，先核对命令和持久化格式，再执行本项目完整回归。
