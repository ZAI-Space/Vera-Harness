[English](../storage.md) · [简体中文](storage.md)

# 运行存储

通过 `--storage PATH` 启用 SQLite；配置 `storage: {}` 使用全局默认库。私有记录需要防止项目工具改写时，放到可写工作区之外。运行记录包含 ID、状态、退出原因、模型调用/费用和轨迹路径；委派记录含父 ID 与角色。父费用已含子费用，自己的调用计数不混为子调用数。

## 收据与检查点

工具收据记录名称、动作、provider 调用 ID、时间和返回码。returned 只表示记录到返回值，返回码决定是否报告成功；unknown 表示无法确定副作用，例如崩溃中断或 MCP 应答丢失。running 记录也可能属于已退出进程，不能只凭字段判断仍在运行。

SQLite 在完整步骤边界保存任务与消息检查点；轨迹和数据库可能包含敏感项目数据。历史命令只读访问。启用存储时默认轨迹名含 run ID；手动 `-o` 要为每次运行选择新路径。

## 取消与恢复

`runs cancel` 在下一步/工具边界停止，包括委派；已发出的外部操作可持续到返回或超时。`--resume` 生成新 ID、新预算和新轨迹，要求相同工作区、模型适配器、后端及相关配置。临时容器状态不因恢复重建，工作区需要持久化。

检查点后有工具调用或 unknown 收据时，先检查工作区和收据，再用 `--reconcile` 提交已验证结果。旧调用不会从检查点自动重放，每个运行只能有一个继续记录，活动进程需释放运行锁。v1 数据库在写入时迁移，旧记录仍可读；没有检查点的记录不能恢复。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
vera --storage ./runs.sqlite3 -t "Run the unit tests"
vera-extra runs list --db ./runs.sqlite3
vera-extra runs show <run-id> --db ./runs.sqlite3
```

```bash
vera-extra runs cancel <run-id> --db ./runs.sqlite3
vera --storage ./runs.sqlite3 --resume <run-id>
```
