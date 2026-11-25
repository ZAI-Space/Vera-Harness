[English](../scheduler.md) · [简体中文](scheduler.md)

# 定时任务

!!! abstract "独立调度，共享 Runtime"

    参考 Hermes 的定义持久化、先认领再执行、每次新 Agent 的结构。SQLite 管理任务与执行账本，独立进程执行，Agent Loop 不改。源码来源固定提交见英文版链接和实现说明。

## 创建与服务

任务定义包含名称、prompt、schedule、时区、工作区、模型/工具配置，以及 timeout/step_limit/cost_limit。后台显式要求 config.agent.mode=yolo，拒绝 confirm/human；不会替用户提高权限。凭据用环境变量，服务继承启动时环境，改密钥后重启。定义是私有快照，不是通用加密凭据库。

create 和 run 只创建定义/排队；需要 start 后台服务、serve 前台服务或 tick 单次分派才执行。start 脱离启动终端，但不安装开机服务、不唤醒电脑。--state 在子命令之前选择存储，workers 1–16，默认 2；同任务不重叠。

## 时间与控制

支持 30m 一次延迟、every 2h 固定间隔、五字段 Cron、未来 ISO 时间。Cron 使用 IANA 时区和夏令时；带偏移量的时间明确 UTC，裸时间采用任务时区。repeat 限制计划尝试数，失败也计入；manual run 不消耗计划次数和下个时刻。

grace_seconds 默认 120。过期一次性任务跳过；周期任务默认合并错过时刻为一次执行，catch_up=false 则记录跳过范围，不集中重放。pause/remove 取消尚未开始的队列，不停止已运行任务；cancel 使用执行 ID 停止。update 重置计划和次数，旧队列/活动调用保持旧快照。remove 保留历史，已消费的一次任务不能用 resume 重新创建。

## 能力和结果

Worker 将已保存的任务配置合并到安装包内置默认值，不在执行时读取项目目录中的 `vera.yaml`。修改任务配置应通过任务编辑入口完成。

每次运行独立消息，长期记忆按配置共享；可注入 Skill、@文件，复用 MCP、插件、模型、Subagent、具名沙箱。引擎或镜像缺失时失败，不回退宿主。cronjob_manage 默认为关闭，由宿主显式开启，只管理当前项目，不能改凭据/工作区/权限。计划 Worker 禁用该工具，防止递归调度。

历史含执行状态、摘要、run ID；artifacts/执行ID 下保留 trajectory.json、result.json、process.log，普通 RunStore 在 runs.sqlite3。前端通过 JobStore 和 Scheduler 接口管理，无通用 HTTP API，也不自动向微信飞书主动发送定时结果。

## 崩溃恢复

认领、计划推进、快照在同一事务。OS 锁避免双控制器；恢复按 PID 加创建身份清理自己遗留的子进程，已有原子结果可结算。未知/损坏结果记 interrupted，不自动重跑。跨崩溃的外部副作用不保证 exactly-once；核实后显式发起新运行。下面保留完整配置、命令与时间表。

## 配置、命令与源码示例

```yaml
name: Daily project check
prompt: Inspect this project and report which checks pass, with actual command output.
schedule: "0 9 * * *"
timezone: Asia/Shanghai
workspace: C:/path/to/project  # On Linux, use an absolute Linux path.
config:
  agent:
    mode: yolo
  model:
    model_class: litellm
    model_name: openai/your-model
    model_kwargs:
      api_base: https://your-provider.example/v1
timeout: 600
step_limit: 50
cost_limit: 1
```

```bash
vera-extra cron create daily-check.yaml
vera-extra cron start
vera-extra cron status
vera-extra cron list
vera-extra cron show JOB_ID
vera-extra cron pause JOB_ID
vera-extra cron resume JOB_ID
vera-extra cron update JOB_ID daily-check.yaml --revision 3
vera-extra cron run JOB_ID
vera-extra cron history --job JOB_ID
vera-extra cron cancel EXECUTION_ID
vera-extra cron remove JOB_ID
vera-extra cron stop
```

```yaml
scheduler:
  enabled: true
  directory: ~/.config/VERA/scheduler  # Or another explicit local path.
```
