# HiAgent — 测试设计与结果汇报（test 分支）

> 本分支（`test`）是 HiAgent 的**测试产物分支**：只存测试过程与结果，不同步 `.opencode/` 配置改进（改进落在 `main` / `codeagent` / `opencode` 三个 dev 分支）。本 README 是今日工作汇报，供 mentor 直接审阅。

---

## 一、HiAgent 与 `/diag` 速览（背景）

HiAgent 是基于 OpenCode 的解耦版 agent 工具集，按「共享能力层 + 用例编排层」组织。核心用例之一 **`/diag`**：丢一份崩溃日志进去，沿代码调用图（CRG）反向回溯，定位到**具体哪一行代码**是根因，附证据链（日志行号 + `文件:行` + 调用链）。

`/diag` 编排：`log-parser`（长日志压成有界 digest）→ `wiki-reader` → **`code-tracer` 写定位报告** → **`code-tracer-reviewer` 独立审阅**（重跑 CRG/grep + 重读源码验真，最多 loop 3 次）→ 报告交人审。双 agent 设计是为防 code-tracer 自审自圆其说。

---

## 二、今日改进：code-tracer 与 reviewer 职责重切

### 发现的问题（test3 实测暴露）
test3 跑出新 regression：改进版的 code-tracer 把根因机制全 hedge 成「资源包失败」，丢了上一版能点名的「R8 shrinking 剥了 i18n bundle」。根因诊断：
- **hedge / 自我审查规则塞在了 code-tracer 提示词里**，让它一刀切全 hedge 求稳；
- **reviewer 提示词里混进了 hindsight 评分、双标、越权**（把「引构建配置」提成硬门槛）等**审阅者个人复盘话**，导致 reviewer 越权苛责一份本合格的报告。

### 改进内容（重切职责边界）

| agent | 改进后职责 | 删去 |
|---|---|---|
| `code-tracer` | **只定位**：assertive 提能推出的机制候选（不憋着），构建配置可 Grep `.kts`/`.pro` | hedge 规则、自我审查、确定源/实证/可 apply 等原则 |
| `code-tracer-reviewer` | **事实 + 逻辑守门**：claim 是假 / 逻辑断才 `verdict=revise` | hindsight 评分、强制 hedge 风格、build-config hard gate、机制具体度强制 |

### 落地（三 dev 分支已推远程）

| 分支 | HEAD | 载体 |
|---|---|---|
| `opencode` | `067d22b` | `.opencode/agents/`（OpenCode，源分支） |
| `main` | `38bc242` | `.claude/agents/`（Claude Code 移植） |
| `codeagent` | `ee4dded` | `.cac/agents/`（CodeAgent 移植） |

---

## 三、测试设计

### 目的
用**真实开源项目的崩溃 case** 验证 `/diag` 定位质量：codebase 取**修复前**版本（bug 确实在），配真实 crash log，跑 `/diag` 出报告，再用**已知答案 PR** 作 ground truth 对照，由审阅者拿源码 + 日志 + PR 逐行验真。

### 每个 `testN/` 的结构
```
testN/
├── codebase/                  # 修复前的开源仓（bug 在）
├── log/                       # 真实 crash log
├── .opencode/                 # /diag 配置（agents + commands）
├── opencode.json              # 权限隔离（external_directory:deny）
├── diag-report-*.md           # code-tracer 产出的定位报告
└── diag-report-*-审阅.md       # 审阅者验真 + 评定位质量
```

### 验真口径
审阅者遵循「**事实 + 逻辑守门**」：核对报告每个 `file:line` claim 对源码是否为真、证据链（日志帧 → CRG 边 → 源码行）是否闭合、根因机制逻辑是否成立。claim 假或逻辑断才判 revise；不搞 hindsight 评分、不强制 hedge 风格、不把边界外期望当核心门槛。

---

## 四、测试结果

### test3 — NewPipe nightly 启动崩溃（重切前）
- **case**：NewPipe nightly 启动即崩（`MissingResourceException: Can't find bundle ... prettytime.i18n.Resources`）
- **code-tracer 定位**：根因 `Localization.java:379`（`return new PrettyTime(getAppLocale())`）+ 触发入口 `App.kt:104`（`initPrettyTime(resolvePrettyTime())`）；证据链日志帧 → CRG `callers_of resolvePrettyTime` → 源码行闭合；confidence=high
- **已知答案**：PR [#13524](https://github.com/TeamNewPipe/NewPipe/pull/13524)
- **审阅结论**：报告合格（file:line 准 + 证据闭合 + 计数来自 digest）。早期苛责（机制没点名 R8 / 漏构建开关 / reviewer 没拦 = 失职）经复核**站不住，全部撤回**——拿已知答案倒推罚报告是 hindsight grading，且机制依赖的「类型（class/.properties）」本仓未构建无法实证、是未定的，hedge 合理。留 1 温和改进（可补一句 R8 候选，非失分）。
- **本次实测的真正产出**：发现「hedge 规则放错层（code-tracer 而非 reviewer）」的设计缺陷 → 直接引出上面的职责重切。

### test4 — commons-app #6433 旋转崩溃（重切后首测）
- **case**：旋转屏后点暂停上传即崩（`UninitializedPropertyAccessException: lateinit property pendingUploadsPresenter has not been initialized`）
- **code-tracer 定位**：根因 `UploadProgressActivity.kt:77`（`setTabs()` 无条件 `PendingUploadsFragment()` 新建实例塞字段，未做 `savedInstanceState` 守卫）。机制四环：
  1. `setTabs:77` 造孤儿实例塞字段；
  2. pager 继承的 `instantiateItem` 用 tag 恢复另一个实例、不调 `getItem`；
  3. 字段实例从未进 FragmentManager → `onAttach` 没跑 → Dagger 注入未发生；
  4. 菜单 lambda 调字段实例 `pauseUploads()` 读未初始化 presenter 即抛。
- **已知答案**：PR [#6532](https://github.com/commons-app/apps-android-commons/pull/6532)——维护者反复调试后结论「stale reference（字段指向错误实例），**非**注入时机/竞态」；最终修法用 `findFragmentByTag` 取回活动实例，与报告定位的根因行 + 机制一致。报告还**提前点了 `failedUploadsFragment` 对称缺陷**，PR 评论中 reviewer Ritika 实测确认同崩。
- **审阅结论**：**PASS**。定位准、机制经源码逐行证实、证据链闭合、**没停在症状层**（浅报告会停在「改 nullable 兜底」——正是 PR 作者最初被 reviewer 打回的错误方向）；reviewer 放行正确。留 1 温和观察（恢复实例措辞「旧 fragment」严格说是 FM 重建的新实例，不影响机制，非失分）。

---

## 五、改进效果对照

| 维度 | test3（重切前） | test4（重切后） |
|---|---|---|
| code-tracer 定位 | 准，但机制过度 hedge（丢 R8） | 准，且机制深（孤儿实例四环） |
| reviewer 守门 | 越权苛责（hindsight / 双标 / 越权），后被撤回 | 边界清晰（事实 + 逻辑），放行正确 |

职责重切解决了 test3 暴露的问题：hedge / 自我审查移出 code-tracer（它只管 assertive 定位），reviewer 只守事实 + 逻辑、不再越权苛责。test4 首测证明重切后**定位质量**与 **reviewer 守门边界**均达标。

---

## 六、测试不足（坦诚说明）

两个 case 互补地各缺一头：

| case | 长处 | 短处 |
|---|---|---|
| **test3** | log 完整（原始 logcat，未筛选） | 问题本身较简单——`MissingResourceException` 栈帧几乎直接指向 `Localization.java:379`，根因在栈里就可见，没真正考验「反向回溯」的深度 |
| **test4** | 问题较难——症状（`UninitializedPropertyAccessException` @ `PendingUploadsFragment.kt:150`）mask 了真根因（在另一个类 `UploadProgressActivity.kt:77` + Fragment 生命周期机制），需跨类回溯 | log 是 issue 提交者**已筛选过的**（28 行，截到关键栈 + `CONFIGURATION_CHANGED` + `USER_COMMENT`），不是原始长日志——没考验 `/diag` 处理原始长日志的 triage 能力（`log-parser` 压缩 + 新见簇检测那一段没真正跑） |

其他不足：
- **样本量小**：仅 2 个 case（test1/test2 已删，方法不成熟故弃）。
- **格式单一**：两个都是 Android logcat，未测通用文本日志。
- **审阅同源**：审阅者与 code-tracer 是同一 LLM，可能有同源盲区；且对照已知答案 PR 有 hindsight 风险（test3 审阅已暴露并撤回苛责）。
- **未跑真实回归**：test4 codebase 是修复前快照，但未在修复后 codebase 上复跑确认「定位消失」，仅靠 PR 对照，非闭环。

**下一步可补**：找一个「问题难 + 原始长日志」的 case（如服务端通用文本日志 + 跨多文件根因），同时考验 triage 与回溯深度。

---

*本分支仅存测试产物；HiAgent 主体（配置、工具、安装说明）见 `main` / `opencode` 分支。*
