# /diag 报告 — rnscreens pullTransaction SIGSEGV

- 日志: log/rnscreens-pullTransaction-sigsegv.log
- 仓库: test6/codebase @ 07527b7312491d5aa97b5c36b919938d45ef8982 (HEAD)
- CRG: fresh (70999 nodes / 412777 edges, built @ 07527b7312491d5aa97b5c36b919938d45ef8982, age 236s)
- Wiki 上下文: 无（仓库无业务流 wiki / 无 `error_index.md` — 退回源码，无历史经验 augment）

---

## 1. 症状 (digest)

- `claimed_error`: **SIGSEGV, code 2 (SEGV_ACCERR), fault addr 0xe500000009** — 试图执行非可执行内存（jump/call 落在 `[anon:scudo:primary]`，Scudo allocator primary heap，RW 非 RX）。
- 机制推断（digest 派生）：一个 **corrupted/stale 函数指针（vtable / delegate）被解引用**，调用目标指向已释放后回收的堆地址 → 跳到非可执行堆 → SEGV_ACCERR。发生在 mount transaction 期间。
- 崩溃线程: `mqt_v_js`（RN JS 线程）。
- 触发: app stop→launch surface-switch 循环；进程启动后约 8s 崩。RN 0.86.0 / Expo SDK 57 / Fabric / Hermes。Issue refs: leon-zym/plogkit#54, software-mansion/react-native-screens#4151（同签名）。
- 故障帧（caller→callee，#00 为 faulting PC）:
  - #00 `[anon:scudo:primary]` — faulting PC 本身（非可执行堆，无符号）
  - #01 `facebook::react::MountingCoordinator::pullTransaction(bool) const+524` ← **直接故障 caller，+524 深 = 反向回溯主入口**
  - #02 `FabricUIManagerBinding::schedulerDidFinishTransaction(...)+72`
  - #03 `Scheduler::uiManagerDidFinishTransaction(...)+100`
  - #04 `UIManager::shadowTreeDidFinishTransaction(...)+116`
  - #05 `ShadowTree::mount(...)+144`
- 注: `+NNN` = stripped `libreactnative.so` 内**符号起点后的字节偏移**，非源码行号；仅用于排序故障落在符号体何处。

---

## 2. 故障符号定位 (file:line)

| 符号 (#frame) | file:line | 取证来源 |
|---|---|---|
| `MountingCoordinator::pullTransaction(bool) const` (#01) | `react-native/packages/react-native/ReactCommon/react/renderer/mounting/MountingCoordinator.cpp:71` | grep `pullTransaction` → 唯一定义在此；header `MountingCoordinator.h:64` 声明 |
| `FabricUIManagerBinding::schedulerDidFinishTransaction` (#02) | `react-native/packages/react-native/ReactAndroid/src/main/jni/react/fabric/FabricUIManagerBinding.cpp:622` | grep `schedulerDidFinishTransaction`；line 631 调 `pullTransaction(/*willPerformAsynchronously=*/true)` |
| `Scheduler::uiManagerDidFinishTransaction` (#03) | `react-native/packages/react-native/ReactCommon/react/renderer/scheduler/Scheduler.cpp:303` | grep；line 311 转发 `delegate_->schedulerDidFinishTransaction(mountingCoordinator)` |
| `UIManager::shadowTreeDidFinishTransaction` (#04) | `react-native/packages/react-native/ReactCommon/react/renderer/uimanager/UIManager.cpp:653` | grep；line 659 调 `delegate_->uiManagerDidFinishTransaction(...)` |
| `ShadowTree::mount` (#05) | `react-native/packages/react-native/ReactCommon/react/renderer/mounting/ShadowTree.cpp:476` | Read；line 478 `mountingCoordinator_->push`，line 479 `delegate_.shadowTreeDidFinishTransaction` |
| **override-delegate 解引用点（候选 #01 体内故障指令）** | `MountingCoordinator.cpp:103` 与 `:124` | 见 §4 — vtable dispatch 候选 |

CRG 检索: `crg_query_graph_tool callers_of "MountingCoordinator::pullTransaction"` 返回 `not_found`；`crg_semantic_search_nodes_tool` 也返回 0 匹配（CRG 的 tree-sitter C++ 解析对此处带 `const` 限定/全限定名的符号命中不稳）。**退回 grep + 源码 Read 闭合证据链** — grep 直接定位到唯一源定义，逐函数 Read 确认调用边，所有 5 个 #frame 符号在源码中逐级对应、边真实存在。

---

## 3. 反向回溯 (callers_of) — 从 pullTransaction 向外

源码逐级回溯闭合的调用链（caller→callee，与栈帧反向一致）：

```
ShadowTree::mount(revision, mountSynchronously)            [#05] ShadowTree.cpp:476
  └─ mountingCoordinator_->push(revision)                   (ShadowTree.cpp:478)
  └─ delegate_.shadowTreeDidFinishTransaction(mountingCoordinator_, mountSynchronously)  (ShadowTree.cpp:479)
       ↓
UIManager::shadowTreeDidFinishTransaction(...)              [#04] UIManager.cpp:653
  └─ delegate_->uiManagerDidFinishTransaction(...)          (UIManager.cpp:659)
       ↓
Scheduler::uiManagerDidFinishTransaction(mountingCoordinator, mountSynchronously)  [#03] Scheduler.cpp:303
  └─ delegate_->schedulerDidFinishTransaction(mountingCoordinator)  (Scheduler.cpp:311)
       ↓
FabricUIManagerBinding::schedulerDidFinishTransaction(mountingCoordinator)  [#02] FabricUIManagerBinding.cpp:622
  └─ mountingCoordinator->pullTransaction(/*willPerformAsynchronously=*/true)  (FabricUIManagerBinding.cpp:631)  ← 进入 #01
       ↓
MountingCoordinator::pullTransaction(bool) const            [#01] MountingCoordinator.cpp:71  ← +524 故障
  └─ 遍历 mountingOverrideDelegates_，对每个 weak_ptr:
        delegate.lock() → (非空时) 虚函数 dispatch
        └─ shouldOverridePullTransaction()  (MountingCoordinator.cpp:103)  ← vtable 候选 A
        └─ pullTransaction(surfaceId_, number_, telemetry, mutations)  (MountingCoordinator.cpp:124)  ← vtable 候选 B
             ↓
       #00 跳到 [anon:scudo:primary]（非可执行堆）→ SIGSEGV
```

**线程归属确认**: `MountingCoordinator.h:58-60` 注释 + `FabricUIManagerBinding.cpp:628-630` 注释均明确："Android 不遵循同步模型，从 **JS 线程**调用 `pullTransaction`，再异步在 UI 线程 mount。" → 与崩溃线程 `mqt_v_js` 完全吻合。`pullTransaction(true)`（willPerformAsynchronously=true，FabricUIManagerBinding.cpp:632）签名亦与 #01 的 `pullTransaction(bool)` 一致。

**谁在 stop→launch surface-switch 期间把 override delegate 注册进此管线**（grep `setMountingOverrideDelegate`）：

1. **rnscreens `RNSScreenRemovalListener`**（首选嫌疑，语义=屏幕移除/导航，与触发完全吻合）:
   - 定义: `react-native-screens/cpp/RNSScreenRemovalListener.h:9` / `.cpp:5`，`struct RNSScreenRemovalListener : public MountingOverrideDelegate`。
   - 注册: `react-native-screens/android/src/main/cpp/NativeProxy.cpp:82` `coordinator->setMountingOverrideDelegate(screenRemovalListener_)`，遍历所有 shadowTree 注册（`NativeProxy.cpp:47-52`）。
   - 持有: `NativeProxy::screenRemovalListener_` 为 `std::shared_ptr<RNSScreenRemovalListener>`（`NativeProxy.cpp:36-42`，`make_shared` 一次性创建）。
   - 回调语义: 其 `pullTransaction`（`RNSScreenRemovalListener.cpp:5-25`）在发现 `Remove` 型 `RNSScreen` mutation 时调 `listenerFunction_(tag)`（line 19）→ 该 function 捕获 `[this]`（NativeProxy*，`NativeProxy.cpp:37`）→ JNI `notifyScreenRemoved`（`NativeProxy.cpp:38-41`）。**即：屏幕移除时它会同步回调 Java 层通知** —— 这是 surface-switch 期间驱动进一步生命周期的钩子。

2. **RN Android 自有 `LayoutAnimationDriver`**:
   - 持有: `FabricUIManagerBinding::animationDriver_` 为 `std::shared_ptr<LayoutAnimationDriver>`（`FabricUIManagerBinding.h:153`；`make_shared` 于 `FabricUIManagerBinding.cpp:591`）。
   - 注册: surface start 时 `setMountingOverrideDelegate(animationDriver_)`（`FabricUIManagerBinding.cpp:152/212/386`），由 `ReactNativeFeatureFlags::enableLayoutAnimationsOnAndroid()` gate。
   - 释放: `uninstallFabricUIManager()`（`FabricUIManagerBinding.cpp:597-608`）置 `animationDriver_ = nullptr`（line 605）→ 共享 ptr 归零。

两条注册路径都把 weak_ptr 插入同一个 `MountingCoordinator::mountingOverrideDelegates_`（`vector<weak_ptr<const MountingOverrideDelegate>>`，`MountingCoordinator.h:133`）。`setMountingOverrideDelegate`（`MountingCoordinator.cpp:210-215`）**只 insert、从不 erase**；`revoke()`（`MountingCoordinator.cpp:54-62`）也不清空该 vector。但 `MountingCoordinator` 是**每 surface/ShadowTree 一个**（构造于 `MountingCoordinator.cpp:25`），新 surface 得空 vector 重新注册，故"跨 surface 累积陈旧 weak_ptr"在 per-coordinator 维度不成立 —— 陈旧性须来自"持有 shared_ptr 的属主在 stop→launch 期间被释放，而 pullTransaction 仍在 mqt_v_js 在途"。

---

## 4. 根因假设 + 证据链

### 4.1 解引用点定位（HIGH — 符号；MEDIUM — 确切指令）

`pullTransaction` 体（`MountingCoordinator.cpp:71-189`）内**所有间接调用（vtable / 函数指针 / std::function dispatch）候选**，按 +524 偏移深度与"跳到非可执行堆=被解引用的函数指针指向已释放堆"语义排序：

| 候选 | file:line | 类型 | 评级 |
|---|---|---|---|
| A | `MountingCoordinator.cpp:103` `mountingOverrideDelegate->shouldOverridePullTransaction()` | **虚函数（vtable）** dispatch on `MountingOverrideDelegate` | 首选 |
| B | `MountingCoordinator.cpp:124` `mountingOverrideDelegate->pullTransaction(surfaceId_, number_, telemetry, std::move(mutations))` | **虚函数（vtable）** dispatch on `MountingOverrideDelegate` | 首选（更深，+524 偏移更可能落此） |
| C | `MountingCoordinator.cpp:87-88` `calculateShadowViewMutations(*baseRevision_.rootShadowNode, *lastRevision_->rootShadowNode)` | 遍历多态 `ShadowNode`（其内部虚调用） | 次选 |
| D | `MountingCoordinator.cpp:181` `LowPriorityExecutor::execute([toDelete=std::move(baseRevision_)](){})` | std::function 间接调用 | 次选 |

digest 显式将机制判为"corrupted/stale 函数指针（vtable / delegate）"，与候选 A/B（override delegate vtable）语义最契合。无二进制/反汇编，A/B 之间不可二分（+524 偏移在 stripped release 优化体里无法精确映射到源行）。

### 4.2 指针属主 + 陈旧条件

- **指针属主**: `MountingOverrideDelegate` 实现对象（rnscreens `RNSScreenRemovalListener` 由 `NativeProxy::screenRemovalListener_` shared_ptr 持有；RN `LayoutAnimationDriver` 由 `FabricUIManagerBinding::animationDriver_` shared_ptr 持有）。`MountingCoordinator` 只持 weak_ptr。
- **陈旧条件（触发）**: app stop→launch surface-switch 期间 ——
  - `FabricUIManagerBinding::uninstallFabricUIManager()`（line 605）置 `animationDriver_=nullptr` → `LayoutAnimationDriver` 引用归零、对象释放。
  - rnscreens `NativeProxy` TurboModule 随实例 teardown 被销毁 → `screenRemovalListener_` shared_ptr 销毁 → `RNSScreenRemovalListener` 释放。
  - 而此时 mqt_v_js 上一个 `pullTransaction`（经 #05→#01 链）**仍在途**，正遍历 `mountingOverrideDelegates_` 并对其做 vtable dispatch（A/B）。
  - 释放后的堆被 Scudo 回收并再分配为别的小对象，原 vptr 槽（偏移 0）被覆写为某堆指针 → `delegate.lock()` 取到的对象 vptr 为陈旧堆地址 → `blr xN` 跳到非可执行 Scudo primary 堆 → **SEGV_ACCERR @ 0xe500000009，PC 落 `[anon:scudo:primary]`**。症状与机制吻合。

### 4.3 标准守卫为何（应）挡住它 —— 诚实分析

源码层面，该路径在**标准 C++ shared_ptr + std::scoped_lock 语义下看似已被守卫**：
- `MountingCoordinator` 全程被链上 `shared_ptr<const MountingCoordinator>` 参数（`FabricUIManagerBinding.cpp:623` by const-ref，caller `Scheduler.cpp:304` by value）持活 → 不会在 pullTransaction 期间释放 → `mountingOverrideDelegates_` vector 不悬空。
- `delegate.lock()`（`MountingCoordinator.cpp:101`）对控制块原子操作：若属主已 reset 返回 null → `mountingOverrideDelegate &&`（line 102）短路、跳过虚调用；若 reset 前返回非空 → 局部 `mountingOverrideDelegate` shared_ptr 持活对象至迭代结束 → 虚调用（103/124）落在活对象上。
- `revoke()`（`MountingCoordinator.cpp:54-62`）在**同一 `mutex_`** 下 reset `baseRevision_.rootShadowNode`/`lastRevision_`；`pullTransaction` 在 `mutex_`（line 75）下且先 `if (lastRevision_.has_value())`（line 80）再访问 → shadow node 不悬空。

**故：教科书语义下此路径不应崩。** 崩溃 ⇒ 存在绕过这些守卫的真实 bug。最可能绕过点 = **同线程重入**：

> `RNSScreenRemovalListener::pullTransaction`（`RNSScreenRemovalListener.cpp:5`）→ `listenerFunction_(tag)`（line 19）→ JNI `notifyScreenRemoved`（`NativeProxy.cpp:38-41`）→ **同步**在同一个 mqt_v_js 上驱动进一步 surface/instance teardown → 在 `pullTransaction` 的 override 循环仍在迭代时，就地 mutate/destroy `mountingOverrideDelegates_` 或其 delegate 属主 → 陈旧 vptr → 跳堆。

此重入假设与以下证据相洽：(a) 触发是 surface-switch；(b) `RNSScreenRemovalListener` 的全部职责就是"反应屏幕移除"；(c) digest 的"vtable/delegate 解引用"框定；(d) rnscreens issue ref #4151 同签名；(e) `mqt_v_js` 单线程 JS、JNI 同步回调正是重入温床。

### 4.4 证据链置信度

| 环节 | 置信度 | 依据 |
|---|---|---|
| 故障符号 `pullTransaction(bool) const` @ `MountingCoordinator.cpp:71` | **HIGH** | 栈帧 #01 唯一对应源定义 |
| 调用链 #05→#00 在源码逐级闭合 | **HIGH** | 5 个符号 grep + Read 全部对上边 |
| 解引用点是 override-delegate vtable dispatch（A/B 候选） | **MEDIUM** | digest 语义框定 + 体内容观唯一"vtable/函数指针"间接调用；无反汇编不能在 A/B 间二分 |
| 指针属主 = rnscreens `RNSScreenRemovalListener`（首选）/ `LayoutAnimationDriver`（次） | **MEDIUM** | 触发语义 + issue ref 倾向 rnscreens；但 RN 自有 `animationDriver_`（uninstall line 605 释放）亦可能在场 |
| 陈旧机制 = stop→launch 期间属主释放 + 重入绕过守卫 | **MEDIUM** | 与触发/线程/issue 相洽；但"教科书 shared_ptr 应挡住"意味着真实 bug 细节需前导帧确认 |
| `libreactnative.so` stripped prebuilt | **HIGH** | `+NNN` 字节偏移、无源行、无 app 符号 |

---

## 5. 构建开关 / stripping

- **`libreactnative.so`** = RN 0.86 **release prebuilt（stripped）**。证据：所有故障帧仅 `symbol+NNN`（字节偏移，非源行）、无 app 自有符号、报告者明言"前 22 个 native 帧无 app 自有符号"。后果：无法把 +524 精确映射到某条源行/指令（不能在候选 A/B 间二分）；无法获知前导帧 #06-#21（可能含真正的 destroyer / 重入 caller）。
- **`react-native-screens`** = 本仓库**从源码构建**（`react-native-screens/cpp/` + `android/src/main/cpp/`）。后果：若某帧落入 rnscreens，其符号应可解析。但 digest 尾部 0 个 rnscreens 帧（全 libreactnative.so）—— 这与"rnscreens 仅作为已注册 vtable 的**被调用目标**存在"相洽（其代码是虚调用的 target，而非本截断尾的中间帧），或解引用在抵达 rnscreens 代码前即崩（vptr 读陈旧即跳）。
- **构建开关检索**: `react-native` 侧未发现 ProGuard/R8 对 native .so 的剥离配置（native 由 NDK 链接器 strip，非 R8）；`enableLayoutAnimationsOnAndroid()` feature flag 决定 `LayoutAnimationDriver` 是否注册（`FabricUIManagerBinding.cpp:151/211/386`）—— 若该 flag 关闭，`animationDriver_` 不注册、则嫌疑只剩 rnscreens 一条。

---

## 6. 修复建议 (file + exact syntax)

> 原则：**不能改源码**（reviewer 审 apply 性）。给可 apply 的确切补丁，基于 §4 分析。优先级 P0=对症解引用点；P1=根因（重入/属主释放）。前导帧缺失下，P1 需 reviewer/人工据 #06-#21 复核。

### P0 — 解引用点硬防御（`MountingCoordinator.cpp:100-130`）

现状（节选自源，`MountingCoordinator.cpp:100-130`）：
```cpp
  for (const auto& delegate : mountingOverrideDelegates_) {
    auto mountingOverrideDelegate = delegate.lock();
    auto shouldOverridePullTransaction = mountingOverrideDelegate &&
        mountingOverrideDelegate->shouldOverridePullTransaction();

    if (shouldOverridePullTransaction) {
      TraceSection section2("MountingCoordinator::overridePullTransaction");
      ...
      transaction = mountingOverrideDelegate->pullTransaction(
          surfaceId_, number_, telemetry, std::move(mutations));
    }
  }
```

补丁（snap-shot delegates 拷贝 + 每次调用前再验活，阻断"同线程重入 mutate vector / delegate 中途释放"路径）：
```cpp
  // Snapshot the delegate list under the lock so a re-entrant call (e.g. an
  // override delegate's pullTransaction -> JS -> surface teardown on the same
  // JS thread) cannot mutate/destroy mountingOverrideDelegates_ mid-iteration.
  std::vector<std::weak_ptr<const MountingOverrideDelegate>> delegatesSnapshot;
  {
    std::scoped_lock lock(mutex_);
    delegatesSnapshot = mountingOverrideDelegates_;
  }

  for (const auto& delegate : delegatesSnapshot) {
    // Re-lock per dispatch: defend against the delegate being destroyed between
    // the snapshot and the virtual call (stop->launch surface-switch race).
    auto mountingOverrideDelegate = delegate.lock();
    if (!mountingOverrideDelegate) {
      continue;  // delegate expired (owner released) — skip, do not dispatch
    }

    auto shouldOverridePullTransaction =
        mountingOverrideDelegate->shouldOverridePullTransaction();
    if (shouldOverridePullTransaction) {
      TraceSection section2("MountingCoordinator::overridePullTransaction");
      // mountingOverrideDelegate (shared_ptr) keeps the delegate alive across
      // the virtual call below even if its owner is concurrently reset.
      auto mutations = ShadowViewMutation::List{};
      auto telemetry = TransactionTelemetry{};
      if (transaction.has_value()) {
        mutations = transaction->getMutations();
        telemetry = transaction->getTelemetry();
      } else {
        number_++;
        telemetry.willLayout(); telemetry.didLayout();
        telemetry.willCommit();  telemetry.didCommit();
        telemetry.willDiff();    telemetry.didDiff();
      }
      transaction = mountingOverrideDelegate->pullTransaction(
          surfaceId_, number_, telemetry, std::move(mutations));
    }
  }
```

> 注意：此改动改变锁粒度 —— `calculateShadowViewMutations`/`baseRevision_`/`lastRevision_` 访问仍在原 `mutex_` 块内（base case 段保留），仅 override 循环段改为先 snapshot 再释锁迭代。reviewer 应核对与 `push`/`revoke` 的互斥不破坏不变量（`number_` 仍需保护 —— 建议把 `number_` 递增留在锁内，仅 override 迭代段移出锁）。

### P1 — rnscreens 重入根治（`RNSScreenRemovalListener.cpp` / `NativeProxy.cpp`）

若 §4.3 重入假设成立，根治须让 `listenerFunction_` 的 side-effect（`notifyScreenRemoved` → 同步驱动 teardown）**离开 pull-transaction 关键路径**：

```cpp
// RNSScreenRemovalListener.cpp — 收集 tag，异步派发，避免在 pullTransaction 内同步触发 surface 生命周期
std::optional<MountingTransaction> RNSScreenRemovalListener::pullTransaction(
    SurfaceId surfaceId,
    MountingTransaction::Number transactionNumber,
    const TransactionTelemetry &telemetry,
    ShadowViewMutationList mutations) const {
  std::vector<int> removedTags;  // 收集，不在循环内同步回调
  for (const ShadowViewMutation &mutation : mutations) {
    if (mutation.type == ShadowViewMutation::Type::Remove &&
        mutation.oldChildShadowView.componentName != nullptr &&
        std::strcmp(mutation.oldChildShadowView.componentName, "RNSScreen") == 0) {
      removedTags.push_back(mutation.oldChildShadowView.tag);
    }
  }
  // 派发到下一个 runloop / 异步队列，不在此（可能正持有 MountingCoordinator 锁/迭代）同步回调
  if (!removedTags.empty()) {
    listenerFunction_(removedTags);  // 改签名为 vector 或在内部 enqueue
  }
  return MountingTransaction{
      surfaceId, transactionNumber, std::move(mutations), telemetry};
}
```

> P1 为**候选**（标"待验"）—— 根因机制（重入 vs. 属主释放竞态）需前导帧 #06-#21 确认后才定调。reviewer 据缺失帧评估 P1 是否对症。

---

## 7. 信心与未覆盖

**HIGH 置信**:
- 故障符号 = `MountingCoordinator::pullTransaction(bool) const` @ `MountingCoordinator.cpp:71`（栈帧 #01 唯一对应）。
- 调用链 #05→#00 在源码逐级闭合（5 符号 grep+Read 边真实存在）。
- 解引用机制属"vtable/函数指针指向已释放堆"（digest 框定 + `[anon:scudo:primary]` 非可执行 + SEGV_ACCERR 自洽）。
- `libreactnative.so` stripped prebuilt（`+NNN` 偏移、无源行/无 app 符号）。
- 触发线程 `mqt_v_js` = Android JS 线程 pull（header/注释双证）。

**MEDIUM 置信**:
- 解引用确切指令在 A（`:103`）/B（`:124`）之间 —— 无反汇编不能二分。
- 陈旧指针属主首选 rnscreens `RNSScreenRemovalListener`（触发语义 + issue ref +1）；`LayoutAnimationDriver`（`animationDriver_`，uninstall line 605 释放）为次选，亦可能在场。
- 根因机制 = stop→launch 期间属主释放 + **同线程重入**（`RNSScreenRemovalListener.pullTransaction → listenerFunction_ → JNI notifyScreenRemoved → 同步 teardown`）绕过标准 shared_ptr+mutex 守卫。

**缺失帧 caveat（诚实声明）**:
- 完整 tombstone #00–#21 **未公开**；本 digest 仅覆盖 `libreactnative.so` 尾部。**根因可能落在未示出的前导帧**（真正释放 delegate/coordinator 的 destroyer、或重入的 surface-stop caller）。
- 报告者注"前 22 个 native 帧无 app 自有符号" —— 即使前导帧公开，可能仍全为 libreactnative.so（stripped），未必能定位到 rnscreens。

**会提升信心的事项**:
1. 公开完整 tombstone（#00-#21）→ 定位 destroyer/重入 caller，确认或排除 §4.3 重入假设。
2. `enableLayoutAnimationsOnAndroid()` 的运行时取值 → 决定 `LayoutAnimationDriver` 是否注册（若关，嫌疑收敛到唯一 = rnscreens）。
3. `libreactnative.so` 的 symbol map / 反汇编 +524 偏移 → 在候选 A/B（`:103` vs `:124`）间二分。
4. `react-native-screens#4151` 的修复 PR / 复现条件 → 交叉验证 §4.3 机制。
