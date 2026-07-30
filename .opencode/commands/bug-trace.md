---
description: BUG 定位（bug 报告驱动，非日志 → 根因）
subtask: true
---
BUG 报告定位根因。参数：$ARGUMENTS（bug 报告文本 + 代码仓路径 [+ wiki 路径]）

按以下步骤编排，中间结果留你这，最后返报告：

1. **CRG 新鲜度门**：Task 调 `code-graph`（全程判新鲜/问询/建图/报错）。`{ok:true}`→继续 step 2；`{ok:false}`→workflow 中止，不继续。

2. **取预期**：若有 wiki → Task 调 `wiki-reader`，传 bug 报告里的符号当信号，读 wiki 取预期行为 + 涉及模块。无 wiki → 跳过（提示「本仓无 wiki，本次无历史经验加持；可先跑 /arch-doc、/flow-doc 生成」但不停下）。

3. **回溯**：Task 调 `code-tracer`，传 bug 报告 + repo（CRG 图已新鲜）+ wiki 预期（无则标「无 wiki」）。从报告里的症状符号沿 CRG callers_of 反向回溯到偏离点，定位 file:line 根因 + 证据链 + 修复建议。

4. **报告**：返 `{file, line, confidence, evidence, fixSuggestion}` 交人审。
