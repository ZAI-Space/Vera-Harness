"""Supervise two message transports and one bounded runtime worker; no inbound network port."""

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread

from vera.channels.config import AccountConfig, ChannelConfig, ChannelError, InboundMessage
from vera.channels.credentials import CredentialStore, private_directory
from vera.channels.store import ChannelStore
from vera.channels.weixin import DeliveryRejected, SessionExpired, WeixinClient, normalize_message
from vera.config import get_config_from_spec
from vera.evolution.process import recover_processes, run_process
from vera.utils.serialize import recursive_merge


def authorized(account: AccountConfig, message: InboundMessage, owner: str = "") -> bool:
    """Apply the host's user allowlist before storing, replying or creating a model request."""
    allowed = account.allowed_users or ([owner] if account.channel == "weixin" and owner else [])
    return (
        account.enabled
        and message.channel == account.channel
        and message.user in allowed
        and (account.allow_groups or not message.is_group)
    )


@contextmanager
def gateway_lock(directory: Path):
    """Own one private store across processes; OS release on crash permits safe reconciliation."""
    with (directory / "gateway.lock").open("a+b") as stream:
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ChannelError("Another channel gateway owns this state directory.") from None
        yield


class ChannelGateway:
    """Long-lived transport supervisor; tasks use fresh agents and scoped bounded history."""

    def __init__(self, config: ChannelConfig):
        self.config = config
        self.store = ChannelStore(config.state_directory)
        self.credentials = CredentialStore(config.state_directory)
        self.stop_event = Event()
        self.senders = {}
        self.threads: list[Thread] = []
        self.worker: Thread | None = None
        self.current: dict | None = None
        self.cancelled_at: float | None = None
        self.last_progress = 0.0
        self.stop_path = config.state_directory / "gateway.stop"
        self.environment = os.environ | {
            "VERA_SILENT_STARTUP": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(Path(__file__).resolve().parents[2]), os.environ.get("PYTHONPATH", "")])
            ),
        }

    def _spawn(self, arguments: list[str], name: str, timeout: float, cancel: Path) -> dict:
        log = private_directory(self.config.state_directory / "artifacts" / name) / "process.log"
        return run_process(
            [
                sys.executable,
                "-m",
                "vera.channels.worker",
                "--state",
                str(self.config.state_directory),
                *arguments,
            ],
            cwd=self.config.workspace,
            env=self.environment,
            log=log,
            timeout=timeout,
            cancel=cancel,
        )

    def _weixin_loop(self, name: str, settings: AccountConfig) -> None:
        client = WeixinClient(self.credentials.load(name), base_url=settings.api_base)
        backoff = 1
        try:
            while not self.stop_event.is_set():
                try:
                    response = client.updates(self.store.cursor(name))
                    accepted = []
                    for raw in response.get("msgs", []):
                        try:
                            message = normalize_message(name, raw)
                            if message and authorized(settings, message, client.owner):
                                accepted.append(message)
                        except (ValueError, KeyError, TypeError, ChannelError):
                            continue  # Malformed events can't prevent acknowledgement of valid siblings.
                    self.store.accept(accepted, account=name, cursor=response.get("get_updates_buf"))
                    self.store.connection(name, "polling")
                    backoff = 1
                except SessionExpired:
                    self.store.connection(name, "login_required")
                    return
                except Exception as error:
                    self.store.connection(name, f"retrying:{type(error).__name__}")
                    if self.stop_event.wait(backoff):
                        return
                    backoff = min(backoff * 2, 30)
        finally:
            client.close()

    def _feishu_loop(self, name: str) -> None:
        while not self.stop_event.is_set():
            self.store.connection(name, "listener_running")
            self._spawn(["--feishu", name], f"transport-{name}", 86_400, self.stop_path)
            if self.stop_event.wait(5):
                return
            self.store.connection(name, "reconnecting")

    def _execute(self, row: dict, cancel: Path) -> None:
        try:
            outcome = self._spawn(["--message", row["id"]], row["id"], self.config.task_timeout + 60, cancel)
            if self.store.get(row["id"])["status"] == "running":
                status = "cancelled" if outcome["status"] == "cancelled" else "interrupted"
                self.store.finish(
                    row["id"],
                    status,
                    "任务进程结束，未完成的工具结果可能未知；请在本机核实后再发起任务，系统不会自动重放。",
                )
        except Exception as error:
            self.store.finish(row["id"], "failed", f"无法运行任务：{type(error).__name__}。请检查本机配置。")

    def tick(self) -> None:
        """Dispatch one result and advance task supervision; receiver threads continue independently."""
        reply = self.store.pending_reply(set(self.senders))
        if reply:
            data = json.loads(reply["payload"])
            message = InboundMessage.model_validate(data["message"])
            if not authorized(
                self.config.accounts[message.account], message, getattr(self.senders[message.account], "owner", "")
            ):
                self.store.sent(reply["id"], "failed")
                return
            try:
                self.senders[reply["account"]].send(message, data["text"], reply["id"])
            except DeliveryRejected:
                self.store.sent(reply["id"], "failed")
            except Exception:
                self.store.sent(reply["id"], "unknown")
            else:
                self.store.sent(reply["id"], "sent")
        if self.worker and self.worker.is_alive():
            row = self.store.get(self.current["id"])
            if row["cancel"]:
                self.cancelled_at = self.cancelled_at or time.monotonic()
                if time.monotonic() - self.cancelled_at >= 5:
                    (self.config.state_directory / f"{row['id']}.cancel").touch()
            return
        self.worker, self.current, self.cancelled_at = None, None, None
        row = self.store.claim()
        if row:
            message = InboundMessage.model_validate_json(row["payload"])
            settings = self.config.accounts.get(message.account)
            if (
                settings is None
                or message.account not in self.senders
                or not authorized(settings, message, getattr(self.senders[message.account], "owner", ""))
            ):
                self.store.finish(row["id"], "cancelled", "账户权限已变更，任务未执行。")
                return
            self.current = row
            cancel = self.config.state_directory / f"{row['id']}.cancel"
            self.worker = Thread(target=self._execute, args=(row, cancel), daemon=True)
            self.worker.start()

    def serve(self) -> None:
        """Acquire the store lease, recover owned processes, connect accounts, and run until stopped."""
        from vera.channels.feishu import FeishuClient

        with gateway_lock(self.config.state_directory):
            recover_processes(self.config.state_directory)
            self.store.reconcile()
            self.stop_path.unlink(missing_ok=True)
            try:
                receivers = []
                for name, settings in self.config.accounts.items():
                    if not settings.enabled:
                        continue
                    if settings.channel == "weixin":
                        self.senders[name] = WeixinClient(self.credentials.load(name), base_url=settings.api_base)
                        target, arguments = self._weixin_loop, (name, settings)
                    else:
                        stored = self.credentials.load(name) if self.credentials.has(name) else {}
                        sender = FeishuClient(settings, stored)
                        if not settings.allowed_users:
                            if stored.get("app_id") != sender.app_id or not stored.get("allowed_users"):
                                raise ChannelError(
                                    "Run channels login for this Feishu account to pair your user, or configure allowed_users."
                                )
                            settings.allowed_users = stored["allowed_users"]
                        self.senders[name] = sender
                        target, arguments = self._feishu_loop, (name,)
                    receivers.append((target, arguments))
                if not self.senders:
                    raise ChannelError("Enable at least one channel account.")
                self.credentials.save(
                    "runtime-profile",
                    {
                        "config": self.config.model_dump(mode="json"),
                        "profile": recursive_merge(
                            get_config_from_spec("vera.yaml"), get_config_from_spec(self.config.agent_config)
                        ),
                    },
                )
                for target, arguments in receivers:
                    thread = Thread(target=target, args=arguments, daemon=True)
                    self.threads.append(thread)
                    thread.start()
                while not self.stop_event.wait(0.1) and not self.stop_path.exists():
                    self.tick()
            finally:
                self.stop()

    def stop(self) -> None:
        """Stop receivers and supervise owned worker cleanup; pending deliveries remain journaled."""
        self.stop_event.set()
        self.stop_path.touch()
        if self.current:
            (self.config.state_directory / f"{self.current['id']}.cancel").touch()
        if self.worker:
            self.worker.join(timeout=20)
        deadline = time.monotonic() + 45
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        for sender in self.senders.values():
            sender.close()
