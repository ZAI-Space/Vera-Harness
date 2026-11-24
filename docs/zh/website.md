[English](../website.md) · [简体中文](website.md)

# 官网文档构建

将仓库文档构建到现有落地页旁。落地页链接到 `docs/zh/`；通过语言标签和每页的语言链接访问英文页面。

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

官网文档主题加入返回官网链接，使用白色背景与蓝色链接。
桌面页面分为分类导航、正文和页内目录三栏。较小屏幕由 Material 提供导航与搜索抽屉。
构建不修改落地页的各屏内容、样式和脚本。

## 重建与预览

生成文件写入落地页目录的 `docs/`，默认的 `website/docs/` 由 Git 忽略。
文档或 Python API 改动后，重新运行同一命令。生成物不纳入仓库。

如果非空 `docs/` 缺少脚本生成的 `.vera-website-docs` 标记，脚本会拒绝清理。
该目录已有其他文件时，选择另一个落地页目录。不要给无关目录添加该标记。

以整个落地页目录启动静态服务，验证相对链接与搜索：

```bash
python -m http.server 8765 --directory /absolute/path/to/landing
```

打开 `http://127.0.0.1:8765/docs/zh/`，检查分类导航、页内目录、语言链接、搜索、代码复制与返回官网链接。
