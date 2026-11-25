[English](../testing.md) · [简体中文](testing.md)

# 测试与交付

沿用项目测试框架。凭据、运行报告和验收截图保存在仓库外。

## 正式测试目录

| 路径 | 覆盖范围 |
| --- | --- |
| `tests/agents`、`tests/models`、`tests/environments`、`tests/config`、`tests/utils` | Python 组件及适配器。 |
| `tests/run` | Runtime 组装、CLI、本机协议、worker、存储、渠道、调度和集成 fixture。 |
| `desktop/tests` | 前端契约、状态、组件和主进程/preload；目录镜像 `desktop/src`。 |
| `desktop/tests/ui` | 真实 Electron 验收和共用启动器。 |
| `tests/run/desktop_contract_trace.py` | 为 TypeScript 契约测试生成真实 Python 事件。 |

`src/vera/models/test_models.py` 提供 Runtime 使用的确定性模型适配器。

## Python 检查

在根目录安装 `.[full,channels]` 后执行：

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

运行 `python -m pytest tests/run/test_examples.py -ra` 检查随仓库发布的示例。集成测试使用真实文件、子进程和本地协议服务。

## 桌面检查

在 `desktop/` 安装锁定依赖后执行：

```bash
npm run check:boundary
npm run lint
npm run typecheck
npm test
npm run build
npm run test:ui
```

UI 测试通过独立场景覆盖设置、市场、模型配置和助手交互。测试启动 Electron、Python 服务和本地模型协议服务，检查界面、文件与数据库变化，并输出报告目录。使用其他 Python 解释器时设置 `VERA_PYTHON`。全局设置场景会启动固定版本的任务面板，运行前按[任务面板](taskboard.md)完成安装准备。

## 测试环境

- 运行 `python -m pytest -n 2 -ra` 执行默认套件，`-ra` 显示包含跳过项的运行摘要。
- 容器测试需准备对应引擎和镜像，任务面板测试需安装对应构建。
- 添加 `--run-fire` 可启用外部模型 API 测试，运行前配置供应商凭据和预算。
- 安全复现用例在独立隔离环境中执行。

`main` 是唯一长期、默认和生产分支。临时任务分支通过必需检查后，经 Squash PR 合回，交付后删除；发布时给已合入 `main` 的提交打标签。完整流程见[贡献指南](contributing.md)。
