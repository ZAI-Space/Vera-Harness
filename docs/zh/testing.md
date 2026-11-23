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

`src/vera/models/test_models.py` 是发布的确定性模型适配器，不是遗漏的测试文件。

## Python 检查

在根目录安装 `.[full,channels]` 后执行：

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

`python -m pytest tests/run/test_examples.py -ra` 验证随仓库发布的示例，不调用付费模型。回归测试尽量使用真实文件和本机协议 fixture；不得用模拟结果替代缺失的联调证据，也不得删除失败测试。

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

UI 验收依次执行设置、全局设置、市场、模型配置与通用助手五组独立场景，启动真实 Electron、Python 服务和本机模型协议端点，检查显示与文件、数据库副作用，并输出各组证据目录。根目录 `.venv` 不是目标解释器时设置 `VERA_PYTHON`。全局设置场景会启动固定版本的可选任务面板；请先按[任务面板](taskboard.md)完成安装准备。

## 证据口径

- 默认 pytest 不启用付费的 `--run-fire` 测试。
- 缺少容器、平台、可选上游应用或凭据会产生跳过，需分别报告。
- 本机协议端点验证集成，不证明模型质量或真实市场可达性。
- 安全复现需要单独的受限隔离环境；普通 CI 记录工程化结果。
- 合并前核对 PR 的准确 SHA 与全部必需 CI；合并后核对 `dev` 的结果。

日常任务从 `dev` 拉分支，经 Squash PR 返回；发布走 `dev` → `main`。分支保护或缺少独立批准是真实交付门槛，不应绕过。
