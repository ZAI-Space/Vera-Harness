# 微信与飞书远程接入

`minisweagent.channels` 是独立渠道模块，复用 `minisweagent.runtime` 组装模型、
Skills、MCP、Subagent、插件和沙箱。终端入口也使用这个组装函数，Agent Loop 保持原有执行语义。
渠道服务主动连接平台，不要求公网 IP、Webhook 服务或内网穿透。

## 安装与启动

在 PowerShell、Git Bash 或 Linux Shell 中激活项目 Python 环境后执行：

```shell
python -m pip install -e '.[channels,mcp]'
mini-extra channels init --workspace .
```

编辑生成的 `channels.yaml`：

```yaml
workspace: /absolute/path/to/workspace
agent_config: model.yaml
sandbox: auto
step_limit: 30
cost_limit: 1.0
task_timeout: 180
accounts:
  weixin:
    channel: weixin
    enabled: true
  feishu:
    channel: feishu
    enabled: false
```

`agent_config` 使用现有 Agent 配置格式，叠加在内置 `mini.yaml` 之上。只需要在
`model.yaml` 中指定模型；密钥使用模型供应商的环境变量，不要放进 YAML。
相对路径按渠道配置文件所在目录解析；工作区、模型、工具和预算不能由聊天消息更改。

`sandbox: auto` 在没有可用隔离环境时明确失败，不自动降级。希望使用本地 Bash 时
显式设为 `local`。Docker 用户可在 Agent 配置中设置 `sandbox.docker_image`；使用已有
本地镜像，模型在宿主进程调用，工作区工具在所选沙箱执行。MCP 的宿主进程/网络权限
继续由原有 SandboxConfig 管理。

```shell
mini-extra channels login weixin -c channels.yaml
mini-extra channels start -c channels.yaml
```

另一个终端可以执行：

```shell
mini-extra channels status -c channels.yaml
mini-extra channels stop -c channels.yaml
```

也可用 Ctrl+C 停止服务。停止只影响该状态目录下的受管进程，不停止其他 Docker 容器。

## 微信登录

实现参考 [Tencent/openclaw-weixin](https://github.com/Tencent/openclaw-weixin) 的后端协议和
扫码状态机，固定参考 commit `0ad1ae91347a938f52f1e4e2abd6dcda51e05f9e`
（`3.0.0-beta-0`）。不安装或嵌入 OpenClaw。

运行 `channels login weixin` 后，终端打印二维码，并给出临时 PNG 的绝对路径。
请在有效期内用手机微信扫描并确认绑定。若手机要求 PIN，在终端的隐藏输入提示中填写。
二维码过期会换新图和路径；登录结束后临时图片删除，不要继续扫描聊天记录中的旧图。

登录只实现操作者绑定自己的账号；其他所有者的实名授权流程不在本模块中自动进行。
登录成功默认只接受扫码人的消息。配置 `allowed_users` 可替换默认名单；禁止使用通配符。
每个账号独立保留登录与轮询游标。`-14` 会显示 `login_required`，要求重新登录。

支持文字和平台已经提供的语音转写文字。图片、文件、视频不会下载或执行；单独发送
不支持的消息会得到文字说明。引用附件/CDN 加密、语音识别和多媒体回复不属于此次实现。

## 飞书登录与配对

使用[官方 lark-oapi Python SDK](https://github.com/larksuite/oapi-sdk-python)，
采用应用机器人和 WebSocket 长连接。不是飞书账号密码，也不是群自定义 Webhook 机器人。

先在[飞书开发者后台](https://open.feishu.cn/app)完成：

1. 创建企业自建应用，启用机器人，取得 App ID 和 App Secret。
2. 开通读取用户发给机器人的单聊消息权限 `im:message.p2p_msg:readonly`。
3. 开通以应用身份发送消息权限 `im:message:send_as_bot`。
4. 在“事件与回调”选择“使用长连接接收事件”，并添加
   “接收消息 v2.0”——`im.message.receive_v1`。
5. 发布应用，使权限和事件配置生效；确认自己在应用可用范围内。

**长连接模式和事件订阅是两项独立配置。**“已添加事件”列表为空时，即使 WebSocket
连接成功也收不到聊天消息。首次保存长连接设置需要活动连接时，先运行下面的登录流程，
保持程序运行，再在后台保存和发布。

```shell
mini-extra channels login feishu -c channels.yaml
```

按提示填写 App ID 和 App Secret（隐藏输入）。程序先检查应用和机器人，再显示五分钟
有效的临时配对码。给机器人**私聊**发送 `/pair 六位码`。只有正确配对者进入允许名单；
普通陌生人消息和群聊配对被忽略。无需手动查 open_id。

完成后将 `accounts.feishu.enabled` 改为 `true`，启动服务。需要自动化配置时也支持
`FEISHU_APP_ID` / `FEISHU_APP_SECRET` 和显式 `allowed_users`；环境变量名可在账号配置中指定。
应用凭据和配对身份必须匹配。多机器人用不同账号配置名区分。

SDK 负责长连接重连；接收器在独立子进程中运行，不阻塞微信轮询。`channels status`
显示 `connected`、`receiving`、`reconnecting` 等连接状态。只支持用户发送的纯文本事件，
不将其他机器人消息作为用户指令。

## 使用与会话

发送文字即排队执行任务，平台会收到开始通知及最终结果。任务处理使用新的 Agent 实例，
并注入同一会话最近最多六轮已完成任务的用户请求与最终答复（最多 24,000 字符）。
原始工具输出和内部推理不会自动发到聊天中；这是有界会话历史，不是完整工具上下文恢复。

```text
/help      查看帮助
/status    查询自己当前会话最近任务
/cancel    取消自己当前会话的排队任务和活动任务
/new       当前任务结束后，开始新的上下文段
```

会话键包含渠道、账号、聊天会话和发送者；其他用户和账号不能查询或取消此会话任务。
群聊默认关闭，可明确设置 `allow_groups: true`，仍受用户白名单约束。
同一 Gateway 串行执行任务，以免多个 Agent 同时修改共享工作区；不同会话保持各自历史。

原生工具模型额外注册 `channel_finish`，用于明确提交最终回复。`/status` 读取阶段和
模型调用计数；不转发思维链。单次任务受步骤、费用和墙钟预算限制。费用限制沿用原有
调用后记账语义，不是供应商端的硬消费上限。

## 凭据、存储与恢复

默认状态目录为全局配置目录下的 `channels/`，也可显式设置 `state_directory`。
Windows 使用当前用户 DPAPI 保护登录和应用凭据；Unix 使用目录 `0700` 和文件 `0600`。
Windows 数据目录继承用户目录 ACL；同用户代码和本地管理员仍然有权读取运行时数据。
SQLite 与轨迹含聊天记录和工具收据，应放在私人目录，不要提交 Git。

收件箱根据渠道、账号和 provider message_id 去重；微信游标与收件箱写入同一事务。
只有受信任用户的消息进入任务队列，任务开始前和发送回复前再次检查权限。
Feishu WebSocket 事件在成功落盘后才返回 SDK 应答。

发件箱每个片段具有稳定 client_id/uuid，按 UTF-8 字节分片。超时、网络失败或进程中断后
可能无法判断消息是否已经送达，记录为 `unknown`，不悄悄自动重发。
在 `channels status` 的 `undelivered` 中查看片段 ID，核实未送达后才能显式执行：

```shell
mini-extra channels retry-reply FRAGMENT_ID -c channels.yaml
```

重试可能产生重复消息。重启会终止匹配 PID 创建时间的遗留受管进程，将未结束任务标记
`interrupted`；**不自动重放**可能已经产生文件或远程副作用的工具。检查 `runs.sqlite3`、
轨迹和工作区后，再决定是否发送新任务。取消先请求协作停止，五秒后可强制结束受管
任务进程树；供应商端已发出的请求或宿主外服务不保证被撤销。

`channels logout ACCOUNT` 删除本地登录；先停止服务以清除内存中的凭据。在微信或飞书
后台撤销绑定/应用访问是另一项操作，不由本地删除代替。

本地诊断日志位于状态目录的 `artifacts/`，错误回复只含异常类型，避免把凭据或堆栈
直接发到聊天。服务不对公网开放 HTTP 端口，来源 URL 限制为平台 HTTPS 域名；仅回环
HTTP 地址用于本地协议测试。TLS 验证保持开启，不跟随微信 API 的 HTTP 重定向。

## 验证

```shell
python -m pytest tests/run/test_channels.py
```

测试使用真实 HTTP 服务、官方飞书 SDK、WebSocket protobuf 事件、SQLite、Bash 和
Agent 子进程，覆盖扫码/PIN、身份配对、白名单、重复事件、会话隔离、发件不确定性、
重启恢复及凭据保护。真人平台联调和真实付费模型结果单独记录，不以本地测试代替。
