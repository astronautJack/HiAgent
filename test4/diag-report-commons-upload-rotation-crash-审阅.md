# test4 /diag 报告审阅 — commons-upload-rotation-crash

> 审阅对象：`diag-report-commons-upload-rotation-crash.md`（test4，commons-app #6433 pre-fix）  
> 对照：已知答案 PR [#6532](https://github.com/commons-app/apps-android-commons/pull/6532)（旋转后暂停上传崩溃）  
> 审阅方式：读报告 + 源码/日志验真（`PendingUploadsFragment.kt` / `UploadProgressActivity.kt` / `ViewPagerAdapter.kt` / `CommonsDaggerSupportFragment.kt` 已逐行核实）  
> 注：`/diag` 职责是**定位 bug**（根因 file:line + 机制 + 证据链），**修 bug 是另一 workflow**——修复建议简略是预期边界，不在苛责范围。本审阅只评「定位」质量。

## 总体结论

**定位准、机制深、证据闭合——是一份高质量的 /diag 产出。** 报告没停在症状层（`UninitializedPropertyAccessException` @ `PendingUploadsFragment.kt:150`），而是挖到真正的根因：`UploadProgressActivity.kt:77` `setTabs()` 造了个孤儿 fragment 实例塞进字段，旋转后 pager 恢复的是另一个实例，字段指向的孤儿从未走 `onAttach` → Dagger 注入未发生 → presenter 未初始化 → 菜单 lambda 调字段实例的 `pauseUploads()` 即抛异常。这套机制经源码逐行核实为真，与 PR #6532 维护者反复调试后的结论（stale reference，**非**注入时机/竞态）一致。

## 已核实正确

| 项 | 报告值 | 核实 |
|---|---|---|
| claimed_error | `UninitializedPropertyAccessException: lateinit property pendingUploadsPresenter has not been initialized` | ✅ 与日志 :5 一致 |
| 崩溃抛出点（症状） | `PendingUploadsFragment.kt:150` = `pauseUploads() = pendingUploadsPresenter.pauseUploads()` | ✅ 源码 :150 一致；日志 :7 栈帧一致 |
| presenter 声明 | `@Inject lateinit` 在 `:31–32` | ✅ 源码 :31–32；日志 :6 `getPendingUploadsPresenter(PendingUploadsFragment.kt:32)` |
| 根因行 | `UploadProgressActivity.kt:77` = `pendingUploadsFragment = PendingUploadsFragment()`（无条件新建） | ✅ 源码 :77 一致 |
| onCreate→setTabs | `onCreate:36` → `setTabs:68`，均无 `savedInstanceState` 守卫 | ✅ 源码 :36/:68/:76–85 均无判 |
| 菜单 lambda | `:122 pendingUploadsFragment!!.pauseUploads()` | ✅ 源码 :122；日志 :8 栈帧一致 |
| 其他 `!!` 访问点 | `:136`/`:150`/`:164`/`:177` | ✅ 源码逐一对应 |
| Dagger 注入时机 | `CommonsDaggerSupportFragment.onAttach:21–23 → inject():35–47`，`fragmentInjector.inject(this):46` | ✅ 源码一致——「只有走过 onAttach 的实例才被注入」成立 |
| FragmentPagerAdapter 行为 | `ViewPagerAdapter:12 extends FragmentPagerAdapter`；`getItem:25 = fragmentList[position]`；`instantiateItem`（继承自父类）用 `findFragmentByTag` 优先恢复旧实例，`getItem` 仅在无旧实例时被调 | ✅ 源码 :12/:25 一致；`instantiateItem`/`makeFragmentName` 为 FragmentPagerAdapter 标准行为，报告正确归因父类 |
| 同类风险 | `failedUploadsFragment` 对称缺陷（`:25`/`:78`） | ✅ 源码 :25 字段 / :78 新建；PR #6532 评论中 Ritika 已实测确认 FailedUploads 同崩 |

## 定位维度的审阅（仅评 /diag 职责内）

### ✅ 没停在症状层（mask vs 真根因）
表面症状是 `:150` 抛 `UninitializedPropertyAccessException`。浅报告会停在「presenter 没初始化，改 nullable 兜底」——这正是 PR 作者**最初**的错误方向（被 reviewer Ritika 打回：「Do you think the presenter should be null by design?」）。报告直接挖到**为什么没初始化**：字段指向的实例从未走过 onAttach。这是真根因，不是 mask。

### ✅ 机制经源码逐行证实
报告的「孤儿实例」机制四环全部落地：(1) `setTabs:77` 造新实例塞字段；(2) pager 继承的 `instantiateItem` 用 tag 恢复另一个实例，不调 `getItem`；(3) 字段实例从未进 FragmentManager → `onAttach` 没跑 → `inject()` 没调；(4) 菜单 lambda 作用在字段实例上 → 读未初始化 presenter → 抛。每一环都有源码行支撑。

### ✅ 证据链闭合
日志栈帧（`:6` → `:7` → `:8`）= 报告反向回溯链（`:32` → `:150` → `:122`）的逆序，逐环对应。

## reviewer 的表现

报告 `## 存疑点: 无` → reviewer 判 `verdict=pass` 放行。**放行正确**——报告定位准、机制真、证据闭合，无事实假、无逻辑断点，无需 revise。

## 一点温和观察（非失分）

报告「根因机制」段把旋转后 pager 恢复的实例描述为「先前已注入、已建好 view 的旧 fragment」——严格说配置变更后 FragmentManager **重建的是新实例**（走 onAttach 再注入），非字面旧实例。但这不影响机制成立（重建实例仍走 onAttach → 注入 → presenter 初始化，与日志实测一致），不构成失分。

---

*审阅遵循「事实 + 逻辑守门」：claim 假 / 逻辑断才 revise；不搞 hindsight 评分、不强制 hedge 风格、不把构建配置/hard gate 边界外期望当核心门槛。*
