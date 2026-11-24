import { readFile } from "node:fs/promises";
import { CHANNEL_TABLE, SUBSCRIPTION_TABLE } from "@vera/contracts";
import type { BackendTransport } from "./backend";

function record(value: unknown): value is Record<string, unknown> {
	return !!value && typeof value === "object" && !Array.isArray(value);
}

async function connection(path: string): Promise<{ url: string; token: string }> {
	const value: unknown = JSON.parse(await readFile(path, "utf8"));
	if (!record(value) || typeof value.url !== "string" || typeof value.token !== "string")
		throw new Error("Invalid VERA connection file");
	const url = new URL(value.url);
	if (
		url.protocol !== "http:" ||
		url.hostname !== "127.0.0.1" ||
		value.token.length < 32 ||
		url.username ||
		url.password
	)
		throw new Error("VERA desktop requires an authenticated loopback service");
	return { url: value.url, token: value.token };
}

/** 本机服务适配：凭据只存在主进程，请求不重放；断线后仅重试只读事件轮询。 */
export class HttpTransport implements BackendTransport {
	private readonly listeners = new Set<(method: string, payload: unknown) => void>();
	private stopped = false;
	private cursor = 0;
	private connected = true;
	private readonly abort = new AbortController();
	private constructor(
		private url: string,
		private token: string,
		private readonly connectionFile: string,
	) {}

	static async fromFile(path: string): Promise<HttpTransport> {
		const value = await connection(path);
		const transport = new HttpTransport(value.url, value.token, path);
		const health = await transport.request("/health");
		if (!record(health) || health.protocolVersion !== 1 || typeof health.cursor !== "number")
			throw new Error("Unsupported VERA backend protocol");
		transport.cursor = health.cursor;
		void transport.poll();
		return transport;
	}

	private async request(path: string, body?: unknown): Promise<unknown> {
		const response = await fetch(this.url + path, {
			method: body === undefined ? "GET" : "POST",
			headers: { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" },
			...(body === undefined ? {} : { body: JSON.stringify(body) }),
			signal: AbortSignal.any([this.abort.signal, AbortSignal.timeout(body === undefined ? 25000 : 120000)]),
		}).catch((error: unknown) => {
			if (this.abort.signal.aborted) throw error;
			if (error instanceof Error && error.name === "TimeoutError")
				throw new Error("本机服务响应超时，请稍后重试。", { cause: error });
			throw new Error("本机服务连接中断，请等待重新连接后重试。", { cause: error });
		});
		const value: unknown = await response.json();
		if (!response.ok)
			throw new Error(record(value) && typeof value.error === "string" ? value.error : "VERA request failed");
		return value;
	}

	async invoke(method: string, args: unknown): Promise<unknown> {
		if (!Object.hasOwn(CHANNEL_TABLE, method)) throw new Error("Unknown VERA desktop method");
		if (method === "harnessInvoke") {
			if (!record(args) || typeof args.method !== "string") throw new Error("Invalid Harness request");
			method = args.method;
			args = args.args;
		}
		const envelope = await this.request("/invoke", { method, args });
		if (!record(envelope) || !Object.hasOwn(envelope, "result"))
			throw new Error("Invalid VERA response envelope");
		return envelope.result;
	}

	subscribe(listener: (method: string, payload: unknown) => void): () => void {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	}

	private async poll(): Promise<void> {
		while (!this.stopped) {
			try {
				const envelope = await this.request(`/events?after=${this.cursor}`);
				if (!record(envelope) || typeof envelope.cursor !== "number" || !Array.isArray(envelope.events))
					throw new Error("Invalid VERA event envelope");
				if (envelope.reset || !this.connected) {
					for (const listener of this.listeners) listener("onBackendStatusChanged", { connected: false });
					for (const listener of this.listeners) listener("onBackendStatusChanged", { connected: true });
					this.connected = true;
				}
				for (const event of envelope.events) {
					if (
						!record(event) ||
						typeof event.method !== "string" ||
						!Object.hasOwn(SUBSCRIPTION_TABLE, event.method)
					)
						throw new Error("Unknown VERA event");
					for (const listener of this.listeners) listener(event.method, event.payload);
				}
				this.cursor = envelope.cursor;
			} catch {
				if (this.stopped) return;
				this.connected = false;
				for (const listener of this.listeners) listener("onBackendStatusChanged", { connected: false });
				try {
					const next = await connection(this.connectionFile);
					if (next.url !== this.url || next.token !== this.token) {
						this.url = next.url;
						this.token = next.token;
						this.cursor = 0;
					}
				} catch {
					// A restarting owner may temporarily remove discovery. Never retry a write.
				}
				await new Promise((resolve) => setTimeout(resolve, 1000));
			}
		}
	}

	async close(): Promise<void> {
		this.stopped = true;
		this.abort.abort();
		this.listeners.clear();
	}
}
