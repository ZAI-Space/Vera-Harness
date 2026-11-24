// @vitest-environment node
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createServer, request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import {
	CHANNEL_TABLE,
	composerDocumentFromText,
	type DesktopClientApi,
	type EnvironmentApi,
	type SessionBaseline,
	type SessionMeta,
	type SlashCommandInfo,
} from "@vera/contracts";
import { Window } from "happy-dom";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, expect, it } from "vitest";
import { HttpTransport } from "../../../src/main/services/http-transport";

// HttpTransport runs in Electron's Node main process. Keep native fetch while supplying
// a concrete DOM/storage implementation for renderer modules, rather than a mocked API.
const browser = new Window();
const descriptors = new Map<string, PropertyDescriptor | undefined>();
for (const [name, value] of Object.entries({
	window: browser,
	document: browser.document,
	localStorage: browser.localStorage,
})) {
	descriptors.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
	Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
}
afterAll(async () => {
	await browser.happyDOM.close();
	for (const [name, descriptor] of descriptors) {
		if (descriptor) Object.defineProperty(globalThis, name, descriptor);
		else Reflect.deleteProperty(globalThis, name);
	}
});

const { useComposerSend } = await import("../../../src/renderer/src/components/composer/use-composer-send");
const { SlashMenu } = await import("../../../src/renderer/src/components/composer/SlashMenu");
const { setHarnessConnected } = await import("../../../src/renderer/src/harness-api");
const { DEFAULT_BEHAVIOR, useBehaviorPreferencesStore } = await import(
	"../../../src/renderer/src/stores/behavior-preferences"
);
const { draftText, EMPTY_DRAFT, useDraftStore } = await import("../../../src/renderer/src/stores/drafts");
const { DEFAULT_MODEL_ADVANCED, saveModelAdvanced } = await import(
	"../../../src/renderer/src/stores/model-advanced-preferences"
);
const { usePermissionPolicyStore } = await import("../../../src/renderer/src/stores/permission-policy");
const { useSessionsStore } = await import("../../../src/renderer/src/stores/sessions");
const { useSubagentDraftsStore } = await import("../../../src/renderer/src/stores/subagent-drafts");
const { useTranscriptStore } = await import("../../../src/renderer/src/stores/transcript");

/**
 * Value: protects=configuration ACKs precede the real composer prompt and rejection retains its draft;
 * fails_when=the composer skips/does not await configuration or sends a rejected task;
 * why_new=store and backend tests previously exercised the bridge's two sides separately;
 * seam=none; no_claim=Electron IPC or paid provider acceptance (all API calls use real loopback HTTP).
 */
it("commits actual frontend selections before execution and prevents a rejected configuration from starting work", async () => {
	const directory = await mkdtemp(join(tmpdir(), "vera-settings-"));
	if (dirname(resolve(directory)) !== resolve(tmpdir())) throw Error("Unexpected test directory");
	const workspace = join(directory, "project");
	const connectionFile = join(directory, "connection.json");
	await mkdir(workspace);
	const root = resolve(process.cwd(), "..");
	const python =
		process.env.VERA_PYTHON ??
		join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
	const configFile = join(directory, "config.yaml");
	await writeFile(
		configFile,
		JSON.stringify({
			model: {
				model_class: "deterministic",
				model_name: "settings-acceptance",
				outputs: [],
				cost_per_call: 0,
			},
			agent: { system_template: "Use Bash.", instance_template: "{{task}}", mode: "human", cost_limit: 1 },
		}),
	);
	const server = spawn(
		python,
		[
			"-m",
			"vera.desktop.server",
			"--port",
			"0",
			"--directory",
			join(directory, "state"),
			"--config",
			configFile,
			"--connection-file",
			connectionFile,
		],
		{
			cwd: root,
			windowsHide: true,
			env: {
				...process.env,
				PYTHONPATH: join(root, "src"),
				PYTHONUTF8: "1",
				VERA_SILENT_STARTUP: "1",
				LITELLM_LOCAL_MODEL_COST_MAP: "True",
			},
		},
	);
	let serverLog = "";
	server.stdout.on("data", (chunk) => {
		serverLog += chunk.toString();
	});
	server.stderr.on("data", (chunk) => {
		serverLog += chunk.toString();
	});
	const traffic: {
		method: string;
		phase: "request" | "ack";
		status?: number;
		args?: Record<string, unknown>;
	}[] = [];
	const upstreamRequests = new Set<ReturnType<typeof httpRequest>>();
	let upstream = "";
	// An observing proxy forwards the real server's bytes; it never supplies a canned result.
	const proxy = createServer(async (incoming, outgoing) => {
		const chunks: Buffer[] = [];
		for await (const chunk of incoming) chunks.push(Buffer.from(chunk));
		const body = Buffer.concat(chunks);
		const call = incoming.url === "/invoke" ? JSON.parse(body.toString()) : null;
		if (call) traffic.push({ method: call.method, phase: "request", args: call.args });
		const request = httpRequest(
			new URL(incoming.url ?? "/", upstream),
			{
				method: incoming.method,
				headers: {
					Authorization: incoming.headers.authorization ?? "",
					"Content-Type": "application/json",
					"Content-Length": body.length,
				},
			},
			(response) => {
				const responseChunks: Buffer[] = [];
				response.on("data", (chunk) => responseChunks.push(Buffer.from(chunk)));
				response.on("end", () => {
					if (call) traffic.push({ method: call.method, phase: "ack", status: response.statusCode });
					outgoing.writeHead(response.statusCode ?? 502, { "Content-Type": "application/json" });
					outgoing.end(Buffer.concat(responseChunks));
				});
			},
		);
		upstreamRequests.add(request);
		request.once("close", () => upstreamRequests.delete(request));
		request.once("error", () => outgoing.destroy());
		request.end(body);
	});
	let transport: HttpTransport | undefined;
	let sessionId: string | undefined;
	const previousApi = window.vera;
	const previousBehavior = useBehaviorPreferencesStore.getState();
	try {
		await expect
			.poll(
				async () => {
					if (server.exitCode !== null) throw Error(serverLog);
					return JSON.parse(await readFile(connectionFile, "utf8"));
				},
				{ timeout: 20000 },
			)
			.toHaveProperty("url");
		const discovery = JSON.parse(await readFile(connectionFile, "utf8")) as { url: string; token: string };
		upstream = discovery.url;
		await new Promise<void>((ready) => proxy.listen(0, "127.0.0.1", ready));
		const address = proxy.address();
		if (!address || typeof address === "string") throw Error("Expected loopback proxy");
		await writeFile(
			connectionFile,
			JSON.stringify({ ...discovery, url: `http://127.0.0.1:${address.port}` }),
		);
		transport = await HttpTransport.fromFile(connectionFile);
		const connected = transport;
		const environment = Object.fromEntries(
			Object.entries(CHANNEL_TABLE)
				.filter(([, definition]) => definition.scope === "environment")
				.map(([method]) => [method, (args: unknown) => connected.invoke(method, args)]),
		) as unknown as EnvironmentApi;
		// This is a concrete HTTP client for the preload contract, not a response stub.
		window.vera = {
			platform: process.platform,
			forEnvironment: () => environment,
		} as unknown as DesktopClientApi;
		setHarnessConnected(true);
		const meta = (await transport.invoke("createSession", {
			options: { cwd: workspace, provider: "deepseek", modelId: "deepseek-chat" },
		})) as SessionMeta;
		sessionId = meta.sessionId;
		useSessionsStore.setState({ sessions: [meta] });
		useTranscriptStore.getState().loadHistory(sessionId, []);
		transport.subscribe((method, payload) => {
			if (method === "onEvent") {
				const envelope = payload as {
					sessionId: string;
					event: Parameters<ReturnType<typeof useTranscriptStore.getState>["applyEvent"]>[1];
				};
				useTranscriptStore.getState().applyEvent(envelope.sessionId, envelope.event);
			}
		});
		useBehaviorPreferencesStore.setState({
			...DEFAULT_BEHAVIOR,
			permissionPolicy: "confirm",
			commandShell: "system",
		});
		usePermissionPolicyStore.setState({ byTarget: { [sessionId]: "human" } });
		useSubagentDraftsStore.setState({
			drafts: [
				{
					id: "reader",
					name: "reader",
					description: "Read project files",
					instructions: "Inspect files without modification.",
					tools: ["project_read"],
					skills: [],
					step_limit: 3,
					cost_limit: 1,
					wall_time_limit_seconds: 30,
					enabled: true,
				},
			],
		});
		expect(
			saveModelAdvanced("deepseek", [
				{
					id: "deepseek-chat",
					advanced: { ...DEFAULT_MODEL_ADVANCED, toolCallLimit: "3", temperature: "0.8" },
				},
			]),
		).toBe(true);
		const key = sessionId;
		let composer!: ReturnType<typeof useComposerSend>;
		function Probe() {
			composer = useComposerSend({ draftKey: key, activeSessionId: key, imagesSupported: true });
			return null;
		}
		renderToStaticMarkup(createElement(Probe));
		const task = "printf settings-bridge-ok > settings-bridge.txt";
		useDraftStore
			.getState()
			.updateDraft(key, () => ({ ...EMPTY_DRAFT, document: composerDocumentFromText(task) }));
		const firstCall = traffic.length;
		await composer.handleSend();
		expect(
			traffic
				.slice(firstCall)
				.map(({ method, phase, status }) => ({ method, phase, ...(phase === "ack" ? { status } : {}) })),
		).toEqual([
			...(
				[
					"saveBehaviorSettings",
					"saveSubagentRoles",
					"saveSandboxProfiles",
					"getSessionSelections",
					"setSessionSelections",
					"prompt",
				] as const
			).flatMap((method) => [
				{ method, phase: "request" },
				{ method, phase: "ack", status: 200 },
			]),
		]);
		const selection = traffic.find(
			(call) => call.method === "setSessionSelections" && call.phase === "request",
		)?.args;
		expect(selection).toMatchObject({
			permissionPolicy: "human",
			modelOptions: { toolCallLimit: "3", temperature: "0.8" },
			selections: { runMode: "normal", sandbox: null },
		});
		await expect
			.poll(
				async () =>
					((await transport!.invoke("getSessionBaseline", { sessionId: key })) as SessionBaseline).transcript
						.agentActive,
				{ timeout: 20000 },
			)
			.toBe(false);
		const before = (await transport.invoke("getSessionBaseline", { sessionId: key })) as SessionBaseline;
		expect(before.transcript.messages).not.toEqual(
			expect.arrayContaining([
				expect.objectContaining({ text: "Worker exited without a completion receipt." }),
			]),
		);
		expect(await readFile(join(workspace, "settings-bridge.txt"), "utf8")).toBe("settings-bridge-ok");
		await expect
			.poll(() => useTranscriptStore.getState().bySession[key]?.agentActive, { timeout: 10000 })
			.toBe(false);
		expect(
			before.transcript.messages.some((message) => message.kind === "user" && message.text === task),
		).toBe(true);
		expect(await transport.invoke("harnessInvoke", { method: "getBehaviorSettings" })).toMatchObject({
			permissionPolicy: "confirm",
			commandShell: "system",
		});
		expect(await transport.invoke("harnessInvoke", { method: "getSubagentRoles" })).toMatchObject([
			{ name: "reader", enabled: true },
		]);

		useBehaviorPreferencesStore.setState({ commandShell: "pwsh" });
		const rejected = "printf unexpected > rejected.txt";
		useDraftStore
			.getState()
			.updateDraft(key, () => ({ ...EMPTY_DRAFT, document: composerDocumentFromText(rejected) }));
		const rejectedCall = traffic.length;
		await composer.handleSend();
		expect(
			traffic
				.slice(rejectedCall)
				.map(({ method, phase, status }) => ({ method, phase, ...(phase === "ack" ? { status } : {}) })),
		).toEqual([
			{ method: "saveBehaviorSettings", phase: "request" },
			{ method: "saveBehaviorSettings", phase: "ack", status: 400 },
		]);
		expect(draftText(useDraftStore.getState().bySession[key] ?? EMPTY_DRAFT)).toBe(rejected);
		expect(useDraftStore.getState().errorsBySession[key]?.detail).toContain("Bash 环境不可用");
		expect(useDraftStore.getState().pendingBySession[key]).toBeUndefined();
		expect(useTranscriptStore.getState().bySession[key]?.agentActive).toBe(false);
		expect(
			useTranscriptStore
				.getState()
				.bySession[key]?.messages.some((message) => message.kind === "user" && message.text === rejected),
		).toBe(false);
		expect(
			((await transport.invoke("getSessionBaseline", { sessionId: key })) as SessionBaseline).transcript
				.messages,
		).toEqual(before.transcript.messages);
		await expect(readFile(join(workspace, "rejected.txt"))).rejects.toMatchObject({ code: "ENOENT" });

		const unavailable = "unavailable-settings";
		const sandbox = (await transport.invoke("harnessInvoke", {
			method: "saveSandboxProfiles",
			args: {
				profiles: [
					{
						name: unavailable,
						mode: "docker",
						docker_image: `${basename(directory).toLowerCase()}-uncached:never`,
					},
				],
				cwd: workspace,
			},
		})) as {
			status: {
				configured: boolean;
				enabled: boolean;
				choices: { name: string; available: boolean; reason: string }[];
			};
		};
		expect(sandbox.status).toMatchObject({
			configured: true,
			enabled: false,
			choices: [{ name: unavailable, available: false }],
		});
		const reason = sandbox.status.choices[0]?.reason;
		expect(reason).toBe(
			"A local Linux Docker engine must be running and the configured image must already be cached.",
		);
		const commands = (await transport.invoke("listSlashCommandsForCwd", {
			cwd: workspace,
		})) as SlashCommandInfo[];
		expect(commands.find((command) => command.name === "sandbox")).toMatchObject({ supported: false });
		expect(commands.find((command) => command.name === `sandbox:${unavailable}`)).toMatchObject({
			supported: false,
			description: reason,
		});
		const menu = browser.document.createElement("div");
		menu.innerHTML = renderToStaticMarkup(
			createElement(SlashMenu, {
				commands,
				query: "sandbox",
				selectedIndex: 0,
				onSelectedIndexChange: () => {
					throw Error("Static rendering must not change selection");
				},
				onPick: () => {
					throw Error("Disabled sandbox must not be invoked");
				},
			}),
		);
		const choices = Array.from(menu.querySelectorAll("button"));
		expect(choices).toHaveLength(2);
		expect(choices.every((button) => button.disabled)).toBe(true);
		expect(menu.textContent).toContain(reason);
	} finally {
		if (transport && sessionId) await transport.invoke("abort", { sessionId }).catch(() => undefined);
		await transport?.close();
		for (const request of upstreamRequests) request.destroy();
		proxy.closeAllConnections();
		proxy.close();
		if (server.exitCode === null) {
			const exited = once(server, "exit");
			server.kill();
			await exited;
		}
		window.vera = previousApi;
		setHarnessConnected(false);
		useBehaviorPreferencesStore.setState(previousBehavior);
		useSubagentDraftsStore.setState({ drafts: [] });
		usePermissionPolicyStore.setState({ byTarget: {} });
		useSessionsStore.setState({ sessions: [] });
		useDraftStore.setState({ bySession: {}, failedBySession: {}, pendingBySession: {}, errorsBySession: {} });
		useTranscriptStore.setState({ bySession: {} });
		localStorage.clear();
		await rm(directory, { recursive: true, force: true });
	}
}, 60000);
