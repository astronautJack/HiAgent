# 数据契约

skill 之间只传版本化结构。字段变化必须升级 `schema_version` 并同步测试，不能让 agent 自由猜字段。

> **注意：本文件是规范说明，agent 运行时不直接读它。** 实际生效的是各 agent/skill prompt 里内联复述的 schema 副本（`log-parser.md`、`diag/SKILL.md` 等）。改字段须**同步三处**：①本文件（规范）②对应 prompt 内联副本（执行）③`tests/`（门禁）。漏一处即漂移，且 skill 化后无运行时强校验，全靠 prompt + 测试 + 人审。

## `hiagent.log-digest.v1`

由 `logscope-triage --json` 直接产生（单文件）；目录/压缩包输入时由 `log-parser` 经 `logscope-collect` 归一为纯文本目录后逐文件 triage、汇总成同一契约：

```json
{
  "schema_version": "hiagent.log-digest.v1",
  "raw_file": "C:\\logs\\sample.log",
  "log_format": "auto",
  "drain_mode": "learn",
  "line_count": 123,
  "claimed_error": "AUDIO/START_FAIL",
  "symbols": [{"kind":"function","name":"Start","raw_line":17}],
  "clusters": [{
    "id":"1",
    "template":"open <NUM> failed",
    "count":3,
    "representative_line":17,
    "domain":"ABCD",
    "tag":"Player",
    "level":"E",
    "is_new":true,
    "known":false,
    "parameter_types":["NUM"]
  }],
  "hisysevent_anchors": [],
  "fault_frames": [],
  "key_lines": [17],
  "truncated": {"clusters":false,"hisysevents":false,"fault_frames":false,"key_lines":false}
}
```

`clusters[].count` 是本次输入日志内计数；Drain3 持久化 cluster size 不得作为本次频次。参数只返回 mask 类型，不返回可能敏感的实际值。

### 收集模式（目录/压缩包输入）的可选字段

输入是目录或压缩包时，`log-parser` 先用 `logscope-collect` 解压并按原始相对目录结构归一为纯文本目录，再逐文件 triage。顶层字段取自 primary 文件（含崩溃信号者），另加两个**可选**字段：

```json
{
  "log_dir": "<workDir>/collected",
  "sources": [
    {"path":"device/hilog.txt","line_count":1500,"log_format":"auto","is_primary":false,"digest":{<完整 per-file digest>}},
    {"path":"tombstone/crash.txt","line_count":17,"log_format":"generic","is_primary":true,"digest":{...}}
  ]
}
```

- `path` 相对 `log_dir`，保留原始结构。`code-tracer` 用它 `Read <log_dir>/<path>:<行号>` 直接取证，日志证据 `ref` 写真实文件路径而非合并行号。
- `sources[]` 是加性可选字段，不破坏 v1；单文件输入时不出现。

## `hiagent.trace.v1`

```json
{
  "schema_version": "hiagent.trace.v1",
  "root_cause": {"file":"src/a.cpp","line":42,"symbol":"Start","summary":"状态首次偏离","confidence":"high"},
  "evidence": [{"kind":"log|code|crg|config|wiki","ref":"src/a.cpp:42","claim":"..."}],
  "impact": ["..."],
  "fix": {"summary":"...","changes":[{"file":"src/a.cpp","description":"..."}]},
  "open_questions": []
}
```

`hiagent.trace.v1` 只由 investigator 生成，不含报告路径。adversarial reviewer 在独立上下文中先形成自己的判断，再核验结构化 claim；最后 `trace-report-writer` 在第三个上下文中把已结束的 trace/verdict 渲染到运行目录。writer 不得改变结论。

## `hiagent.feature-design.v1`

```json
{
  "schema_version":"hiagent.feature-design.v1",
  "summary":"...",
  "assumptions":[],
  "changes":[{"file":"src/a.cpp","symbol":"Start","description":"...","type":"modify"}],
  "risks":[],
  "test_plan":[],
  "knowledge_updates":[]
}
```

`feature-design` 返回该契约的同时返回 `ask_user` 和 `hiagent.skill-handoff.v1`。只有用户明确批准，且 CodeAgent 把本次 design 原样传递并设置 `approved=true`，才能进入 `feature-implement`。

## `hiagent.experience.v1`

写入 wiki-mcp 的 metadata：

```json
{
  "schema_version":"hiagent.experience.v1",
  "repo":"repo-id",
  "source_commit":"git-sha",
  "source_paths":["src/a.cpp"],
  "confidence":"high",
  "created_from":"diag",
  "tags":["START_FAIL"]
}
```

页面 `external_id = hiagent:<repo-id>:case:<stable-slug>`，是跨重试和重复归档的幂等键。

页面不携带固定分类。`exp-archive` 把 `metadata.created_from` 作为 `target.route` 交给 wiki-gateway；gateway 读取 `.cac/wiki-targets.json` 的可变分类列表和 routes，从 `base_url` 导航到准确名称。禁止拼接 URL 或直接使用 base。

## wiki-gateway 统一动作

- `probe` → `{available,server,capabilities,error}`
- `search` → `{matches,total}`
- `read` → `{found,page}`
- `upsert` → `{written,action,id,title,url,verified,error}`

这些是 HiAgent 内部契约，不假设 wiki-mcp 的实际工具名。适配发生在 `wiki-gateway` 内部。
