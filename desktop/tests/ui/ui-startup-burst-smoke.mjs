/** A real loopback startup burst must not reject authenticated catalog reads. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const directory = await mkdtemp(join(tmpdir(), "vera-startup-ui-"));
const connectionFile = join(directory, "connection.json");
const environment = {
	...process.env,
	VERA_GLOBAL_CONFIG_DIR: join(directory, "global"),
	VERA_SILENT_STARTUP: "1",
	PYTHONUTF8: "1",
};
for (const key of Object.keys(environment)) {
	if (key.endsWith("_API_KEY") || key === "VERA_DESKTOP_TOKEN") delete environment[key];
}
const python =
	process.env.VERA_PYTHON ??
	join(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const server = spawn(
	python,
	[
		"-m",
		"vera.desktop.server",
		"--port",
		"0",
		"--directory",
		join(directory, "backend"),
		"--connection-file",
		connectionFile,
	],
	{
		cwd: repository,
		env: environment,
		windowsHide: true,
		stdio: ["ignore", "pipe", "pipe"],
	},
);
let logs = "";
server.stdout.on("data", (value) => {
	logs += value.toString();
});
server.stderr.on("data", (value) => {
	logs += value.toString();
});
let startupError;
server.once("error", (error) => {
	startupError = error;
});
try {
	let connection;
	const deadline = Date.now() + 30000;
	while (!connection) {
		if (startupError) throw startupError;
		if (server.exitCode !== null) throw new Error("Startup service exited.");
		if (Date.now() > deadline) throw new Error("Startup service timed out.");
		try {
			connection = JSON.parse(await readFile(connectionFile, "utf8"));
		} catch {
			await new Promise((resolve) => setTimeout(resolve, 50));
		}
	}
	const results = await Promise.all(
		Array.from({ length: 64 }, async () => {
			try {
				const response = await fetch(`${connection.url}/invoke`, {
					method: "POST",
					headers: { Authorization: `Bearer ${connection.token}`, "Content-Type": "application/json" },
					body: JSON.stringify({
						method: "querySessionCatalog",
						args: { query: { archived: false, limit: 6 } },
					}),
					signal: AbortSignal.timeout(10000),
				});
				const body = await response.json();
				assert.equal(response.status, 200);
				assert.deepEqual(body.result.sessions, []);
				assert.equal(body.result.complete, true);
				return "ok";
			} catch (error) {
				return error.cause?.code ?? String(error);
			}
		}),
	);
	assert.deepEqual(
		results.filter((result) => result !== "ok"),
		[],
	);
	console.log("PASS 64 concurrent authenticated catalog requests without connection rejection");
} catch (error) {
	console.error(error);
	process.exitCode = 1;
} finally {
	server.kill();
	await writeFile(join(directory, "diagnostics.log"), logs);
	console.log(`EVIDENCE ${directory}`);
}
