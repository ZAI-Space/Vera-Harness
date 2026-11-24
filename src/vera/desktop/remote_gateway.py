"""Connect the existing Weixin/Feishu transports to inspectable desktop conversations."""

import threading
import time
from pathlib import Path

from vera.channels.config import InboundMessage
from vera.channels.gateway import ChannelGateway
from vera.channels.store import ChannelStore


def validate_session(desktop, key: str) -> dict:
    """Validate a writable, configured chat before accepting a remote binding or switch."""
    value = desktop.sessions.get(key)
    if value["meta"].get("parentSessionId") or value["meta"].get("archivedAt"):
        raise ValueError("请选择一个可继续对话的普通会话。")
    if value.get("permissionPolicy") == "human" or not value["meta"].get("model"):
        raise ValueError("请先为这个对话配置模型和 Agent 权限模式。")
    if not desktop.providers.definition(value["meta"]["model"]):
        raise ValueError("该对话绑定的模型已失效，请先打开对话并切换到当前可用模型。")
    desktop.sessions.config(value)
    return value


class DesktopChannelStore(ChannelStore):
    """Retain durable deduplication while allowing scoped, nonce-specific remote approval."""

    def __init__(self, directory, gateway):
        self.gateway = gateway
        super().__init__(directory)

    def dispatch_received(self) -> None:
        """Dispatch durable SDK ingress in receive order on the desktop host.

        The Feishu listener runs in a subprocess and cannot mutate desktop session
        bindings. It acknowledges only after persistence; commands run here.
        """
        with self.connect() as db:
            rows = db.execute("SELECT * FROM messages WHERE status='received' ORDER BY rowid LIMIT 100").fetchall()
            for row in rows:
                message = InboundMessage.model_validate_json(row["payload"])
                command = message.text.strip()
                status = "command" if command.startswith("/") or not command else "queued"
                epoch = db.execute("SELECT epoch FROM sessions WHERE id=?", (message.session_id,)).fetchone()[0]
                db.execute("UPDATE messages SET status=?,epoch=? WHERE id=?", (status, epoch, row["id"]))
                if status == "command":
                    self._command(db, message, command)

    def _command(self, db, message, command):
        action, _, nonce = command.partition(" ")
        if action == "/session":
            action = "/sessions"
        if action in {"/sessions", "/switch", "/help"}:
            self._routing_command(db, message, action, nonce.strip())
            return
        if action not in {"/allow", "/deny"}:
            super()._command(db, message, command)
            return
        current = self.gateway.current
        text = "当前没有匹配的待审批操作；如已在桌面放行，无需重复审批。"
        if current and InboundMessage.model_validate_json(current["payload"]).session_id == message.session_id:
            desktop = self.gateway.desktop
            nonce = nonce.strip()
            candidates = [
                row
                for row in list(desktop.sessions.approvals.values())
                if row["sessionId"] == self.gateway.execution_session
            ]
            pending = (
                desktop.sessions.approvals.get(nonce) if nonce else candidates[0] if len(candidates) == 1 else None
            )
            if not nonce and len(candidates) > 1:
                text = "当前有多个待审批操作，请在 /allow 或 /deny 后附上对应的审批编号。"
            if pending and pending["sessionId"] == self.gateway.execution_session:
                try:
                    desktop.sessions.respond(
                        {
                            "sessionId": pending["sessionId"],
                            "requestId": pending["id"],
                            "answer": "allow" if action == "/allow" else "deny",
                        }
                    )
                except ValueError:
                    pass  # A desktop click may have already resolved this exact nonce.
                else:
                    text = "已允许这一次操作。" if action == "/allow" else "已拒绝这一次操作。"
        self._reply(db, message, text, "approval")

    def _routing_command(self, db, message, action, target):
        """Handle paired-user routing locally; these commands never reach the model."""
        desktop = self.gateway.desktop
        if action == "/sessions":
            rows = sorted(desktop.metas(), key=lambda row: row.get("modifiedAt", 0), reverse=True)
            available = []
            for row in rows:
                try:
                    validate_session(desktop, row["sessionId"])
                except ValueError:
                    continue
                available.append(f"{row['sessionId']} · {row.get('name') or '未命名对话'}")
                if len(available) == 20:
                    break
            text = "可用对话（最近 20 条）：\n" + "\n".join(available) + "\n发送 /switch 对话ID 切换。"
        elif action == "/help":
            text = "/sessions 列出对话；/switch 对话ID 切换；/new 新建上下文；/status 查询；/cancel 取消；/pause 查看暂停说明；/allow 或 /deny 回答当前审批。"
        else:
            active = db.execute(
                "SELECT 1 FROM messages WHERE session=? AND status IN ('queued','running')",
                (message.session_id,),
            ).fetchone()
            if active:
                text = "本聊天仍有执行中或排队的任务，请先 /cancel 并等待结束，再切换对话。"
            else:
                try:
                    validate_session(desktop, target)
                except (KeyError, ValueError):
                    text = "目标对话不可用，请用 /sessions 查看有效对话ID。"
                else:
                    epoch = db.execute("SELECT epoch FROM sessions WHERE id=?", (message.session_id,)).fetchone()[0]
                    desktop.store.save("remote-route", self.gateway.route_key(message, epoch), target)
                    self.gateway.last_session = target
                    text = f"已切换到：{desktop.sessions.get(target)['meta'].get('name') or target}。后续消息沿用目标对话的模型、目录和权限。"
        self._reply(db, message, text, "routing")


class DesktopChannelGateway(ChannelGateway):
    """Reuse existing collectors/outbox; execute through Sessions instead of a second Agent loop."""

    def __init__(self, config, desktop, session_id):
        super().__init__(config)
        self.desktop = desktop
        self.root_session = session_id
        self.execution_session = None
        self.last_session = session_id
        self.route_lock = threading.RLock()
        self.routing_generation = desktop.store.get("remote-routing-generation", next(iter(config.accounts)), 0)
        self.store = DesktopChannelStore(config.state_directory, self)

    def route_key(self, message, epoch) -> str:
        """Isolate overrides by default binding, sender conversation and /new generation."""
        return f"{self.root_session}/{self.routing_generation}/{message.session_id}/{epoch}"

    def _feishu_loop(self, name: str) -> None:
        """Let the SDK subprocess receive only; desktop routing stays on its owning host."""
        while not self.stop_event.is_set():
            self.store.connection(name, "listener_running")
            self._spawn(["--feishu", name, "--desktop-inbox"], f"transport-{name}", 86_400, self.stop_path)
            if self.stop_event.wait(5):
                return
            self.store.connection(name, "reconnecting")

    def tick(self) -> None:
        self.store.dispatch_received()
        super().tick()

    def switch_session(self, key: str) -> None:
        """Change this channel's default only while its inbox is idle; do not restart collectors."""
        with self.route_lock, self.store.connect() as db:
            if db.execute("SELECT 1 FROM messages WHERE status IN ('queued','running','received')").fetchone():
                raise ValueError("本通道仍有执行中或排队的任务，请等待完成或取消后再切换。")
            validate_session(self.desktop, key)
            self.root_session = key
            self.last_session = key
            self.routing_generation += 1
            channel = next(iter(self.config.accounts))
            self.desktop.store.save("remote-binding", channel, key)
            self.desktop.store.save("remote-routing-generation", channel, self.routing_generation)

    def _execute(self, row: dict, cancel: Path) -> None:
        message = InboundMessage.model_validate_json(row["payload"])
        key = None
        try:
            with self.route_lock, self.desktop.sessions.lock:
                mapping = self.route_key(message, row["epoch"])
                key = self.desktop.store.get("remote-route", mapping)
                if not key:
                    key = self.root_session
                    if row["epoch"]:
                        previous = self.desktop.store.get(
                            "remote-route", self.route_key(message, row["epoch"] - 1), self.root_session
                        )
                        root = self.desktop.sessions.get(previous)
                        value = self.desktop.store.create_session(
                            {
                                "cwd": root["meta"]["cwd"],
                                **root["meta"]["model"],
                                "thinkingLevel": root["meta"].get("thinkingLevel", "default"),
                            }
                        )
                        key = value["meta"]["sessionId"]
                        value["permissionPolicy"] = root.get("permissionPolicy", "confirm")
                        value["meta"]["name"] = f"{message.channel} · 新对话"
                        self.desktop.save_session(value)
                        self.desktop.events.emit("onSessionCatalogChanged", {"revision": key, "complete": True})
                    self.desktop.store.save("remote-route", mapping, key)
                if key in self.desktop.sessions.running:
                    raise ValueError("这个对话正在执行，请稍后重试，或先在微信/飞书发送 /cancel。")
                self.desktop.sessions.prompt(key, message.text)
                self.execution_session = key
                self.last_session = key
            permissions = set()
            while key in self.desktop.sessions.running:
                if self.stop_event.is_set() or cancel.exists() or self.store.get(row["id"])["cancel"]:
                    self.desktop.sessions.abort(key)
                for nonce, pending in list(self.desktop.sessions.approvals.items()):
                    if pending["sessionId"] == key and nonce not in permissions:
                        with self.store.connect() as db:
                            self.store._reply(
                                db,
                                message,
                                f"需要确认：{pending['title']}\n{pending['message']}\n"
                                f"允许一次请发送 /allow {nonce}\n拒绝请发送 /deny {nonce}\n"
                                "只有一个待审批操作时，也可以直接发送 /allow 或 /deny。",
                                "permission-" + nonce,
                            )
                        permissions.add(nonce)
                value = self.desktop.sessions.get(key)
                self.store.progress(row["id"], f"桌面对话：{key}；已记录 {len(value['messages'])} 条消息。")
                time.sleep(0.2)
            result = self.desktop.sessions.get(key).get("lastRunResult") or {}
            status = result.get("exit_status", "WorkerFailed")
            self.store.finish(
                row["id"],
                "completed" if status == "Submitted" else "cancelled" if status == "Cancelled" else "failed",
                result.get("submission") or f"执行已结束：{status}。请在桌面查看工具记录。",
            )
        except Exception as error:
            self.store.finish(
                row["id"],
                "failed",
                str(error) if isinstance(error, ValueError) else "远程执行失败，请在桌面检查运行记录。",
            )
        finally:
            self.execution_session = None
