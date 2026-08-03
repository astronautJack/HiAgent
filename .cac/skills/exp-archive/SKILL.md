---
name: exp-archive
description: 经验沉淀用例。把人工确认且验证充分的案例幂等写入公司 wiki-mcp，写后回读核验父位置与内容。仅在人确认结果后调用。传 args {caseData, repo, humanConfirmed}。
---

# exp-archive — 经验归档状态机

本 skill 是编排层，只做质量门校验、结构化传值和回读核验；底层能力放 subagent。

## 输入

- `caseData`：已确认案例对象（必填）。
- `repo`：目标代码仓（必填）。
- `humanConfirmed`：必须为 `true`。

## 路径工具

- `isWindowsAbsolutePath(v)`：`/^[A-Za-z]:[\\/]/` 或 UNC。
- `hasTraversal(v)`：按 `[\\/]/` 切分后含 `..`。

## 阶段 0：质量门（前置校验）

1. `repo` 必须 Windows 绝对路径且无穿越，否则 `{archived:false, stage:'validate', error:'repo 必须是 Windows 绝对路径'}`。
2. `caseData` 必须是对象。
3. `humanConfirmed !== true` 则 `{archived:false, stage:'quality-gate', reasons:['humanConfirmed 必须为 true']}`。
4. `caseData.confidence !== 'high'` 则 `reasons:['confidence 必须为 high']`。
5. `caseData.evidence` 必须是非空数组，否则 `reasons:['至少需要一条结构化证据']`。
6. `caseData.validation` 必须存在，否则 `reasons:['缺少验证证据']`。
7. `JSON.stringify(caseData).length > 100000` 则 `{archived:false, stage:'validate', error:'caseData 过大；只传脱敏摘要和证据引用，不传完整日志'}`。

任一质量门未过返回 `{archived:false, stage:'quality-gate'|'validate', reasons|error}`，不进入后续阶段。

## 阶段 1：Curate

调用 `experience-curator` subagent，提示「执行经验归档质量门并生成页面。」输入 `{caseData, repo, human_confirmed:humanConfirmed}`。校验返回符合 `PAGE` 契约：

```json
{
  "ready": true,
  "reasons": [],
  "page": {
    "external_id": "hiagent:<repo-id>:case:<stable-slug>",
    "title": "",
    "content": "",
    "metadata": {}
  }
}
```

- `ready` 为 false 则 `{archived:false, stage:'quality-gate', reasons:curated.reasons}`。
- `page.external_id` 必须是字符串且以 `hiagent:` 开头，否则 `{archived:false, stage:'quality-gate', error:'external_id 必须是稳定的 hiagent: 幂等键'}`。

## 阶段 2：Wiki

调用 `wiki-gateway` 执行 probe，校验 `PROBE = {available, server, capabilities, error}`。`!available || !capabilities.write` 则 `{archived:false, stage:'wiki', error:probe.error||'wiki-mcp 不可用或无写入能力', page:curated.page}`。

## 阶段 3：Publish

调用 `wiki-gateway` 执行 upsert 并回读核验，输入 `{...curated.page, target:{route: caseData.created_from || 'default'}}`。校验 `WRITE`：

```json
{
  "written": true,
  "action": "created | updated | none",
  "id": "",
  "title": "",
  "url": "",
  "verified": true,
  "error": ""
}
```

## 输出

```json
{
  "archived": "<written && verified>",
  "stage": "<written&&verified ? 'complete' : 'verify'>",
  "...WRITE 结果",
  "external_id": "<curated.page.external_id>"
}
```

`archived` 仅在 `written && verified` 同时为真时为 true。「写请求成功」不等于「归档成功」。

## 不变量

- `target.route` 来自 `caseData.created_from`（来源场景），由 `wiki-gateway` 读取 `.cac/wiki-targets.json` 路由；不在本 skill 写死分类名。
- 不保存完整原始日志；只保存脱敏摘要和证据引用。
- 写后必须回读核验父位置与内容；无法确认时 `verified=false`。
