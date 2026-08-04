# Bug-Trace 报告 — `rnscreens-pullTransaction-sigsegv.log`

> 生成方式：`/diag` 编排（log-parser → code-tracer 反向回溯 + 证据链闭环校验）。
> 状态：**已定位，未进入 fix 流程**（人审决定归档为报告）。

## 一、定位结果

| 字段 | 值 |
|---|---|
| **崩溃文件** | `react-native/packages/react-native/ReactCommon/react/renderer/mounting/MountingCoordinator.cpp` |
| **崩溃行** | **line 124**（主嫌疑）/ line 102-103（次候选，二者同经 `mountingOverrideDelegate` 虚分发） |
| **置信度** | **high** — 崩溃点 + 调用链 + 根因机制三重闭合；残差见「存疑点」 |
| **claimed_error** | `Fatal signal 11 (SIGSEGV), code 2 (SEGV_ACCERR), fault addr 0xe500000009 in tid <mqt_v_js>` |

## 二、错误摘要（digest_preview）

- **信号**：SIGSEGV / SEGV_ACCERR @ `0xe500000009` — Cause: **trying to execute non-executable memory**。
- **PC 位置**：`[anon:scudo:primary]`，最近符号化帧 `MountingCoordinator::pullTransaction(bool) const+524`。
- **触发场景**：app 进程 stop→launch 循环（surface 切换），崩溃发生在启动约 8s 后、JS 线程。
- **backtrace（已符号化）**：

  ```
  #00  scudo:primary
  #01  MountingCoordinator::pullTransaction(bool) const+524
  #02  FabricUIManagerBinding::schedulerDidFinishTransaction+72
  #03  Scheduler::uiManagerDidFinishTransaction+100
  #04  UIManager::shadowTreeDidFinishTransaction+116
  #05  ShadowTree::mount+144
  ```

- **来源**：leon-zym/plogkit #54；同签名 issue software-mansion/react-native-screens #4151。
- **digest 规模**：15 行 / 12 cluster（全部 new: id 115–126）。

## 三、证据链（闭合）

### 3.1 崩溃点定位

`MountingCoordinator.cpp:71` 定义 `pullTransaction`；函数体内的 override-delegate 循环（line 100-130）有两处通过 `mountingOverrideDelegate` 的虚调用：

- `shouldOverridePullTransaction()`（line 102-103）
- `pullTransaction(...)`（line 124）

PC 落入 scudo 堆 + "execute non-exec memory" = **虚分发跟随了悬空/损坏 vtable**。+524 字节偏移（≈131 条 ARM64 指令）越过 prologue/base-case 后正落在该循环虚分发处。

### 3.2 调用链确认（log frames #02–#05 全部在源码中命中）

| frame | 符号 | 源码位置 |
|---|---|---|
| #02 | `FabricUIManagerBinding::schedulerDidFinishTransaction` | `FabricUIManagerBinding.cpp:622`（:631 / :675 调 `mountingCoordinator->pullTransaction()`） |
| #03 | `Scheduler::uiManagerDidFinishTransaction` | `Scheduler.cpp:303` |
| #04 | `UIManager::shadowTreeDidFinishTransaction` | `UIManager.cpp:659`（`delegate_->uiManagerDidFinishTransaction`） |
| #05 | `ShadowTree::mount` | `ShadowTree.cpp:476` |

### 3.3 根因机制 — 已文档化的 use-after-free

- **`ReactNativeFeatureFlags.h:263`** 明文：guard 围绕 `Scheduler::uiManagerDidDispatchCommand` / `uiManagerDidFinishTransaction`，防止 "queued rendering-update lambdas 在 SchedulerDelegate 被销毁后解引用它（use-after-free）"。
- **`Scheduler.cpp:316-332`**：Android 路径（`!mountSynchronously`）把 lambda 经 `runtimeScheduler_->scheduleRenderingUpdate` 排队，捕获裸 `delegate = delegate_`；仅当 `enableSchedulerDelegateInvalidation()` 开启时才以 `if (guardEnabled && *invalidated) return` 防护。
  → **flag 关闭或该路径未覆盖 override-delegate 时，悬空分发无防护 → 崩溃**。
- **生命周期解耦**：override delegate 由 `Scheduler` / `ReactHost` / `NativeAnimatedNodesManagerProvider` 持 `shared_ptr`（`Scheduler.cpp:164`、`NativeAnimatedNodesManagerProvider.cpp:108`、`ReactHost.h:116`），但只以 `weak_ptr` 注册进 `MountingCoordinator`（`MountingCoordinator.h:133`）。
  rapid stop→launch（`FabricUIManagerBinding::stopSurface` @ `:392`）下强引用释放，而 `pullTransaction` 仍在 JS 线程飞行 → 悬空 vtable。

## 四、存疑点（非阻断残差）

1. **+524 字节偏移无法逐指令符号化** — log 自述「全 tombstone 在 reporter 本机未公开」「前 22 个 native frame 无 app 自有符号」。故 line 124 vs 102-103 的精确二选一无法钉死；但两候选同经 `mountingOverrideDelegate` 虚分发，**根因类与定位不因此改变**。
2. **`delegate.Lock()` 局部保活为何失效** — 若为标准 `std::weak_ptr::lock`，局部 `shared_ptr` 应保活对象；实际崩溃说明存在**越过该保活的并发析构/控制块竞态或 vtable 损坏**。精确子机制需完整 tombstone + 运行时复现方能钉死。

## 五、建议下一步（未执行，待后续决策）

- 在复现环境开启 `enableSchedulerDelegateInvalidation()` flag，验证是否消解崩溃；
- 若仍现 → 审计 `mountingOverrideDelegates_` 注册/注销与 `stopSurface` 的时序竞态（`setMountingOverrideDelegate` 未提供 unregister 接口，weak_ptr 失效窗口即漏洞面）；
- 取得完整 tombstone 后逐指令符号化 +524 偏移，钉死 line 124 vs 102-103。

---

**报告生成时间**：2026-07-30
**工作流**：`/diag`（log-parser → wiki-reader 跳过（本仓无业务流页） → code-tracer 单次回溯证据闭合，未触发 reviewer loop）
**决定**：不进入 fix 流程，归档为报告。
