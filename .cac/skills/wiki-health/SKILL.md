---
name: wiki-health
description: 内网 wiki-mcp 只读验收用例。检查 wiki-mcp 是否可检索、读取和写入，不产生测试页面。项目传入内网后首先运行；无需参数。
---

# wiki-health — wiki-mcp 零配置验收状态机

本 skill 是编排层，只做只读探测和结果汇总；底层能力放 `wiki-gateway` subagent。

## 输入

无参数。

## 阶段 1：Probe

调用 `wiki-gateway` subagent，提示「执行 probe。只做只读探测，不创建测试页面。服务名必须准确为 wiki-mcp。」校验返回符合 `PROBE` 契约：

```json
{
  "available": true,
  "server": "wiki-mcp",
  "capabilities": { "search": true, "read": true, "write": true },
  "error": ""
}
```

## 输出

```json
{
  "available": true,
  "server": "wiki-mcp",
  "capabilities": {},
  "error": "",
  "ready": true,
  "next": "可以直接运行 diag、feature-design、exp-search 和 exp-archive。"
}
```

- `ready = available && capabilities.search && capabilities.read && capabilities.write`。
- `available` 为 false 时 `next='确认内网 CodeAgent 会话已注入 wiki-mcp，然后重启 codeagent。'`。

## 不变量

- 探测只读，不创建测试页面。
- 服务名必须准确为 `wiki-mcp`。
