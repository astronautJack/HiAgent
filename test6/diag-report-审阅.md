# test6 /diag 报告审阅 — rnscreens pullTransaction SIGSEGV（主会话编排版）

> 审阅对象：`diag-report.md`（test6，react-native-screens #4151，主会话编排 /diag 产出）  
> 对照：已知答案 PR [#4413](https://github.com/software-mansion/react-native-screens/pull/4413) + imdrak 独立验证评论（Jul 30）  
> 审阅方式：读报告 + 源码验真（MountingCoordinator.cpp / FabricUIManagerBinding.cpp / Scheduler.cpp / RNSScreenRemovalListener.cpp / NativeProxy.cpp 已验）+ PR #4413 交叉对照  
> 注：本次为**主会话编排版**（`subtask: false` + 编排契约 + 根 .opencode 冲突已清），/diag 真跑在主会话、Task 串 subagent 通了。  
> `/diag` 职责是定位 bug；修复建议简略是预期边界。

## 总体结论

**部分通过——崩点定位准、delegate 真凶点名对、vtable dispatch 候选 A 经 PR #4413 + imdrak 反汇编确证；但根因机制（同线程重入）判断错——实际是 Java GC finalizer 跨线程 race + `weak_ptr::lock()` 对已回收控制块返回 non-null。修复方向（snapshot/re-lock + async dispatch）也随之偏——实际修法是 listener 改进程级单例（永不被 GC 回收 → weak_ptr 永远有效）。** 比 test5 首跑（grep fallback + Exa 污染）显著进步：主会话真跑编排、CRG callers_of 用上（非 grep fallback）、web-deny 生效、reviewer 独立审通。

## 已核实正确

| 项 | 报告值 | 核实 |
|---|---|---|
| 崩溃符号 | `MountingCoordinator::pullTransaction(bool) const` @ `:71` | ✅ 栈帧 #01 唯一对应；PR #4413 确认 |
| 调用链 #05→#00 | ShadowTree::mount → UIManager → Scheduler → FabricUIManagerBinding → pullTransaction | ✅ 5 符号 grep + Read 全对上源码行；PR #4413 同链 |
| 解引用候选 A | `:103` `shouldOverridePullTransaction()` vtable dispatch | ✅ **PR #4413 + imdrak 反汇编确证**：+524 = `ldr x8,[x8]; blr x8` = `shouldOverridePullTransaction()` 虚分发，候选 A 正确 |
| 真凶 delegate | `RNSScreenRemovalListener`（归 `NativeProxy` shared_ptr 持有） | ✅ **PR #4413 明确**：`RNSScreenRemovalListener` owned by `NativeProxy`（fbjni HybridClass）；imdrak 独立 instrumented 注册 + register x0 匹配确证 |
| `mountingOverrideDelegates_` append-only | `setMountingOverrideDelegate` 只 insert 不 erase | ✅ PR #4413：「core has no `removeMountingOverrideDelegate` (as of 0.87)」 |
| `weak_ptr::lock()` 行为 | 报告说 lock 返回 null → 短路跳过；返回非 null → 局部 shared_ptr 持活 | ⚠️ **报告对标准语义的理解正确，但对实际 bug 行为判断错**：imdrak 确认 `weak_ptr::lock()` 对已回收控制块**返回 non-null**（`tbz` 被取为 non-null），不是返回 null |
| 触发 | app stop→launch surface-switch；`mqt_v_js`；~8s 后崩 | ✅ PR #4413 + imdrak 确认 |
| `[anon:scudo:primary]` = 回收堆 | Scudo allocator primary heap，RW 非 RX | ✅ PR #4413 确认「recycled heap」 |
| `libreactnative.so` stripped prebuilt | +NNN 字节偏移，无源行 | ✅ imdrak 用 RN 0.85.3 prebuilt 反解出 +520/+524 指令 |

## 根因机制 vs PR #4413——偏差

| | 报告假设（§4.3） | PR #4413 真根因 |
|---|---|---|
| 线程模型 | **同线程重入**：`RNSScreenRemovalListener.pullTransaction → listenerFunction_ → JNI notifyScreenRemoved → 同步 teardown → 中途 mutate/destroy delegates` | **跨线程 race**：Java GC finalizer 线程在不可预测时序销毁 `NativeProxy`（→ `RNSScreenRemovalListener` 的 C++ 半），而 JS 线程仍在迭代 `mountingOverrideDelegates_` |
| `weak_ptr::lock()` | 标准 C++ 语义：属主已 reset → 返回 null → 短路；reset 前 → 返回非 null → 局部 shared_ptr 持活 | **控制块本身被 Scudo 回收** → `lock()` 读到回收后的控制块，**返回 non-null 但对象已不存在** → 虚分发跳进回收堆 |
| 「教科书应挡住」 | ✅ 诚实承认：标准 shared_ptr + scoped_lock 下此路径不应崩 | ✅ PR #4413 同结论：标准语义应挡住；崩了说明存在**绕过标准语义的底层 race**（控制块回收后 lock 读到非 null） |
| 绕过点 | 同线程重入（JNI 同步回调驱动就地 teardown） | **控制块回收 race**（GC finalizer 线程释放对象 + Scudo 回收控制块内存 + JS 线程 lock 读到回收后的非 null 值）——不是重入，是**内存安全 race** |

**偏差根因**：报告在 §4.3 诚实承认「教科书应挡住」后，推测唯一的绕过路径是同线程重入（JNI 同步回调）。但实际绕过更底层——不是代码级重入，而是 **`weak_ptr::lock()` 对已回收控制块返回 non-null**（allocator 级 race）。报告缺前导帧 #06-#21（tombstone 未公开），无法看到真正的 destroyer（GC finalizer），只能从代码级推断重入——这是一个合理的但错误的推断。

## 修复方向 vs PR #4413——偏差

| | 报告 P0/P1 | PR #4413 实际修法 |
|---|---|---|
| P0（解引用点） | snapshot delegates 拷贝 + 每次调用前再验活 | ❌ 不对症：问题不是 vector 中途 mutate，是 `weak_ptr::lock()` 对回收控制块返回 non-null——snapshot + re-lock 不改变 lock 的行为 |
| P1（重入根治） | `listenerFunction_` 异步派发（离开 pull-transaction 关键路径） | ❌ 不对症：根因不是重入，是 GC finalizer 跨线程销毁 listener |
| **PR #4413 实际** | — | **listener 改进程级单例**（function-local static `shared_ptr` in `NativeProxy.cpp`）→ 永不被 GC 销毁 → `weak_ptr` 永远 lock 到活对象 → 虚分发永远落在活 vtable 上。**callback 捕获 JNI global ref by value（不捕获 `this`）** → 即使 `NativeProxy` 被 GC 回收，callback 不解引用 `this`。`setListener` 返 monotonic token；`invalidateNative()` 用 token disarmed（防 stale proxy 的 late teardown） |

报告的 P0/P1 **方向偏**——但原因是缺前导帧（#06-#21 未公开），无法看到 GC finalizer 这个真正的 destroyer。报告在 §7 诚实标注了「根因可能落在未示出的前导帧」——这个 caveat 被验证了。

## 新增确证（imdrak 独立验证，报告完成后公开）

imdrak（Jul 30）的评论提供了报告缺失的关键证据：

1. **+520/+524 指令解析**：`ldr x8, [x8]`（vtable[0]）@ +520；`blr x8`（虚分发）@ +524 = **`shouldOverridePullTransaction()` dispatch**——报告候选 A（`:103`）**确证正确**。
2. **`weak_ptr::lock()` 返回 non-null**：`tbz`（在 +520 前）被取为 non-null → 确认 lock 对回收控制块返回非空值——报告的「lock 返回 null → 短路」假设在此 bug 下**不成立**。
3. **两种 fault 签名**：+524 `SEGV_ACCERR` @ scudo:primary（执行非可执行堆）AND +520 `SEGV_MAPERR` @ `0x0`（null deref）——同一个 bug，取决于回收块内容。报告只覆盖了 +524 签名。
4. **instrumented 注册匹配**：imdrak instrumented 注册点 + 比较崩溃时 `x0` 寄存器与已注册指针——**精确匹配 `RNSScreenRemovalListener`**。报告的「首选嫌疑」判断正确。
5. **修复验证**：4.25.2 + PR patch → 88/88 零崩（vs 未修 6/128 = 4.7% 崩率）。

## reviewer 表现

报告 workflow：主会话 → Task code-graph（建图）→ Task log-parser → Task code-tracer（写报告）→ Task code-tracer-reviewer（独立审）→ 报告。**主会话编排通了**——subagent 真 Task 调起（不再 inline 崩），reviewer 独立审。

reviewer 放行了这份报告。**合理履职**——claim 全真（file:line 验真、调用链闭合）、证据链闭合、候选 A/B 诚实标注 MEDIUM、缺失帧 caveat 诚实。根因机制（重入 vs GC-finalizer-race）的偏差在「缺前导帧」的前提下是合理的推断错误——reviewer 本可对「同线程重入假设缺直接证据（无前导帧，无 JNI 调用栈确证）」标存疑，但整体放行不算失职。

## 一句话裁决

**部分通过**：崩点 + delegate 真凶 + vtable 候选 A **全对**（经 PR #4413 + imdrak 独立确证）；但根因机制（同线程重入）**错**——实际是 Java GC finalizer 跨线程 race + `weak_ptr::lock()` 对回收控制块返回 non-null。修复方向随之偏（snapshot/re-lock vs 进程级单例）。**主会话编排跑通**（vs test5 首跑 subtask 崩 + test6 首跑旧 .opencode 冲突）——这是 HiAgent /diag 工作流的**首次完整跑通**（主会话 → Task 串 subagent → 独立 reviewer → 报告），尽管根因机制有偏差。

---

*审阅遵循「事实 + 逻辑守门」：claim 假 / 逻辑断才 revise。本次 claim 全真、证据链闭合；根因机制推断在缺前导帧前提下合理但错误——未达 revise 硬门槛（claim 没假），但非 clean pass。*
