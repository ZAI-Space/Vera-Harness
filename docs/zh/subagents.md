[English](../subagents.md) · [简体中文](subagents.md)

# Subagent

通过 YAML 角色描述何时委派、如何工作、使用哪些模型、工具和 Skill。主 Agent 按任务调用角色，每次创建独立上下文并复用当前 Runtime 环境与已建立的工具连接。

## 角色配置

`description` 用于发现，`instructions` 定义行为；`tools` 为允许的注册工具名，`skills` 为当前目录中的技能名。`model` 省略时从父配置创建新实例；显式指定时必须是完整模型配置。Bash 表示共享环境中的正常 Shell 权限，包括写入。

父模型通过 `subagents_list` 查看角色、`subagent_run` 发送自包含任务并同步等待结果。子任务用 `subagent_finish` 返回摘要；主任务收到状态、步骤/调用与费用信息，以及启用轨迹时的路径。委派入口留给主 Agent。

## 预算与权限

`max_runs` 限制一次 CLI 运行中的委派次数，子任务费用计入父预算。步骤、费用和墙钟限制在模型调用间检查，已发出的调用不是硬终止。交互授权沿用父 Agent 当前模式，角色不能突破父运行时的能力边界。独立上下文不等于独立文件系统；并发/互相修改需由宿主协调。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```yaml
subagents:
  max_runs: 8
  roles:
    documentation-reviewer:
      description: Check public documentation against the implementation.
      instructions: |
        Inspect the named module and cite concrete lines in your findings.
        Limit the review to the assigned files.
      model:
        model_class: litellm
        model_name: openai/gpt-4o-mini
      tools: [bash]
      skills: []
      step_limit: 12
      cost_limit: 0.5
      wall_time_limit_seconds: 180
```

```bash
vera -c vera.yaml -c roles.yaml -t "Ask the documentation-reviewer to review the command-line examples"
```
