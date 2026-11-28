[English](desktop-api.md) · [简体中文](zh/desktop-api.md)

# Desktop API boundaries

The desktop service is an owner-local application interface. It is not a public multi-tenant API. Keep its connection file private.

## Local transport

The launcher creates a discovery file containing `url` and `token`. The service binds numeric `127.0.0.1`; its token has at least 32 characters. Electron main reads the file. Renderer code uses the fixed preload methods and never receives the transport token.

| Request | Result | Boundary |
| --- | --- | --- |
| `GET /health` | `ok`, `protocolVersion`, `cursor` | Bearer authentication; no model execution. |
| `POST /invoke` | `{result: ...}` or `{error: ...}` | Bearer authentication, no browser Origin, JSON object, body at most 12 MB. |
| `GET /events?after=<cursor>` | `cursor`, `events`, optional `reset` | Authenticated long polling; reload session baseline after reset. |

```http
POST /invoke HTTP/1.1
Host: 127.0.0.1:<port>
Authorization: Bearer <private-token>
Content-Type: application/json

{"method":"listAllSessions","args":{}}
```

The token in this example is a placeholder. Do not expose the service through a public reverse proxy. Unknown methods fail explicitly. Failed mutations are not automatically replayed.

## Application methods

TypeScript contracts live in `desktop/src/contracts`; dispatch lives in `src/vera/desktop/service.py` and `capabilities.py`. Use those definitions for complete field types.

| Domain | Representative methods | Side effects / conditions |
| --- | --- | --- |
| Sessions | `createSession`, `prompt`, `abort`, `getSessionBaseline` | Project must exist; running sessions reject configuration/history mutations. |
| Permissions | `setSessionSelections`, `respondPermission` | Allow once/deny; approval binds request and active session. |
| Providers | `listProviders`, `listModels`, `addCustomProvider` | Credential presence can be returned; stored keys are not returned. |
| MCP / Skills / plugins | `probeMcpServer`, `getLoadedResources`, `pluginAction` | Probe starts a configured transport and lists tools; installation and activation remain separate. |
| Background | `saveScheduledTask`, `scheduledAction`, `runTaskboardTask` | Schedule needs explicit unattended policy; taskboard execution checks current task state. |
| Maintenance | `previewSessionProjectDeletion`, `deleteSessionProject` | Expiring single-use preview; removes session records, not project source. |
| Media | See `media_maintenance.py` method table | Explicit confirmation, authoritative session ownership and backup/fingerprint checks. |

An authenticated local caller has desktop-owner authority. Use the method contracts above when integrating a client.

`prompt({sessionId,text,document?,images?,interrupt?})` starts an idle session or queues input behind an active task. The queue holds at most 20 messages and normally runs in first-in, first-out order. With `interrupt: true`, an active worker stops and the new input runs before existing follow-ups; those follow-ups keep their order. The same queue limit applies. Sending while the worker is stopping or sending a slash command during an active task fails explicitly. In the desktop composer, use Send now to request interruption.

Queued input is removed only after its worker starts. If startup fails, the input remains available for recovery. `clearQueue({sessionId})` atomically clears the queue and returns `steering: []`, queued text in `followUp`, and complete input in `followUpInputs`. Each input contains its `document` (including file references) and `images`; plain text receives a text-only document. Use the returned input to restore the composer before retrying.

## LAN and messaging

LAN is disabled on startup. Enabling it starts a separate HTTP listener with a fresh pairing token in the URL fragment. `GET /api/snapshot` needs that token. `POST /api/action` also requires remote control to be enabled and permits only `prompt`, `abort` and `respondPermission`. Host/Origin and current session are checked. Remote prompts cannot issue configuration slash commands.

LAN transport uses plain HTTP: use a trusted private network. Anyone with the pairing link receives its granted visibility; do not publish the link. Disable the listener to revoke its token. Messaging channels instead use their configured provider identity, paired-user allowlist and conversation routing. See [channels](channels.md).

The optional taskboard has its own loopback capability URL and separate upstream HTTP implementation. Desktop service authentication does not substitute for that implementation's route controls.
