[English](../../advanced/yaml_configuration.md) · [简体中文](yaml_configuration.md)

# YAML 配置

!!! abstract "完整基础配置再叠加"

    -c 接受内置名称、路径和 section.key=value，按从左到右合并。传入 -c 会替换隐式默认列表，需保留基础 YAML 来提供模板和终端设置，不能只传零散覆盖。

agent 控制类、模板、交互模式和步骤/费用/时间；model 选择适配器与请求参数；environment 是低层后端/cwd；sandbox 或 sandbox_profile 管隔离；web/MCP 管外部能力，Skill/插件/角色管扩展，storage/terminal/goal/scheduler 管存储和外部控制器。

配置目录按内置层级和额外目录查找；值由 YAML/JSON 规则解析，并需正确引用宿主 Shell 字符。相对路径遵守模块契约：终端按工作区，channels 按文件所在目录，后台任务建议绝对路径。私有存储放在需要的保护边界外，密钥放环境。

## 模板和类

Jinja 模板读取组件与任务上下文，直接构造 Agent 需要完整模板。非可信文件和记忆作为任务数据，不二次解释为模板。类选择可用短名或完整 Python 路径，字段以对应 Config 为准。

confirm/yolo/human 为权限；run_mode 只是 plan/goal 的运行时配置部分，持续目标还需要 drive_goal 外部控制。不要以为单设字段即可获得自动闭环。

## 配置、命令与源码示例

```bash
vera -c vera.yaml -c project.yaml -c agent.step_limit=40
```

```yaml
agent:
  agent_class: stateful_interactive
  mode: confirm
  step_limit: 40
  cost_limit: 1.0
  wall_time_limit_seconds: 300
model:
  model_class: litellm
  model_name: openai/YOUR_MODEL
environment:
  environment_class: local
  cwd: .
storage:
  path: ./runs.sqlite3
```
