"""Configure, log in and run the independent Weixin/Feishu remote channel gateway."""

import json
import os
import signal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
import yaml

from minisweagent.channels import ChannelError, load_config
from minisweagent.channels.credentials import CredentialStore, private_directory
from minisweagent.channels.gateway import ChannelGateway
from minisweagent.channels.store import ChannelStore
from minisweagent.channels.weixin import WeixinClient
from minisweagent.channels.weixin import login as weixin_login

app = typer.Typer(help="Connect Weixin and Feishu to Vera's runtime.", no_args_is_help=True)
ConfigPath = Annotated[Path, typer.Option("--config", "-c", help="Channel gateway YAML file.")]


@app.command("init")
def initialize(config: ConfigPath = Path("channels.yaml"), workspace: Path = Path(".")) -> None:
    """Create a nonsecret starting config; choose local explicitly if isolation isn't available."""
    if config.exists():
        raise typer.BadParameter("Config already exists; edit it instead of overwriting it.")
    config.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "workspace": str(workspace.resolve()),
        "agent_config": "mini.yaml",
        "sandbox": "auto",
        "accounts": {
            "weixin": {"channel": "weixin", "enabled": True},
            "feishu": {"channel": "feishu", "enabled": False, "allowed_users": []},
        },
    }
    config.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    typer.echo(f"Created {config.resolve()}. Set the model/profile and execution mode, then log in.")


@app.command()
def login(account: str = "weixin", config: ConfigPath = Path("channels.yaml")) -> None:
    """Show a Weixin QR code; only explicit phone approval persists bot credentials."""
    settings = load_config(config)
    if account not in settings.accounts:
        raise typer.BadParameter("Choose a configured channel account.")
    if settings.accounts[account].channel == "feishu":
        from minisweagent.channels.feishu import pair_account

        app_id = typer.prompt("Feishu App ID")
        secret = typer.prompt("Feishu App Secret", hide_input=True)
        try:
            pair_account(
                settings,
                account,
                lambda code: typer.echo(f"Send /pair {code} privately to your Feishu bot within five minutes."),
                credentials={"app_id": app_id, "app_secret": secret},
            )
        except ChannelError as error:
            raise typer.BadParameter(str(error)) from None
        typer.echo("Feishu user paired; credentials are protected locally. Enable this account and start the gateway.")
        return
    try:
        import qrcode
    except ImportError:
        raise typer.BadParameter("Install mini-swe-agent[channels] for QR-code rendering.") from None
    directory = private_directory(settings.state_directory)
    images = []

    def show_qr(value: str):
        destination = directory / f"login-qr-{uuid4().hex[:8]}.png"
        images.append(destination)
        code = qrcode.QRCode(border=2)
        code.add_data(value)
        code.make(fit=True)
        code.make_image().save(destination)
        if os.name != "nt":
            destination.chmod(0o600)
        code.print_ascii(invert=True)
        typer.echo(f"QR image: {destination}\nScan using your own Weixin account and approve the binding.")

    client = WeixinClient(base_url=settings.accounts[account].api_base)
    try:
        credentials = weixin_login(
            client, show_qr, lambda: typer.prompt("Enter the PIN displayed on your phone", hide_input=True)
        )
        CredentialStore(settings.state_directory).save(account, credentials)
        typer.echo(f"Weixin account {account!r} logged in. The scanning user is the default allowed user.")
    except ChannelError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        client.close()
        for destination in images:
            destination.unlink(missing_ok=True)


@app.command()
def logout(account: str = "weixin", config: ConfigPath = Path("channels.yaml")) -> None:
    """Remove the local Weixin token; stop the gateway first to clear in-memory credentials."""
    settings = load_config(config)
    CredentialStore(settings.state_directory).delete(account)
    typer.echo("Local credentials removed. Revoke the binding in Weixin if needed.")


@app.command()
def start(config: ConfigPath = Path("channels.yaml")) -> None:
    """Run until Ctrl+C. Only authorized messages enter the durable task queue."""
    gateway = ChannelGateway(load_config(config))
    previous = {}
    for name in (signal.SIGINT, signal.SIGTERM):
        previous[name] = signal.signal(name, lambda *_: gateway.stop_event.set())
    try:
        typer.echo("Starting channel gateway. Use Ctrl+C to stop; send /help, /status or /cancel in chat.")
        gateway.serve()
    except ChannelError as error:
        raise typer.BadParameter(str(error)) from None
    finally:
        for name, handler in previous.items():
            signal.signal(name, handler)


@app.command()
def stop(config: ConfigPath = Path("channels.yaml")) -> None:
    """Request gateway shutdown from another terminal without killing unrelated processes."""
    settings = load_config(config)
    private_directory(settings.state_directory).joinpath("gateway.stop").touch()
    typer.echo("Gateway shutdown requested.")


@app.command()
def status(config: ConfigPath = Path("channels.yaml")) -> None:
    """Show durable task/delivery counts and transport status without exposing credentials."""
    settings = load_config(config)
    typer.echo(json.dumps(ChannelStore(settings.state_directory).status(), ensure_ascii=True, indent=2))


@app.command("retry-reply")
def retry_reply(identifier: str, config: ConfigPath = Path("channels.yaml")) -> None:
    """Explicitly retry one failed/unknown delivery after checking whether it arrived; may duplicate it."""
    store = ChannelStore(load_config(config).state_directory)
    with store.connect() as db:
        result = db.execute(
            "UPDATE outbox SET status = 'pending' WHERE id = ? AND status IN ('failed', 'unknown')", (identifier,)
        )
        if not result.rowcount:
            raise typer.BadParameter("No failed/unknown reply with this ID.")


if __name__ == "__main__":
    app()
