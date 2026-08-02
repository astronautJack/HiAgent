# 数据契约

workflow 之间只传版本化结构。字段变化必须升级 `schema_version` 并同步测试，不能让 agent 自由猜字段。

## `hiagent.log-digest.v1`

由 `logscope-triage --json` 直接产生：

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

## `hiagent.trace.v1`

```json
{
  "schema_version": "hiagent.trace.v1",
  "report_path": "C:\\repo\\.hiagent\\runs\\diag-1\\report.md",
  "root_cause": {"file":"src/a.cpp","line":42,"symbol":"Start","summary":"状态首次偏离","confidence":"high"},
  "evidence": [{"kind":"log|code|crg|config|wiki","ref":"src/a.cpp:42","claim":"..."}],
  "impact": ["..."],
  "fix": {"summary":"...","changes":[{"file":"src/a.cpp","description":"..."}]},
  "open_questions": []
}
```

报告 Markdown 与结构化 trace 必须表达同一结论；reviewer 独立核验结构化 claim。

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

只有该契约且 `approved=true` 才能进入 `feature-implement`。

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
