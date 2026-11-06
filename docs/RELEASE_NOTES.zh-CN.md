# FreeTube iOS 27.2 兼容性修复候选

修复针对启动时出现的 `This can only be called by an approved app.`，以及栈中的 LNPopupUI / UITabBarController 私有布局路径。

- 移除 LNPopupUI、LNPopupController、LNSwiftUIUtils 的链接/嵌入依赖。
- 以公开 SwiftUI safeAreaInset 实现迷你播放器；完整播放器持续挂载，继续使用同一个 AVQueuePlayer。
- 保留 AVKit 播放、后台音频、PiP、搜索及下载代码；补充 PiP 返回 UI 回调和后台 processing 声明。

## 验证与限制

- **编译通过**：macOS Runner，Xcode 26.6 / Swift 6.3.3，iPhoneOS 26.5 SDK，Release，iOS device arm64。
- **IPA 检查通过**：Payload、app、Info.plist、可执行架构、依赖加载、资源及 popup 残留检查；取回后再次校验通过。
- **12 项打包检查器自动测试通过**；这些是合成包回归测试，不是应用端功能测试。
- **未完成 iOS 27.2（24B119）真机验证**。编译和打包成功不等于崩溃已在设备上解决。PiP、后台音频、搜索、下载及横竖屏仍需设备回归。
- 上游仍有 actor 隔离、Sendable、弃用 API 等编译警告，详情见附带日志。

构建源码：`21833f0d84017961ab8039a98228d27e89de257a`。

构建日志：https://github.com/liljz808/freetube/actions/runs/42268855040

## 下载与 SideStore 安装

下载附件 **FreeTube-fixed.ipa**，不要下载页面自动生成的 Source code ZIP 来安装。

这是未签名、供 SideStore 重新签名的 IPA，不需要向本项目提供 Apple ID、密码或个人签名证书。按当前 SideStore 配置开启 LocalDevVPN、连接所需 Wi-Fi 并完成校园网认证，然后在 My Apps 点击“+”导入 IPA。

建议先用 SideStore 独立安装验证启动，再测试 LiveContainer。保留旧版本的下载和其他数据，勿在未备份时随意卸载。

文件大小：22,956,285 字节。

SHA-256：`f8c0adf899a404aaf0198ac07321fe407dffe100348f9f71971d179a43f1e5de`。

附件还包括 SHA-256 校验文件、IPA 校验 JSON、完整构建日志/xcresult ZIP 和中文修复报告。发布为预发布版本，以明确真机验证尚未完成。
