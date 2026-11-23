import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { HttpTransport } from "../../../src/main/services/http-transport";

/** Real loopback peers exercise credential rotation and ambiguous mutation failure. */
it("reconnects from private discovery and never replays a failed mutation", async () => {
	const directory = await mkdtemp(join(tmpdir(), "vera-http-"));
	const path = join(directory, "connection.json");
	let writes = 0;
	const peers: ReturnType<typeof createServer>[] = [];
	const peer = async (token: string) => {
		const server = createServer((request, response) => {
			if (request.headers.authorization !== `Bearer ${token}`) {
				response.writeHead(401).end(JSON.stringify({ error: "Unauthorized" }));
				return;
			}
			if (request.url === "/invoke") {
				writes++;
				request.socket.destroy();
				return;
			}
			if (request.url === "/health") {
				response.end(JSON.stringify({ protocolVersion: 1, cursor: 0 }));
				return;
			}
			setTimeout(() => response.end(JSON.stringify({ cursor: 0, events: [] })), 80);
		});
		await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
		peers.push(server);
		const address = server.address();
		if (!address || typeof address === "string") throw Error("Expected loopback listener");
		return { url: `http://127.0.0.1:${address.port}`, token };
	};
	let transport: HttpTransport | undefined;
	try {
		const first = await peer("a".repeat(48));
		await writeFile(path, JSON.stringify(first));
		transport = await HttpTransport.fromFile(path);
		await expect(transport.invoke("prompt", { sessionId: "actual", text: "one request" })).rejects.toThrow();
		expect(writes).toBe(1);
		const states: boolean[] = [];
		transport.subscribe((method, payload) => {
			if (method === "onBackendStatusChanged") states.push((payload as { connected: boolean }).connected);
		});
		const second = await peer("b".repeat(48));
		await writeFile(path, JSON.stringify(second));
		peers[0]?.closeAllConnections();
		peers[0]?.close();
		const deadline = Date.now() + 6000;
		while ((!states.includes(false) || !states.includes(true)) && Date.now() < deadline)
			await new Promise((resolve) => setTimeout(resolve, 30));
		expect(states).toContain(false);
		expect(states.at(-1)).toBe(true);
		expect(writes).toBe(1);
		await writeFile(path, JSON.stringify({ url: "https://example.com", token: first.token }));
		await expect(HttpTransport.fromFile(path)).rejects.toThrow("loopback");
	} finally {
		await transport?.close();
		for (const server of peers) {
			server.closeAllConnections();
			server.close();
		}
		await rm(directory, { recursive: true, force: true });
	}
}, 12000);
