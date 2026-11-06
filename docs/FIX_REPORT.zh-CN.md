# FreeTube iOS 27.2 启动异常：修改与验证记录

记录日期：2026-11-07（北京时间）。

**交付状态：修复候选源码已完成；尚未通过 Xcode 编译，尚未生成 IPA，尚未完成 iOS 27.2 真机验证。**

## 基线与问题

- 源仓库：https://github.com/leshkodev/freetube
- 克隆时 main 的提交：`8fc6d3b7be9571e3ffcb179de3d1de2dfe7012e7`。
- 本地修改分支：`fix/ios27-popup-crash`。
- 用户报告环境：iOS 27.2（24B119）；LiveContainer 和 SideStore 独立安装均启动失败。
- 异常文字：`This can only be called by an approved app.`
- 用户提供的栈涉及 LNPopupUI、UITabBarController、`_ln_proposedFrameForPopupBar`、`_ln_popupOffsetForPopupBar:`。
- 已阅读完整 README.md 和 CLAUDE.md。没有收到完整 `.ips` 或真机调试会话。

## 源码定位与升级评估

原锁文件固定 LNPopupUI **3.0.2**、LNPopupController **4.4.1**、LNSwiftUIUtils **1.1.5**。`App/RootView.swift` 将 `.popup` 挂到 `TabView`，并配置 popup 的交互、样式和进度。`PopupContentWrapper` 再把完整播放器和元数据交给该库。

核对 LNPopupController 的 4.4.1 标签源码后发现：

1. `Private/Minimization/UITabBar+LNPopupMinimizationSupport.mm` 在 `+load` 检查私有 selector 是否存在。
2. `_ln_proposedFrameForPopupBar` 通过 KVC 读取 **`_frameForHostedAccessoryView`**。
3. `UIViewController+LNPopupSupportPrivate.mm` 中 UITabBarController 的 `_ln_popupOffsetForPopupBar:` 调用上述方法。

这条路径与用户提供的栈吻合。`respondsToSelector` 能证明方法存在，不能证明第三方应用获准调用；UIKit 抛出的 Objective-C 异常也不能用常规 Swift `do/catch` 修复。SideStore 重新签名和 LiveContainer 容器不会把私有布局 API 变成受支持的第三方接口。

**原因判断的边界：**依据用户报告和源代码，可以定位到私有 tab accessory 布局路径；但缺少完整崩溃报告，无法逐帧确认 24B119 中最终执行审批检查的 UIKit 内部函数或其具体授权规则。

优先检查了新版本：远端存在 LNPopupUI **4.0.4** 和 LNPopupController **4.6.2**。实际读取的 LNPopupUI master 提交为 `60853564423524c9ed15cc74c5969d3e1ca666f1`；LNPopupController master/4.6.2 为 `0e130bcc3e88d4b2134f0afdbf034ea93f6ab75d`。

最新 LNPopupController 的 `Private/Minimization/UITabBar+LNPopupInheritedBarMetricsSupport.mm` 仍读取私有 **`_hostedElementLayoutResolver`** 并调用返回的布局闭包，且仍有标签栏 swizzling。上游确有 iOS 27.1/27.2 适配记录，但静态检查不能证明新版本消除了本次权限异常。因此没有把“升级依赖”直接宣称为修复，也没有在缺少设备和 Xcode 的情况下声称做过升级版运行测试。

采用用户授权的替代方案：**从应用依赖图移除 LNPopup 系列，并用公开 SwiftUI API 承载播放器。**

## 修改文件与原理

以下路径均相对仓库根目录。

| 文件 | 变化与目的 |
|---|---|
| `FreeTube/FreeTube/App/RootView.swift` | 移除 LNPopupUI import、`.popup` 链和 PopupContentWrapper；在每个 tab 的内容上用 `safeAreaInset` 放迷你播放器，不读取系统 tab bar 私有结构；在 tab 外维持一份完整播放器。 |
| `FreeTube/FreeTube/UI/Player/MiniPlayerBar.swift` | 新增 SwiftUI 迷你播放器：标题、封面、准备/下载状态、进度、播放暂停、下一首；点击或向上滑动展开。进度过滤非有限值并限制在 0…1。 |
| `FreeTube/FreeTube/UI/Player/FullScreenPlayer.swift` | 继续使用既有完整播放器、队列、评论、下载菜单和 AVKit 控件；清理失效的 LNPopup 注释；保留视频区域下滑收起和 Close 按钮；限制快速手势方向，避免横向拖动被当作收起。 |
| `FreeTube/FreeTube/UI/Player/PlayerSurface.swift` | 添加 AVPlayerViewControllerDelegate 的 PiP 返回 UI 回调，返回时展开既有播放器。没有添加私有 UIKit API。 |
| `FreeTube/FreeTube/Core/Player/PlayerStateManager.swift` | 仅修正一条过时注释；播放状态和 AVQueuePlayer 实现不变。 |
| `FreeTube/FreeTube.xcodeproj/project.pbxproj` | 移除 LNPopupUI 的链接、嵌入、包和产品引用；把剩余直接依赖固定到原锁文件的版本/提交，避免移除 UI 库时意外升级下载和 Python 栈。 |
| `FreeTube/FreeTube.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved` | 删除三个 popup 相关 pin，保留其余 revision；使用不带过时 originHash 的 v2 格式，供 Xcode 重新解析。 |
| `FreeTube/FreeTube.xcodeproj/xcshareddata/xcschemes/FreeTube.xcscheme` | 提交共享 scheme，供没有个人 Xcode 用户状态的 CI 构建。 |
| `FreeTube/FreeTube/Info.plist` | 保留 audio/fetch；为已在启动时注册并提交的 BGProcessingTaskRequest 补充 `processing` 模式。 |
| `FreeTube/FreeTube/Localizable.xcstrings` | 给新可访问性标签补充 en/es/ru/fr/de 翻译。 |
| `scripts/build-ipa.sh` | 无个人签名构建 Release、iphoneos、arm64，打包 IPA，保存解析/编译日志和 xcresult，校验后生成 SHA-256。 |
| `scripts/verify-ipa.py` | 检查 Payload、唯一 app、Info.plist、可执行权限、Mach-O arm64/iOS device 平台、依赖嵌入和 popup 残留；不冒充真机测试。 |
| `scripts/check-source.py` | CI 阻止已移除的私有 UIKit popup 依赖链回归，并检查后台模式。 |
| `tests/test_ipa_validation.py` | 12 项打包检查器回归测试，用合成 Mach-O 头覆盖错误架构、模拟器、缺失框架、私有实现残留等拒绝路径。 |
| `.github/workflows/build-ios.yml` | GitHub macOS 26 runner 构建；选择已安装的稳定 Xcode 26.2+；只申请 contents:read，产物和失败证据分别上传。 |
| `README.md`、`CLAUDE.md` | 更新播放器结构、实际工具链要求和测试状态，避免后续维护重新引入 LNPopup。 |

完整播放器在收起后只移动到可见区域外，仍保持挂载，避免切换 tab 或收起时销毁正在参与 PiP 的 AVPlayerViewController。迷你播放器和完整播放器都操作原有 PlayerStateManager 中的同一个 AVQueuePlayer。展开状态屏蔽背后 tab 的无障碍元素，收起状态屏蔽隐藏播放器的交互和无障碍元素。

这是对触发路径的移除，没有屏蔽错误弹窗、安装异常吞噬器、伪造批准状态或添加受限制 entitlement。视觉上的库专属标签栏缩小动画被普通迷你栏替代；展开/收起用 SwiftUI 动画，未复刻 LNPopup 的跟手弹簧交互。

## 功能保留与其他兼容性审查

- 搜索、网络服务、YouTubeKit 映射、下载/转码管线、Python/JavaScript 桥、SwiftData 模型未作功能修改。
- AVPlayerViewController 的系统播放控件、AirPlay 和 `allowsPictureInPicturePlayback = true` 保留。
- AVAudioSession `.playback`、Now Playing、锁屏控制、远程命令和 `audiovisualBackgroundPlaybackPolicy = .continuesIfPossible` 保留。
- 后台音频和 BG processing 的 plist 声明已核对；这不保证系统会允许任意下载无限期后台运行。
- 原 README 的 Xcode 15+ 描述与当前源代码使用的 Swift 6.2 隔离语法、Xcode 工程设置不符，构建入口明确要求 Xcode 26.2+。
- iOS 上未发现另一条应用自有的 LNPopup 私有调用。MacIntegration 的动态 AppKit 交互受 Mac 环境判断约束，不属于这条 iOS tab bar 路径，未扩大改动。
- 既有 SwiftData 初始化失败会 fatalError、后台下载 coordinator 有未完成的整合 TODO、Python/ffmpeg 运行时和 YouTube 提取逻辑仍有各自的潜在故障点。没有证据把这些认定为本次异常，也没有删除用户数据来绕过它们。

**保留代码不等于功能已通过测试。**布局、横竖屏、后台音频、PiP 生命周期、网络搜索和下载都需要实际运行回归。

## 已执行的验证

| 检查 | 结果 | 说明 |
|---|---|---|
| 12 项 Python 检查器回归测试 | 通过 | 合成输入测试；不是 Swift 或真机功能测试。 |
| 修改的 4 个播放器 Swift 文件语法解析 | 通过 | Tree-sitter Swift 解析；不是 Swift 编译器类型检查。 |
| Xcode project OpenStep 解析及对象引用检查 | 通过 | 检查项目文件结构，不解析/编译 Swift Package。 |
| plist、字符串目录 JSON、共享 scheme XML、workflow YAML 解析 | 通过 | 文件格式检查。 |
| `scripts/check-source.py` | 通过 | 源码和依赖图移除了 popup 链；后台模式存在。 |
| Bash 脚本语法、`git diff --check` | 通过 | 构建脚本尚待在 macOS 执行。 |
| 本环境运行构建脚本 | 被阻塞，退出码 69 | Linux 环境没有 xcodebuild；真实输出见 build-evidence/local-build-attempt.txt。 |
| GitHub 网页登录 | 未成功 | 通行密钥不受支持；账号密码安全表单提交后站点返回浏览器异常，未到两步验证码页面。没有在聊天中接收密码或验证码。 |
| macOS Actions 编译 | 待提交后执行 | 已检测到 liljz808/freetube Fork，并确认写入权限；将通过现有连接提交，不再依赖网页登录。 |
| 真实 IPA 内容校验 | 未执行 | 没有真实 IPA；不会把合成测试包当作 IPA 交付。 |
| iOS 27.2（24B119）真机验证 | 未执行 | 无该设备访问；无法确认异常已在真机消失。 |

源仓库虽在 README 中提到 FreeTubeTests，但克隆内容中没有对应 XCTest 源码/测试 target；本次没有虚构执行 xcodebuild test。

## 构建与下一步

现成构建入口为 `bash scripts/build-ipa.sh`；只应在 macOS + Xcode 26.2+ 上执行。Actions workflow 可手动运行，或在 `fix/ios27-popup-crash` 分支收到 push 时运行。

构建使用 `CODE_SIGNING_ALLOWED=NO`、`CODE_SIGNING_REQUIRED=NO` 和空 DEVELOPMENT_TEAM，不导入 Apple ID、P12 或 provisioning profile。成功时输出：

- `build/FreeTube-fixed.ipa`
- `build/FreeTube-fixed.ipa.sha256`
- `build/ipa-verification.json`
- `build/logs/resolve.log`、`build/logs/xcodebuild.log`、`build/logs/build-ipa.log`
- `build/Build.xcresult`

IPA 是供 SideStore 重新签名的未签名包，不能直接作为企业签名包安装。CI 检查失败会停止发布 IPA；失败日志仍上传。

继续推进所缺少的账号操作：用户在自己的 GitHub 账号下 Fork 源仓库，并让现有 GitHub 连接能够访问该 Fork。随后可以提交该修复分支并利用 macOS Actions 实际编译、排查编译错误和下载产物。若 GitHub App 缺少 workflow 写入或 Actions 权限，需要补齐对应权限；当前尚未提交，不能预先保证这部分权限已具备。

更新：已检测到 `liljz808/freetube` Fork，现有连接具备写入权限；不再需要网页登录，正在提交修复并推进 macOS Actions。

## SideStore 安装说明（待 IPA 生成后）

1. 将 `FreeTube-fixed.ipa` 下载到 iPhone 的“文件”。
2. 按当前 SideStore 版本要求开启本地连接 VPN；本用户已有 LocalDevVPN 配置，并准备好所需 Wi-Fi 及校园网认证。
3. 在 SideStore 的 My Apps 使用“+”导入 IPA，等待 SideStore 在设备端重新签名和安装。无需把 Apple ID、密码或个人证书交给本修复流程。
4. 先独立启动 FreeTube，记录是否仍出现原异常；随后验证搜索、在线视频、本地下载播放、锁屏后台音频、PiP 进入/返回、跨 tab、横竖屏以及下载/取消/离线播放。
5. 免费开发者签名以 SideStore 显示的有效期为准，及时续签。先保留旧应用的数据；不要为了测试随意卸载含有未备份下载的旧版本。

参考 SideStore 官方文档：https://docs.sidestore.io/ 。实际按钮和联网要求以已安装版本为准。

## 主要上游依据

- 原项目 README 与 CLAUDE：https://github.com/leshkodev/freetube
- 原受影响依赖：https://github.com/LeoNatan/LNPopupController/tree/4.4.1
- 最新依赖源码：https://github.com/LeoNatan/LNPopupController/tree/4.6.2
- iOS 27.1/27.2 适配记录：https://github.com/LeoNatan/LNPopupController/issues/648
- LNPopupUI：https://github.com/LeoNatan/LNPopupUI
- GitHub macOS runner 镜像：https://github.com/actions/runner-images/blob/main/images/macos/macos-26-Readme.md
- Apple BGProcessingTaskRequest：https://developer.apple.com/documentation/backgroundtasks/bgprocessingtaskrequest

所有“源码已移除触发路径”的描述均限定于本修复候选。**没有 Xcode 编译成功记录或 iOS 真机验证记录，不能宣布该崩溃已修复。**
