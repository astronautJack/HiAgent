# 日志报错定位报告：commons-upload-rotation-crash

> 由 `/diag` 编排生成（log-parser → wiki-reader → code-tracer 反向回溯 → 独立审阅）。
> 代码仓：`apps-android-commons`　日志：`log/commons-upload-rotation-crash.log`

## 结论速览

| 项 | 值 |
|---|---|
| **claimed_error** | `kotlin.UninitializedPropertyAccessException: lateinit property pendingUploadsPresenter has not been initialized` |
| **崩溃抛出点（症状）** | `app/src/main/java/fr/free/nrw/commons/upload/PendingUploadsFragment.kt:150`（`pauseUploads()` 读取未初始化的 `pendingUploadsPresenter`，属性声明在 `:32`） |
| **根因（缺陷代码行）** | `app/src/main/java/fr/free/nrw/commons/upload/UploadProgressActivity.kt:77`（`setTabs()` 无条件 `PendingUploadsFragment()` 重建实例，未做 `savedInstanceState` 守卫） |
| **confidence** | 高（证据链闭合，3 重印证：栈帧 + 源码 + 日志触发信号） |

## digest_preview（logscope-triage 输出）

- `line_count` 28 / `cluster_count` 9 / `new_cluster_ids`: 108–114
- claimed_error 截断：`...E AndroidRuntime: kotlin.UninitializedPropertyAccessException: lateinit property pendingUpl...`
- 关键簇：
  - **#110** — 异常本体
  - **#111** — 栈帧集合，`size` 20，`rep`=`getPendingUploadsPresenter(PendingUploadsFragment.kt:32)`
  - **#108** — `CONFIGURATION_CHANGED — orientation changed (portrait → landscape)`
  - **#109** — `UploadProgressActivity: updateMenuItems: rebuilding menu after configuration change`
  - **#114** — `USER_COMMENT=I hit the pause button ...`

## 证据链（反向回溯 callers_of）

```
菜单点击(R.id.pause_icon) onClick
  └─ UploadProgressActivity.kt:122   pendingUploadsFragment!!.pauseUploads()     [updateMenuItems 内 lambda]
       └─ PendingUploadsFragment.kt:150  pauseUploads() = pendingUploadsPresenter.pauseUploads()
            └─ PendingUploadsFragment.kt:32   lateinit var pendingUploadsPresenter   ← 抛 UninitializedPropertyAccessException
```

CRG `callers_of pauseUploads` 确认唯一真实调用点 = `UploadProgressActivity.updateMenuItems:122`（`updateMenuItems` 的调用方：`onCreateOptionsMenu:90`、`onPageSelected:60`、`setPausedIcon:200`、`hidePendingIcons:191`、`setErrorIconsVisibility:209`）。`setTabs` 的唯一运行期调用方 = `onCreate:68`。

## 根因机制（为什么未初始化）

1. **注入时机**：`PendingUploadsPresenter` 为 `@Inject lateinit`（`PendingUploadsFragment.kt:32`），由 `CommonsDaggerSupportFragment.onAttach → inject()`（`CommonsDaggerSupportFragment.kt:21–23,46`）字段注入；首次使用在 `onCreateView:58` 的 `pendingUploadsPresenter.onAttachView(this)`。**只有被加进 FragmentManager、走过 onAttach 的实例才会被注入。**

2. **配置变更触发崩溃路径**（与日志 #108/#109/#114 逐一对应）：
   - 旋屏 `portrait→landscape`（#108）→ Activity 销毁重建。
   - `onCreate:36` → `setTabs:68` → `setTabs:77` **无条件 `PendingUploadsFragment()` 新建一个 fragment**，赋给字段 `pendingUploadsFragment` 并塞进 adapter 的 `fragmentList`。
   - 但 `ViewPagerAdapter extends FragmentPagerAdapter`（`ViewPagerAdapter.kt:12`），其 `instantiateItem` 用 `makeFragmentName` + `FragmentManager.findFragmentByTag` **优先恢复旧实例**（配置变更后 FragmentManager 恢复的是先前已注入、已建好 view 的旧 fragment）。`getItem()`（返回 `fragmentList` 里的新实例）仅在「无旧 fragment」时调用——旋转重建时不会被调。
   - 结果：**字段 `pendingUploadsFragment` 指向新建的孤儿实例**（从未进 FragmentManager → onAttach 未跑 → 注入未发生 → `pendingUploadsPresenter` 保持未初始化），而屏上实际显示的是恢复的旧实例。两者是不同对象。
   - 用户点暂停（#114）→ lambda 调 `pendingUploadsFragment!!.pauseUploads()`（`:122`）作用在孤儿实例上 → `:150` 读 `pendingUploadsPresenter` → 抛异常。

3. **`savedInstanceState` 缺守卫**：`onCreate:36` 与 `setTabs:76` 均未判 `savedInstanceState != null`，导致每次重建都造新实例而非复用恢复的 fragment（标准修复模式是 `savedInstanceState` 非空时跳过 `setTabs` 或用 `findFragment` 取回）。

## 修复方向（供人审后实施）

- **主修**：`UploadProgressActivity.onCreate` 在 `savedInstanceState == null` 时才 `setTabs()`；否则从恢复的 fragment 取回引用（或改用 `supportFragmentManager.findFragmentByTag` / 按 id 取）。
- **兜底加固**：菜单 lambda（`:122`/`:136`/`:150`/`:164`/`:177`）访问 `pendingUploadsFragment!!` 前判空或确保引用指向恢复实例。
- **同类风险**：`failedUploadsFragment`（`:25`/`:78`）有完全对称的缺陷，建议一并修。

## 存疑点

无。栈帧、源码生命周期、注入机制、日志触发信号三者一致。

---

*报告生成于 `/diag` 工作流；按编排约定，此报告即人审 checkpoint 边界，批准后方可进入 implement/fix 阶段。*
