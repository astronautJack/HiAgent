# 标准答案索引

每个测试用例的期望诊断结果（根因 + 证据链 + 修复方向）。`*.md` 是 diag/bug-trace 报告，`*-审阅.md` 是对报告的独立审阅。

## 用例与答案

| 用例 | 日志 | 代码库 | 标准答案 | 根因 |
|---|---|---|---|---|
| test3 | `../test3/log/NewPipe.nightly.log.d0cba707e674.txt` | `../test3/codebase/NewPipe` | `test3-NewPipe-nightly.md` (+审阅) | `Localization.java:379` — `PrettyTime` 缺 `en_US` 资源包 → `MissingResourceException` → App 创建崩溃 |
| test4 | `../test4/log/commons-upload-rotation-crash.log` | `../test4/codebase/apps-android-commons` | `test4-commons-upload-rotation-crash.md` (+审阅) | `UploadProgressActivity.kt:77` — `setTabs()` 无 `savedInstanceState` 守卫，无条件重建 `PendingUploadsFragment` → `pendingUploadsPresenter` lateinit 未初始化 |
| test5 | `../test5/log/rnscreens-pullTransaction-sigsegv.log` | `../test5/codebase/{react-native,react-native-screens}` | `test5-rnscreens-pullTransaction-sigsegv.md` (+审阅) | `MountingCoordinator.cpp:124` 虚分发到悬空 delegate（`RNSScreenRemovalListener` 归 GC 持有的 `NativeProxy`，无注销路径）→ 跨线程 race → SIGSEGV；对应上游 PR [#4413](https://github.com/software-mansion/react-native-screens/pull/4413) |

## 评分口径

- **根因行准确**：定位到首个状态偏离点（非仅崩溃抛出点）。
- **证据链闭合**：log + code + CRG 多源印证，无虚构边。
- **机制自洽**：与语言/库语义一致（如 test5 的 `make_shared` + `weak_ptr::lock` 语义）。
- **审阅通过**：独立 reviewer 在隔离上下文复现判断且无实质矛盾。
