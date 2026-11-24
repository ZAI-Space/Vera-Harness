[English](../website.md) · [简体中文](website.md)

# 官网文档构建

将仓库文档接入现有落地页。首页、文档和演示共用顶部胶囊导航；文档视图内嵌 `docs/zh/`，通过文档语言链接访问英文页面。

## 构建

使用已包含项目文档依赖的 Python 环境。在 Windows 仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe scripts/build_website_docs.py
```

其他系统使用当前环境：

```bash
python scripts/build_website_docs.py --landing-dir /absolute/path/to/landing
```

默认落地页目录是仓库中的 `website/`。通过 `--landing-dir` 可构建到包含 `index.html` 的外部落地页。
仓库内仅允许输出到 `website/docs/`。
脚本先输出核实后的生成目录，再以 `--strict` 运行 MkDocs。脚本不安装依赖，构建失败时返回非零状态码。

## 文件与导航

`docs/` 是维护中的文档源，`website/` 是静态落地页源。
`mkdocs.website.yml` 继承[常规文档配置](documentation.md)。官网 hook 将既有导航分为使用文档、维护文档和接口参考。
构建复用现有 Markdown 页面、Python API 引用、搜索索引、代码复制控件和 Mermaid 代码块。

官网文档使用白色背景与蓝色链接。首页、文档和演示之间采用横向过渡，顶部胶囊导航始终保留。
桌面文档的左侧分类和右侧页内目录固定，中间正文独立滚动。较小屏幕使用导航与搜索抽屉。
首页保留原有七屏展示内容。

## 重建与预览

生成文件写入落地页目录的 `docs/`，默认的 `website/docs/` 由 Git 忽略。
文档或 Python API 改动后，重新运行同一命令。生成物不纳入仓库。

如果非空 `docs/` 缺少脚本生成的 `.vera-website-docs` 标记，脚本会拒绝清理。
该目录已有其他文件时，选择另一个落地页目录。不要给无关目录添加该标记。

使用 Node.js 24 和已安装的桌面端依赖预览落地页：

```bash
npm --prefix desktop run preview:website
```

预览外部落地页目录时，在仓库根目录运行：

```bash
node desktop/node_modules/vite/bin/vite.js /absolute/path/to/landing --host 127.0.0.1 --port 8765 --strictPort
```

该服务支持 HTTP 字节范围请求，视频拖动进度时需要此能力。部署官网时，也应使用支持字节范围请求的静态托管服务。

打开 `http://127.0.0.1:8765/#docs`，检查顶部导航、栏目切换、分类导航、页内目录、语言链接、搜索和代码复制。
滚动长文档时，确认两侧栏保持原位。
打开 `#demo`，检查播放、进度跳转和全屏。无声演示仅保留这些控件，离开演示页时自动暂停。
