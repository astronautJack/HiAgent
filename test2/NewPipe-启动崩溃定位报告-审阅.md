# NewPipe 启动崩溃定位报告 审阅（test2 / 修复前代码）

> 审阅对象：`NewPipe-启动崩溃定位报告.md`（test2，**修复前** NewPipe 代码 dfc3f4b9f，无 keep 规则）  
> 对照：修复 PR [#13524](https://github.com/TeamNewPipe/NewPipe/pull/13524)「proguard-rules: Keep resource **classes** for prettytime」+ test1 审阅  
> 审阅方式：读源码 + 日志验真 + 对照 maintainer 修复，未跑 diag

> **更正（2026-07-29）**：本审阅原 §1 / 验证清单称「PID 22907 不是崩溃 PID / 222 次纯子串匹配 / 05-17 共 8 次」——**审阅自身核实错误，已撤销**。
> 复核 log:1847 = `05-17 04:44:51.585 22907 22907 E AndroidRuntime: FATAL EXCEPTION: main`：**22907 是真实的 04:44:51 FATAL main 崩溃 PID**。05-17 FATAL main 实际 **9 次**（20985/21026/21051/21088/21112 @04:25:54–57、21936@04:31、22792@04:44:38、22837@04:44:40、**22907@04:44:51**），非 8。
> 审阅原错因：(1) `grep … | head` 截断 10 行，line 1847（22907）在 head 外未显示；(2) `grep "PID 22907"` 用错模式——logcat 是裸数字无 "PID" 前缀，永不匹配；(3)「222 次纯子串」误判——含 22907 自身崩溃栈前缀。
> 另：原 §2「`.properties` 机制误判」**降级**为「资源类型描述词未验证」——根因机制（R8 shrinking 剥 i18n → getBundle 失败）成立且被 maintainer keep 规则方向证实；仅 `.class`/`.properties` 描述词是双方均未解 jar 的臆断。

## 总体结论

**比 test1 明显进步——这次走对了方向。** 在修复前代码（无 keep 规则）上，diag 正确识别了根因区（PrettyTime i18n bundle 缺失、R8 shrinking 所致）并提议保留资源，方向与 maintainer 实际修复（PR #13524）一致。test1 把「已在仓内的修复」误判为「不足的缺陷」；test2 在无规则的代码上提议「加规则」，这是对的。

但有 3 类问题：崩溃计数/PID 事实错误、`.properties` 机制与 maintainer 的「classes」相悖、修复建议未落到 `proguard-rules.pro` 具体规则。

## 已核实正确（读源码 + 日志验真）

| 项 | 报告值 | 核实 |
|---|---|---|
| 根因行 | `Localization.java:379` = `return new PrettyTime(getAppLocale());` | ✅ 一致 |
| 触发点 | `App.kt:104` = `Localization.initPrettyTime(Localization.resolvePrettyTime())` | ✅ 一致 |
| locale 闭合 | log:933 `locales updated from [] to [en_US]` | ✅ 一致（05-17 04:25:54.801 PID 20985） |
| 构建开关 | `build.gradle.kts:84-85` `isMinifyEnabled=true` + `isShrinkResources=true` | ✅ 一致（报告未提此两行，但开关确在） |
| 依赖来源 | `build.gradle.kts:299` `implementation(libs.ocpsoft.prettytime)` | ✅ 一致 |
| 修复前状态 | proguard-rules.pro 无 prettytime keep 规则 | ✅ 一致（grep=0，确认是修复前） |
| `claimed_error` | `null`（工具未断言，人工判读 FATAL 簇） | ✅ 诚实——**比 test1 的假阳性好**（test1 误命中 `buffers:` 元数据的 `crash` 字样） |
| R8 行映射 | 注 27 标注「:489/:7 为混淆行，源码行由 CRG+源码对齐」 | ✅ 标为推断——**比 test1 的未验证断言好** |

## 审阅疑点

### 1. 崩溃计数少计（PID 全部真实，非伪造）——**审阅原「22907 假 PID」判断已撤销**
报告称「05-17 启动崩溃 **3 次**（PID 20985 @04:25、22792 @04:44:38、22907 @04:44:51），每次栈完全一致」。复核：

- 05-17 `FATAL EXCEPTION: main` 实际 **9 次**（PID 20985/21026/21051/21088/21112 @04:25:54–57、21936 @04:31、22792 @04:44:38、22837 @04:44:40、**22907 @04:44:51**，见 log:1847）。
- 报告列的 3 个 PID（含 22907@04:44:51）**全部是真实崩溃 PID**，非伪造——审阅原称「22907 假 PID」是审阅自身核实错误（见顶部更正），撤销。
- 报告的真实问题：**少计**——把 3 个代表样当总数写了（应 9）。应改为按 digest `cluster.size` 或实数 FATAL 行得 9。

### 2. `.properties` 资源类型描述词未验证（**非「机制误判」**——机制成立）
报告（§4 + 修复#2）用「`.properties`」描述被剥离的资源。maintainer 修复 PR #13524 用 `-keep class ...Resources*` + 标题「Keep resource **classes**」，强示 prettytime i18n 是 `ListResourceBundle` 子**类**。

- **机制成立**：根因「R8 shrinking 剥离 PrettyTime i18n 资源 → `ResourceBundle.getBundle` 按名加载失败」正是 maintainer keep 规则要解决的，方向已被实际修复证实。审阅原「机制误判」帽子**收回**。
- **仅描述词未验证**：`.class` vs `.properties` 是报告的臆断；审阅也未解 jar（双方都在推）。prettytime jar 不在本地 gradle 缓存（未构建），建议 `unzip -l prettytime-*.jar | grep i18n` 实证后改措辞为「资源类」或「.properties」。

### 3. 修复建议未落到 `proguard-rules.pro` 具体规则
修复#2 只笼统说「在打包规则中保留 `org/ocpsoft/prettytime/i18n/**` 资源」，未：
- 点名 `app/proguard-rules.pro`（该加规则的具体文件）；
- 给出 maintainer 的确切规则 `-keep class org.ocpsoft.prettytime.i18n.Resources* { *; }`。

修复前代码的诊断应直接提议「在 `proguard-rules.pro` 末尾加 `-keep class org.ocpsoft.prettytime.i18n.Resources* { *; }`」——这才与 maintainer 的实际修复对齐，可机检。

### 4. 根因链未提「构建开关」
报告提了 `build.gradle.kts:299`（依赖），但没提 `:84-85` 的 `isMinifyEnabled=true` + `isShrinkResources=true`——**正是这两个开关启用了 R8 shrinking**，是根因链的「构建开关」环节。test1 报告提了开关（虽行号写错 78-79，实际 84-85）；test2 漏了。补上才闭合「依赖→开关→剥离→缺 bundle」链。

## 与 test1 对比（同一项目两次测试）

| 维度 | test1（修复后代码） | test2（修复前代码） |
|---|---|---|
| 代码状态认知 | ❌ 把已有修复当缺陷 | ✅ 识别无规则、提议加 |
| 修复方向 | ❌ 说 keep 规则不足、另改 keep.xml | ✅ 提议保留 prettytime i18n（与 maintainer 同向） |
| `claimed_error` | ❌ 假阳性（`buffers:` 含 crash） | ✅ null（诚实，人工判读） |
| R8 行映射 | ⚠️ 当断言 | ✅ 标为推断 |
| 崩溃计数 | 12（MissingResourceException 实际 24） | 3（实际 8）+ 假 PID 22907 |
| 机制措辞 | .properties（错） | .properties（同样错） |
| 落到具体规则 | 提了 proguard-rules.pro:59（但判错） | 未点名 proguard-rules.pro / 未给确切规则 |

**结论**：test2 整体优于 test1——隔离 test1 + 用修复前代码后，diag 没再犯「把修复当缺陷」的错，方向对了。剩 `.properties` 机制误判 + 计数/PID 事实错 + 修复建议不够具体。

## 改进建议（对 HiAgent 项目）

| 问题 | 改进 | 落点 |
|---|---|---|
| 崩溃计数/PID 漏算 + 假 PID | code-tracer 数 FATAL/崩溃簇时用 digest 的 `size`（cluster size）而非手挑几个 PID；PID 要从 FATAL 行实取，别凑 | code-tracer（证据链措辞 + 计数来源） |
| `.properties` vs `classes` 误判 | 根因机制别臆断资源类型；可在 digest 阶段或 code-tracer 解依赖 jar 列 i18n 条目（`.class`/`.properties`）实证 | code-tracer（依赖探查） |
| 修复建议不具体 | 提议 keep 规则应给确切 ProGuard 语法 + 落点文件（`proguard-rules.pro`），可机检 | code-tracer / 报告模板 |
| 漏构建开关 | 根因链应含「构建开关」（`isMinifyEnabled`/`isShrinkResources`）环节 | code-tracer（回溯到 build 配置） |

## 验证清单（人审确认）

- [ ] 05-17 FATAL main 实际次数（已核实：**9**，非 3；报告少计）
- [ ] PID 22907 是否为崩溃 PID（已核实：**是**，log:1847 `04:44:51.585 22907 22907 … FATAL EXCEPTION: main`；审阅原「否」撤销）
- [ ] prettytime 5.0.8 i18n 是类还是 `.properties`（maintainer PR 标题「classes」+ `-keep class` 强指示类；解 jar 确认）
- [ ] `proguard-rules.pro`（修复前）是否确无 prettytime 规则（已核实：无）
- [ ] `build.gradle.kts:84-85` 构建开关（已核实：minify+shrink 开）
- [ ] `Localization.java:379` / `App.kt:104`（已核实：一致）

## 一句话裁决

**方向对了，细节没到位。** 修复前代码 + 隔离 test1 后，diag 正确指向「PrettyTime i18n bundle 被 R8 shrinking 剥离 → 加 keep 规则」，与 maintainer PR #13524 同向——这是 test1 没做到的。但崩溃计数少计（3 vs 9；3 个 PID 含 22907 全真实，非伪造——审阅原误判已撤销），资源类型描述词 `.properties` 未验证（机制本身成立），修复建议没落到 `proguard-rules.pro` 的确切 `-keep class ...Resources* { *; }` 规则。修掉这几点，报告就够格作为可机检的定位结论。
