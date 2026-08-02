# Windows 内网手工适配手册

本文档的目标是：不借助 AI，仅用 Git、PowerShell、公司 uv 安装器和 CodeAgent 完成内网部署。

## 1. 准备

确认 Windows 已有：

```powershell
git --version
uv --version
codeagent --version
```

若缺少 uv，先运行公司提供的 `uv_install.psl`。HiAgent 不自带、不下载 uv。

## 2. 获取项目

正式合入 `codeagent` 分支后：

```powershell
git clone -b codeagent https://github.com/astronautJack/HiAgent.git
cd HiAgent
```

若内网已有仓库：

```powershell
git switch codeagent
git pull
```

确认存在 `.cac\settings.json`、`.cac\agents`、`.cac\workflows`。

## 3. 安装依赖

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

脚本执行：

1. 用 `uv tool install --force "code-review-graph>=2.3.7,<3.0"` 安装兼容版本。
2. 从本仓 `tools` 安装 `logscope-triage`、`hiagent-crg`、`hiagent-run`。
3. 验证命令和 `.cac` 文件。

再次确认：

```powershell
code-review-graph --version
logscope-triage --help
hiagent-crg --help
hiagent-run --help
```

## 4. 配置 Wiki 分类

只需准备：

- 公司给出的 Wiki `base_url`。
- 当前各分类在该 base 下的准确名称。

不要自行把分类名拼到 base_url 后面。`wiki-gateway` 会让 wiki-mcp 从 base 导航到对应子位置，并使用 MCP 返回的 ID/URL 作为 parent。

推荐运行：

```powershell
.\scripts\configure-wiki.ps1
```

脚本读取 `.cac\wiki-targets.json` 里的当前分类列表，依次询问准确名称。当前模板中的四类只是初始建议，不是代码契约。

也可以直接用记事本编辑 `.cac\wiki-targets.json`：

```json
{
  "schema_version": "hiagent.wiki-targets.v2",
  "base_url": "公司给出的 Wiki base URL",
  "categories": [
    {"key": "code", "name": "准确目录名", "description": "代码类知识"},
    {"key": "logs", "name": "准确目录名", "description": "日志定位经验"},
    {"key": "misc", "name": "准确目录名", "description": "其他已验证知识"}
  ],
  "routes": {
    "diag": "logs",
    "bug-trace": "logs",
    "feature-implement": "code",
    "default": "misc"
  }
}
```

以后分类变化时只改这个 JSON：

1. 在 `categories` 中增删或改名；`key` 是稳定内部标识，`name` 是 Wiki 准确名称。
2. 在 `routes` 中把来源场景指向目标 key；必须保留 `default`。
3. 确认所有 route 的值都能在 categories 中找到，key 和 name 都不能重复。
4. 重新运行 `wiki-health`。

无需修改 workflow、subagent 或 Python。`configure-wiki.ps1` 也不包含固定分类列表，它只处理 JSON 中已有的项目。

检查：

```powershell
Select-String -Path .cac\wiki-targets.json -Pattern "REPLACE_WITH_"
```

正确配置后应无输出。`base_url` 不参与写入；目标名称无法从 base 唯一定位时必须失败，禁止拼 URL、猜相似名称或降级写到 base。

## 5. 确认 MCP

`.cac\settings.json` 只负责启动本地 CRG MCP。公司 `wiki-mcp` 应由内网 CodeAgent 自动注入并自动处理权限，不要在仓库写 token、用户名或权限配置。

启动：

```powershell
codeagent
```

在会话中运行：

```text
运行 wiki-health
```

期望：

- `server = wiki-mcp`
- `available = true`
- `capabilities.search/read/write = true`
- `ready = true`

`wiki-health` 只做只读探测，不创建页面。若 search/read 可用但 write=false，先检查配置是否仍含占位符、route 是否有效，以及 wiki-mcp 能否从 base_url 看见每个准确名称。

若 `available=false`，问题在 CodeAgent 会话没有注入 wiki-mcp；联系内网平台管理员，不要自行填 token。

## 6. wiki-mcp 工具签名变化时

正常情况下 `wiki-gateway` 会根据服务名 `wiki-mcp` 的工具描述匹配 search/read/create/update/upsert，无需修改 workflow。

若内部工具描述不充分而适配失败，只改一个文件：`.cac\agents\wiki-gateway.md`。在“工具发现”下补充内网文档中的准确映射，例如：

```text
search:        <准确工具名>(query=<query>, limit=<limit>)
read:          <准确工具名>(page_id=<id>)
list-children: <准确工具名>(parent_url=<base_url>)
create:        <准确工具名>(parent_id=<定位到的分类 id>, title=<title>, content=<content>, external_id=<external_id>)
update:        <准确工具名>(page_id=<命中 id>, title=<title>, content=<content>)
```

必须保留以下行为：

- 工具所属服务必须是 `wiki-mcp`。
- 根据 `target.route` 读取配置中的 category key，再按准确 name 从 base 下定位 parent。
- 禁止字符串拼接 URL，禁止把 `base_url` 或 MCP 默认位置作为 parent。
- 写前按 `external_id` 精确查重。
- 写后 read 回查标题、external_id、正文摘要和父目录；无法确认分类则 `verified=false`。

不要修改 `diag.js`、`feature-*.js` 或 `exp-archive.js` 去适配具体工具名，否则会重新产生耦合。

## 7. CRG 大仓验收

首次可手工检查：

```powershell
hiagent-crg gate --repo C:\src\目标仓
```

小仓应返回 `ok=true`。超过默认 5000 tracked files 的仓库可能返回 `state=building`，说明已启动与 CodeAgent/MCP 请求分离的 Windows 后台 CLI build。

查看状态和日志：

```powershell
Get-Content C:\src\目标仓\.hiagent\crg-state.json
Get-Content C:\src\目标仓\.hiagent\crg-build.log -Tail 50
```

后台完成后再次运行 gate，应返回 `ok=true`。不要改成 MCP `build_or_update_graph_tool`；这会重新引入大仓 RPC 超时。

若返回 `ok=true` 但 `warning` 提示“CRG 不索引未跟踪源码”，图本身已更新，只是新建且尚未 `git add` 的源码不在图中。不要为了建图自动暂存文件；本轮 review 直接读这些文件，等人工决定纳入版本控制后再运行 refresh。

若仓库含大量 tracked 生成物，在目标仓根创建 `.code-review-graphignore`，例如：

```text
generated/**
vendor/**
**/*.snapshot.*
```

## 8. 验收顺序

按以下顺序执行，容易定位问题：

1. `.\scripts\test.ps1`：本地 workflow/Python 测试通过。
2. `wiki-health`：MCP 与分类配置通过，只读、无页面副作用。
3. `exp-search`：用一个已知 Wiki 标题确认权限内检索。
4. `feature-design`：确认能读 CRG 和 Wiki，但不改代码。
5. `diag`：用一份已脱敏日志确认产生报告与独立 review。
6. 用第一条真实、已验证案例运行 `exp-archive`。
7. 人工打开返回 URL，确认页面位于配置路由对应的子位置而非 base。
8. 用相同案例再次归档，确认更新原页面而不是产生重复页。

只有第 7、8 步通过，才算 wiki 写入适配完成。

## 9. 常见故障

| 现象 | 检查 |
|---|---|
| 找不到 uv | 先运行公司 `uv_install.psl`，重开 PowerShell |
| 找不到 CLI | 检查 `%USERPROFILE%\.local\bin` 是否在 PATH |
| CRG building | 等后台 CLI 完成，再原样重试 workflow |
| CRG update 慢 | 检查 `.code-review-graphignore` 和 tracked 生成物 |
| wiki search 可用、write 不可用 | 检查占位符、routes，并确认 base 下能精确看到各分类名称 |
| 页面写到错误分类 | 检查 `routes` 的来源场景与 category key 映射 |
| 页面可能写到 base | 立即停止归档；核对 gateway 是否先导航取得分类 ID，再把它作为 create parent |
| 重复页面 | 确认 wiki-mcp 搜索 metadata 支持 `external_id`，并在 gateway 映射中先查后写 |
