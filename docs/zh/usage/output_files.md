[English](../../usage/output_files.md) · [简体中文](output_files.md)

# 输出文件

轨迹 .traj.json 保存完整消息、组件配置、费用/调用信息、退出状态和提交内容；轨迹 Schema 与产品版本是不同标识。工具请求、调用 ID 和观察必须按 Provider 的 Chat/Responses 格式理解，不假设所有消息都有普通 content 字符串。

## 轨迹结构

info 包含 model_stats、config、版本信息、exit_status、submission；messages 包含系统/用户/助手和工具消息；动作与返回码/时间等在 extra 中。注册工具通过命名调用关联观察，传统 Bash 完成标记仍可触发提交。精确字段与兼容名见下方示例及[迁移](../advanced/v2_migration.md)。

轨迹可能在执行中保存，不代表出现文件就已成功；结果需看退出原因和收据。请求/配置可能包含敏感项目内容，放私人目录，不公开转发内部推理。查看可用[Inspector](inspector.md)，持久运行与恢复使用[RunStore](../storage.md)。

## 批量预测

preds.json/转换产物按 benchmark 的模型名、实例 ID 和预测补丁契约汇总，评分由外部评测器执行。保存预测不等于得分，失败/未完成题仍应保留在实例清单中。运行记录、子任务轨迹和存储库各有不同用途，不能互相当作完成证明。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```json
{
  "info": {
    "model_stats": {
      "instance_cost": 0.05,  // total cost of API calls for this run
      "api_calls": 12  // number of API calls made
    },
    "config": {
      "agent": { ... },  // agent configuration
      "agent_type": "vera.agents.default.DefaultAgent",
      "model": { ... },  // model configuration
      "model_type": "vera.models.litellm_model.LitellmModel",
      "environment": { ... },  // environment configuration
      "environment_type": "vera.environments.local.LocalEnvironment"
    },
    "vera_version": "2.4.6",  // version of VERA used
    "exit_status": "Submitted",  // final status (Submitted, LimitsExceeded, etc.)
    "submission": "..."  // final output/patch submitted by the agent (if any)
  },
  "messages": [  // full conversation history
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    ...
  ],
  "trajectory_format": "vera-1.1"  // format version identifier
}
```

```json
// System message (agent instructions)
{"role": "system", "content": "You are a helpful assistant..."}

// User message (task description)
{"role": "user", "content": "Please solve this issue: ..."}

// Assistant message (model response with parsed actions)
{
  "role": "assistant",
  "content": "Let me check the files...\n\n```vera_bash_command\nls -la\n```",
  "extra": {
    "actions": [{"command": "ls -la"}],  // parsed actions to execute
    "cost": 0.003,  // cost of this API call
    "timestamp": 1706000000.0,  // unix timestamp of when this message was created
    "response": { ... }  // raw API response
  }
}

// Observation message (execution result)
{
  "role": "user",
  "content": "<returncode>0</returncode>\n<output>\nfile1.py\nfile2.py\n</output>",
  "extra": {
    "returncode": 0,
    "timestamp": 1706000001.0
  }
}

// Final message (when agent submits)
{
  "role": "exit",
  "content": "",
  "extra": {
    "exit_status": "Submitted",
    "submission": "diff --git a/file.py..."
  }
}
```

```json
{
  "owner__repo__123": {  // keyed by instance_id
    "model_name_or_path": "anthropic/claude-sonnet-4-5-20250929",  // model used
    "instance_id": "owner__repo__123",  // SWE-bench instance identifier
    "model_patch": "diff --git a/file.py b/file.py\n..."  // generated patch (unified diff)
  },
  ...
}
```
