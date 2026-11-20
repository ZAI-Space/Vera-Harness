[English](channels.md) · [简体中文](zh/channels.md)

# Weixin and Feishu channels

The independent `vera.channels` module reuses the shared Runtime for models, tools, Skills, MCP, plugins, Subagents and sandboxes. Connections are outbound: no public IP, webhook listener or tunnel is required.

## Install and start

```bash
python -m pip install -e '.[channels,mcp]'
vera-extra channels init --workspace .
```

```yaml
workspace: /absolute/path/to/workspace
agent_config: model.yaml
sandbox: local
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

The agent overlay is merged onto built-in `vera.yaml`. Keep provider keys in environment variables. Relative paths resolve from the channel config file. Chat messages cannot change the workspace, provider settings, tools or budgets. Use `sandbox: auto` only when an available isolated backend is configured; it fails rather than falling back to local. Docker images must exist locally; host MCP/network opt-ins still apply.

```bash
vera-extra channels login weixin -c channels.yaml
vera-extra channels start -c channels.yaml
vera-extra channels status -c channels.yaml
vera-extra channels stop -c channels.yaml
```

## Weixin QR login

The adapter follows Tencent/openclaw-weixin's protocol at `0ad1ae91347a938f52f1e4e2abd6dcda51e05f9e`. It does not embed OpenClaw. Login displays a terminal QR and an absolute temporary PNG path. Scan and confirm with the operator's phone; enter a PIN through hidden input if requested. An expired QR is replaced, and login cleanup deletes temporary images. Never keep using an old screenshot.

By default only the paired owner is allowed. Explicit `allowed_users` replaces the list; wildcards are rejected. Accounts keep separate credentials and poll cursors. A `-14` response requires login again. Text and platform-provided voice transcription are supported. Attachments, encrypted CDN downloads, speech recognition and multimedia replies are not implemented.

## Feishu application pairing

Use an enterprise self-built application with the official `lark-oapi` SDK, not a group webhook robot or a user's password.

1. Enable the application bot and obtain App ID/App Secret.
2. Grant `im:message.p2p_msg:readonly` and `im:message:send_as_bot`.
3. Select long-connection delivery and subscribe to `im.message.receive_v1`.
4. Publish the application and include the operator in its availability scope.
5. Run `vera-extra channels login feishu -c channels.yaml`; provide the application credentials through hidden input, then privately send `/pair SIX_DIGIT_CODE` to the bot within five minutes.

Long-connection mode and the event subscription are separate settings. A connected socket without the message event will not deliver chat tasks. Keep login running if the developer console requires an active connection before saving, then publish. No manual open_id lookup is needed after pairing. Enable the account before starting the service.

Automated setup can use `FEISHU_APP_ID`, `FEISHU_APP_SECRET` and explicit allowed users. Credentials and paired identity must match. The SDK reconnects in its own receiver process, without blocking Weixin polling. Status distinguishes connection/reconnection/receiving phases. Only user text is accepted, not instructions from another bot.

## Conversations and commands

```text
/help
/status
/cancel
/new
```

Text messages queue tasks and receive start/final notices. Each task creates a fresh Agent with up to six completed user/final-response pairs (24,000 characters); full tool transcripts and internal reasoning are not forwarded. Conversation keys include channel, account, chat and sender. Users cannot inspect or cancel other conversations. Groups are disabled unless `allow_groups: true`, still subject to user allowlists. One Gateway serializes execution against its shared workspace. `channel_finish` lets native tool models submit the reply. The terminal's entire slash catalog, plan/goal controls and market installs are not automatically channel commands.

## Persistence and recovery

The default private `channels/` directory stores credentials, inbox/outbox, runs and trajectories. Windows uses user DPAPI for credentials and inherited ACLs; Unix uses directory 0700 and file 0600. Same-user code and administrators retain their platform authority. SQLite histories are private data, not credentials safe to commit.

Incoming provider IDs deduplicate messages; Weixin cursor/inbox updates share a transaction. Access is checked before enqueue, execution and reply. Feishu acknowledges events only after durable storage. Replies have stable IDs and UTF-8 byte chunks. Uncertain sends become `unknown`; inspect `undelivered` before explicitly retrying:

```bash
vera-extra channels retry-reply FRAGMENT_ID -c channels.yaml
```

A retry can duplicate a delivered reply. Restart cleans only processes matching recorded PID creation identities, marks interrupted tasks and never automatically replays uncertain effects. Inspect RunStore, trajectory and workspace before resubmission. Cancellation requests cooperation before bounded process-tree termination; external calls already issued may continue. Logout clears local credentials; provider-side revocation remains a separate operator action.

## Verification

```bash
python -m pytest tests/run/test_channels.py
```

Tests use real local HTTP, the official SDK/WebSocket events, SQLite, Bash and agent subprocesses. Actual human platform pairing and paid model tests require separate evidence. Logs are in private `artifacts/`; chat errors expose exception types rather than secret-bearing tracebacks. Platform API URLs are restricted, HTTPS validation stays enabled, and Weixin API redirects are not followed.
