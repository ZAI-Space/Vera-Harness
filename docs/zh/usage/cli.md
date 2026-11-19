[English](../../usage/cli.md) · [简体中文](cli.md)

# vera 终端

!!! abstract "交互入口"

    在项目目录运行 vera 或 python -m vera，别名按迁移文档保留。未传任务则询问输入，直接 -t 可以非交互提交。命令 --help 是当前参数依据。

## 参数与任务

-t 指定任务，-m 指定模型，--model-class/--agent-class 选择适配器，-c 合并配置，-y 免逐项审批，-l 费用界（0 关闭）。--sandbox 与 --sandbox-profile 互斥；--skill 注入技能；--storage/--resume/--reconcile 管运行存储与恢复；-o 轨迹；--exit-immediately 完成后不追问。

支持 @项目文件、能力选择与 /plan、/goal。启动器保留带引号参数和调用目录。当前命令与[终端指南](../terminal.md)共同定义输入，不把模型输出的斜杠当用户操作。

## 模式与产物

confirm 审批，yolo 直接执行，human 手动输入；旧快捷控制按交互提示可用。权限不等于沙箱。启动打印配置与轨迹，启用 RunStore 才获得持久化收据。前端复用结构化接口，不解析彩色终端文本。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```text
Explain @src/main.py
/permissions confirm
/skill
/mcp
/plugin
/subagent
/sandbox
/plan Design a change before implementing it
/goal Complete the change and verify it
```

## API 参考

::: vera.run.cli
