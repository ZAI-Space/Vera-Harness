[English](../licenses.md) · [简体中文](licenses.md)

# 许可证与字体

VERA 自有代码使用仓库的 MIT 许可证。第三方代码保留自己的许可证；品牌更名不改变这些义务。完整来源见仓库根目录 `THIRD_PARTY_NOTICES.md` 和 `desktop/third_party/`。

| 内容 | 来源与许可证 | 分发注意事项 |
| --- | --- | --- |
| 基础 Agent 来源 | mini-swe-agent，MIT | 保留原版权和许可文字；旧命令及配置读取属于兼容路径。 |
| 桌面基础来源 | Percho，MIT | 保留来源和许可证。 |
| 部分插件/调度界面 | PI-Desktop，LGPL-3.0 | 保留相关源码、修改及 LGPL 声明；不能统一改称 MIT。 |
| 数学字体 | KaTeX，MIT | 可商业使用及分发，保留版权和 MIT 许可。 |
| 编辑器图标字体 | Microsoft Codicons，CC BY 4.0 | 可商业使用，保留署名、许可链接及修改说明。 |
| 编辑器及其他依赖 | Monaco 等包的 LICENSE、ThirdPartyNotices | 按实际分发版本保留各组件声明。 |

## 打包规则

界面正文使用系统字体栈，没有随应用分发系统字体文件。字体名称出现在 CSS 中不代表仓库拥有这些字体的再分发权。

KaTeX 保留全部公式字族，Electron 构建只保留 WOFF2 格式，去掉同一字体的 WOFF/TTF 副本。Monaco 的 Codicon TTF 用于编辑器图标，不能作为无用字体删除。MkDocs 关闭远程 Google 字体加载。

发布时一并携带 `desktop/third_party/katex-LICENSE`、`codicons-LICENSE` 和 Monaco 的许可证及第三方声明。新增字体、素材、插件或上游代码前，核对固定版本的实际许可；不要用单个 npm 包的 license 字段概括所有内嵌素材。

来源：[KaTeX fonts](https://github.com/KaTeX/katex-fonts/blob/master/LICENSE)、[Codicons](https://github.com/microsoft/vscode-codicons/blob/main/LICENSE)。

## 落地页字体

静态落地页通过 Google Fonts 加载 Inter、Quantico、Space Grotesk 和 JetBrains Mono。
这四个字族采用 SIL Open Font License 1.1，允许商业使用。仓库没有打包落地页字体文件。
如需自行托管字体，保留版权和 OFL 声明，并遵守保留字体名称的限制。
远程字体需要能够访问 Google Fonts；服务不可达时，页面使用本地回退字体。

字体许可：[Inter](https://github.com/google/fonts/blob/main/ofl/inter/OFL.txt)、
[Quantico](https://github.com/google/fonts/blob/main/ofl/quantico/OFL.txt)、
[Space Grotesk](https://github.com/google/fonts/blob/main/ofl/spacegrotesk/OFL.txt)、
[JetBrains Mono](https://github.com/google/fonts/blob/main/ofl/jetbrainsmono/OFL.txt)。
