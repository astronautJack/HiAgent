# test5 /diag 报告审阅 — rnscreens-pullTransaction-sigsegv

> 审阅对象：`rnscreens-pullTransaction-sigsegv-report.md`（test5，react-native-screens #4151，native crash）  
> 对照：已知答案 PR [#4413](https://github.com/software-mansion/react-native-screens/pull/4413)  
> 审阅方式：读报告 + 源码逐行验真（`MountingCoordinator.cpp` / `FabricUIManagerBinding.cpp` / `Scheduler.cpp` / `ReactNativeFeatureFlags.h` 已验）  
> 注：本次为**干净跑**——web-deny 生效 + CRG 已 CLI 预建 fresh；先前 Exa 搜答案的会话已被关掉，本报告来自限权后重开的对话，无联网污染。  
> `/diag` 职责是定位 bug；修复建议简略是预期边界，不在苛责范围。

## 总体结论

**部分通过——崩点定位准、证据链源码逐行验真、且抓住了 PR 的核心 subtlety（`weak_ptr::lock` 该保活却没 = 控制块已回收）；但根因机制把 override delegate 的销毁路径说成「shared_ptr 释放 → weak_ptr 悬空」，与自己的存疑点#2（lock 非 null）自相矛盾，且未点名真凶（`RNSScreenRemovalListener` / `NativeProxy` fbjni GC / append-only `mountingOverrideDelegates_`）。** 非 clean PASS（不像 test4）：crash site + 关键 anomaly 是 genuine 好；根因机制陈述有内部矛盾 + 真凶未钉。

## 已核实正确

| 项 | 报告值 | 核实 |
|---|---|---|
| claimed_error | SIGSEGV / SEGV_ACCERR @ 0xe500000009 / execute non-exec memory | ✅ 与 log 一致 |
| 崩点定义 | `MountingCoordinator.cpp:71` = `pullTransaction` 定义 | ✅ 源码 :71 一致 |
| override-delegate 循环 | `:100-130` `for (delegate : mountingOverrideDelegates_)` | ✅ 源码 :100 一致 |
| weak_ptr::lock | `:101` `delegate.lock()` | ✅ 源码 :101 一致——存疑点#2 抓的正是这行 |
| shouldOverridePullTransaction | `:102-103` | ✅ 源码 :102-103 一致 |
| 虚分发崩点 | `:124` `mountingOverrideDelegate->pullTransaction(...)` | ✅ 源码 :124 一致 |
| frame #02 | `FabricUIManagerBinding.cpp:622` = `schedulerDidFinishTransaction` | ✅ 源码 :622 一致 |
| frame #02 调 pullTransaction | `:631` / `:675` 两处 `mountingCoordinator->pullTransaction()` | ✅ 源码 :631（else 分支）+ :675（`schedulerShouldRenderTransactions`）一致 |
| frame #03 | `Scheduler.cpp:303` = `uiManagerDidFinishTransaction` | ✅ 源码 :303 一致 |
| 根因源码 #1 | `Scheduler.cpp:316-332` Android 路径 lambda 捕获裸 `delegate` + guard | ✅ 源码 :316-332 逐字一致（注释也对上） |
| 根因源码 #2 | `ReactNativeFeatureFlags.h:263` `enableSchedulerDelegateInvalidation` guard 注释 | ✅ 源码 :262-265 逐字一致 |

（frame #04 `UIManager.cpp:659` / #05 `ShadowTree.cpp:476`：函数名对上 log 帧，行号未逐一验但一致。）

## 定位维度的审阅

### ✅ 没停在症状层
症状是 SIGSEGV @ scudo + execute-non-exec memory（一个信号 + 一个内存区名）。报告挖到 `pullTransaction` 的 override-delegate 虚分发 UAF + `delegate.lock()` anomaly——从信号到代码行 + 机制。

### ✅ 证据链源码闭合
崩点 + 调用链 #02–#05 函数名全对上 log 帧 + 源码行验真（`:71` / `:100` / `:124` / `:622` / `:631` / `:675` / `:303` + `:316-332` + `:263`）。无 fabricated 行——每条引的源码都对得上。

### ✅ 抓住关键 anomaly（存疑点#2）——正中 PR crux
报告存疑点#2：「`delegate.Lock()` 局部保活为何失效——若标准 `weak_ptr::lock`，局部 `shared_ptr` 应保活对象；实际崩溃说明存在越过该保活的并发析构/控制块竞态或 vtable 损坏。」这**正是 PR #4413 的核心 subtlety**：「`weak_ptr::lock()` 返回 non-null 给控制块已失效的槽 → 虚派发跳进回收堆。」报告没绕过这个矛盾，诚实标为待钉死（需完整 tombstone + 复现）。genuine 好——从源码读出「lock-保活-却-崩」的悖论，正是 PR 要解的。

## 根因机制 vs PR #4413——有偏差

| | 报告根因（3.3 bullet 3） | PR #4413 真根因 |
|---|---|---|
| 真凶 delegate | 「override delegate」（泛指，归 `Scheduler`/`ReactHost`/`NativeAnimatedNodesManagerProvider` 持 `shared_ptr`） | **`RNSScreenRemovalListener`**（归 `NativeProxy` fbjni hybrid，Java GC finalizer 随机销毁其 C++ 半） |
| 注册结构 | `weak_ptr` 注册进 `MountingCoordinator` | 注册进 core 的 **append-only `mountingOverrideDelegates_`**（无 `removeMountingOverrideDelegate` API，0.87 前） |
| 销毁路径 | stop→launch 释放强引用 → `weak_ptr` 悬空 | `NativeProxy` 被 Java GC finalize（finalizer 线程，不可预测时序） |
| lock 行为 | 「悬空 vtable」（隐含 lock 返回 null） | **lock 返回 non-null 给已回收控制块**（控制块本身被回收，非对象 gone） |

**偏差**：
1. **内部自相矛盾**——3.3 bullet 3 说「强引用释放 → weak_ptr 悬空 → 悬空 vtable」，但若 `lock()` 返回 null，`:102` 的 `mountingOverrideDelegate &&` 短路、不崩 `:124`。报告自己的存疑点#2 识破了这个矛盾（lock 非 null），但 3.3 仍写「悬空 vtable」——根因陈述与自己的存疑点打架。PR 的解恰好是：lock 返回 non-null 给**已回收控制块**（不是对象 gone 那种 null）。
2. **SchedulerDelegate guard 当背景，但非 #4151 根因**——3.3 bullet 1-2 引 `enableSchedulerDelegateInvalidation` guard（`Scheduler.cpp:316-332`，`SchedulerDelegate` 路径）是 real 机制（源码验真），报告也说「flag 关闭或该路径未覆盖 override-delegate → 悬空分发无防护」——即它知道 guard 是给 SchedulerDelegate 的、不覆盖 override 路径。但崩在 `:124`（override delegate 虚分发），guard 与 `:124` 无直接因果；把 guard 当根因背景，绕过了真凶（NativeProxy GC）。
3. **真凶未钉**——未点名 `RNSScreenRemovalListener` / `NativeProxy` fbjni GC / append-only list。建议段（section 5）提了「`mountingOverrideDelegates_` 无 unregister 接口、`weak_ptr` 失效窗口」（genuine grep `mountingOverrideDelegates_` 4 matches 查到，方向对上 PR），但那在建议、不在根因，且没钉到 `NativeProxy`/`RNSScreenRemovalListener` 这个具体 owner。

## 存疑点评估

- **存疑点#1（+524 无法逐指令符号化）**：诚实。log 确实截断（6 帧，全 tombstone 未公开），`:124` vs `:102-103` 二选一钉不死。报告正确标「两候选同经 `mountingOverrideDelegate` 虚分发，根因类不变」——合理。
- **存疑点#2（lock 保活失效）**：**核心好 catch**（见上）——正中 PR crux。

## reviewer 表现

报告 workflow 行：「code-tracer 单次回溯证据闭合，未触发 reviewer loop」——即 reviewer 一次 pass（无 revise 循环）。报告含 `## 存疑点`（+524 + lock anomaly）——code-tracer 诚实留了残差。reviewer 放行一份「崩点准 + 证据链源码闭合 + lock-anomaly 诚实标出」的报告，**合理履职**——这些维度确实 pass。根因机制的内部矛盾 + 真凶未钉，reviewer 没拦——可议：reviewer 本可对「3.3 悬空 vtable 与存疑点#2 lock-非null 自相矛盾」判 revise；但 native cross-repo + 截断 log 的难度下，claim 没假、证据链没断（只是机制没钉死），放行不算失职。

## 一句话裁决

**部分通过**：崩点定位准（源码逐行验真）+ lock-anomaly 抓取是 genuine 好（正中 PR crux）+ 证据链闭合；但根因机制 3.3 与存疑点#2 自相矛盾（悬空 vs lock-非null）+ 真凶（`NativeProxy`/`RNSScreenRemovalListener`/append-only list）未钉。**干净跑**（web-deny + CRG fresh）。作为 native cross-repo 难 case 的首次定位，到「崩点 + 方向 + crux」、没到「机制钉死 + 真凶点名」——可接受，非 clean PASS。

---

*审阅遵循「事实 + 逻辑守门」：claim 假 / 逻辑断才 revise。本次 claim 全真、证据链闭合；机制陈述有内部矛盾但报告自己标了存疑点——未达 revise 硬门槛，但非 clean pass。*
