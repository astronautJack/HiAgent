# AVSession 业务流 wiki — 错误索引（error_index）

> `/diag` 的 wiki-reader **只读本文件**做匹配；命中后按需读单页。**不全量读**各生命周期页。
> 由 `flow-writer` 聚合各页 frontmatter 的 `error_catalog` 生成。

| page_id | code | event | msg_pattern | throw_file | throw_line | step | function |
|---|---|---|---|---|---|---|---|
| avsession-cast | 14900001 | AVSESSION_CAST_BEHAVIOR | AVSessionRadar not registered / null | utils/src/avsession_radar.cpp | 201 | StartCast | ReportWithoutTrustInfo（经 ReportHiSysEventBehavior@248） |
| avsession-cast | 14900001 | AVSESSION_CAST_BEHAVIOR | AVSessionRadar null（trust 路径） | utils/src/avsession_radar.cpp | 225 | StartCast | ReportWithTrustInfo（经 ReportHiSysEventBehavior@248） |
| avsession-cast | GetRadarErrorCode(err) | AVSESSION_CAST_BEHAVIOR | 统一雷达错误码 | utils/src/avsession_radar.cpp | 248 | 任意投播步 | AVSessionRadar::ReportHiSysEventBehavior |

## 检索示例

- 日志出现 `AVSESSION_CAST_BEHAVIOR` + err `14900001` / "AVSessionRadar null" → 命中第 1 行 → `avsession_radar.cpp:201`（或 225/248），code-tracer 直接定位，连 `avsession-cast.md` 整页都不必读。
- 要调用链上下文再 `read avsession-cast.md` 的「调用序列」段。
