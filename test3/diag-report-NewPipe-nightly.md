# 日志报错定位报告 — NewPipe nightly

## 根因定位（主）

| 字段 | 值 |
|---|---|
| **file** | `app/src/main/java/org/schabi/newpipe/util/Localization.java` |
| **line** | **379** (`return new PrettyTime(getAppLocale());`) |
| **confidence** | **high**（证据链闭合） |
| **触发入口** | `app/src/main/java/org/schabi/newpipe/App.kt:104` — `Localization.initPrettyTime(Localization.resolvePrettyTime())` |

## claimed_error

日志解析器返回 `claimed_error: null`（无显式声明错误），但 digest 内含 **3 类 FATAL EXCEPTION**。定位选最可代码回溯的一条为主根因：

- **主根因崩溃**：`java.lang.RuntimeException: Unable to create application org.schabi.newpipe.App`，`Caused by: java.util.MissingResourceException: Can't find bundle for base name org.ocpsoft.prettytime.i18n.Resources, locale en_US`（log 行 937/949，cluster 30/33，size 18）
- 次要崩溃（OOM，非单点代码 bug，见末尾「其他崩溃」）

## evidence（证据链，已逐环闭合）

**1. 日志堆栈（cluster 30/33，log 行 935-962）**
```
E AndroidRuntime: FATAL EXCEPTION: main
E AndroidRuntime: java.lang.RuntimeException: Unable to create application org.schabi.newpipe.App
E AndroidRuntime: Caused by: java.util.MissingResourceException:
        Can't find bundle for base name org.ocpsoft.prettytime.i18n.Resources, locale en_US
    at org.ocpsoft.prettytime.impl.ResourcesTimeFormat.setLocale$1(...)
    at org.ocpsoft.prettytime.PrettyTime.addUnit(...)
    at org.ocpsoft.prettytime.PrettyTime.<init>(...)
    at org.schabi.newpipe.util.Localization.resolvePrettyTime(...)   ← NewPipe 帧
    at org.schabi.newpipe.App.onCreate(...)                          ← NewPipe 帧（入口）
```

**2. CRG `callers_of resolvePrettyTime`**（图已建，5835 节点）
- `App.onCreate`（`App.kt`，调用点 **line 104**）✅ 与日志帧 `App.onCreate` 对应
- `MainActivity.onResume`（`MainActivity.java:519`）— 另一调用方（本次崩溃路径未走）

**3. CRG `callees_of resolvePrettyTime`**
- `PrettyTime`（构造函数，调用点 **line 379**）✅ 与日志帧 `PrettyTime.<init>` 对应
- `Localization.getAppLocale`（line 379）

**4. 源码复核**
- `Localization.java:378-380`：
  ```java
  public static PrettyTime resolvePrettyTime() {
      return new PrettyTime(getAppLocale());   // line 379 ← 触发点
  }
  ```
- `App.kt:104`：
  ```kotlin
  Localization.initPrettyTime(Localization.resolvePrettyTime())  // line 104 ← 入口
  ```

**5. 闭合判定**：日志帧 → CRG 边 → 源码行 三者逐一对应，无缺环。根因为 `new PrettyTime(getAppLocale())` 构造时，PrettyTime 库尝试加载 `org.ocpsoft.prettytime.i18n.Resources`（locale en_US）资源包失败——属库资源未正确打包进 APK / 该 locale 资源缺失，异常沿 `resolvePrettyTime → initPrettyTime → App.onCreate` 上抛致应用无法创建。

## digest_preview

```
line_count: 1929 | fed: 1928 | cluster_count: 106 | new_cluster_ids: [] | claimed_error: null
Top 崩溃簇：
  #30 (18×) RuntimeException: Unable to create application org.schabi.newpipe.App
  #33 (18×) Caused by: MissingResourceException: Can't find bundle org.ocpsoft.prettytime.i18n.Resources, en_US
  #9  (20×) FATAL EXCEPTION: ExoPlayer:Playback
  #11 (13×) OutOfMemoryError (Failed to allocate 16 byte ... <1% heap free after GC)
  #75 (49×) FATAL EXCEPTION: main
```

## 其他崩溃（次要，非本次主根因，供参考）

1. **ExoPlayer OOM**（log 行 11-28 / 54-71，cluster 9/11）：`OutOfMemoryError` 发生在 `android.util.Pair.create` → `AbstractConcatenatedTimeline.getConcatenatedUid`（ExoPlayer 库内，r8 行 :1）。堆栈无直接 NewPipe 帧——属库内 timeline 拼接时堆耗尽，根因在 ExoPlayer 库或上游过度累积 media period，非 NewPipe 单点代码行。
2. **动画 OOM**（log 行 72-89，cluster 14）：`OutOfMemoryError` at `org.schabi.newpipe.ktx.ViewUtils$$ExternalSyntheticLambda0.onAnimationUpdate`（`ViewUtils` 的 lambda，r8 行 :17）。属堆耗尽型 OOM，非特定 bug 行；如需深查可沿 `ViewUtils` 的 `onAnimationUpdate` lambda 继续回溯。

## 建议修复方向（待人审批准后实施）

`Localization.resolvePrettyTime()`（Localization.java:379）应捕获/兜底 `MissingResourceException`，或在 PrettyTime 初始化前确保 i18n Resources 资源已随 APK 正确打包（检查 gradle shading/资源包含配置）。入口 `App.kt:104` 可加保护避免应用整体无法创建。

---

## 人审决定

仅定位，不进 fix 实现。报告留档供后续参考。
