#!/usr/bin/env node
/** Start the authenticated loopback service before Electron, then stop owned children on exit. */
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { findPython, prepareRuntime, run, verifyWheel } from "./runtime.mjs";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
const args = process.argv.slice(2);
if (args.includes("--help") || args.includes("-h")) {
	console.log(
		`VERA Harness ${manifest.version}\n\nUsage: npx vera-harness [--help | --version | --doctor | --setup-only]\n\nRequires Node.js 22–25 and Python 3.10–3.13. First launch installs a private\nPython runtime. VERA_PYTHON selects Python; VERA_RUNTIME_DIR selects its cache.\nClose the app or press Ctrl+C to stop the local service.`,
	);
} else if (args.includes("--version")) {
	console.log(manifest.version);
} else {
	let backend, desktop, directory;
	const controller = new AbortController();
	async function stop(child) {
		if (!child || child.exitCode !== null || child.signalCode) return;
		if (process.platform === "win32") {
			await run("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
				stdio: "ignore",
			}).catch(() => {});
		} else {
			child.kill("SIGTERM");
			await Promise.race([
				new Promise((resolve) => child.once("exit", resolve)),
				new Promise((resolve) => setTimeout(resolve, 3000)),
			]);
			if (child.exitCode === null && !child.signalCode) child.kill("SIGKILL");
		}
	}
	const interrupted = () => {
		controller.abort();
		void stop(desktop).then(() => stop(backend));
	};
	process.on("SIGINT", interrupted);
	process.on("SIGTERM", interrupted);
	try {
		if (args.some((arg) => !["--doctor", "--setup-only"].includes(arg)))
			throw new Error("Unknown option. Run vera-harness --help.");
		const major = Number(process.versions.node.split(".")[0]);
		if (major < 22 || major >= 26) throw new Error("Use Node.js 24 LTS (supported: 22–25).");
		const runtime = JSON.parse(await readFile(join(packageRoot, "runtime.json"), "utf8"));
		if (args.includes("--doctor")) {
			const interpreter = findPython();
			await verifyWheel(packageRoot, runtime);
			console.log(
				`VERA ${manifest.version}: bundled runtime verified; Python available via ${interpreter.command}.`,
			);
		} else {
			const python = await prepareRuntime(packageRoot, manifest, runtime, {
				signal: controller.signal,
			});
			controller.signal.throwIfAborted();
			if (!args.includes("--setup-only")) {
				directory = await mkdtemp(join(tmpdir(), "vera-desktop-"));
				const connectionFile = join(directory, "connection.json");
				const environment = {
					...process.env,
					VERA_SILENT_STARTUP: "1",
					PYTHONUTF8: "1",
					VERA_RELEASE_CHANNEL: "alpha",
				};
				delete environment.ELECTRON_RUN_AS_NODE;
				delete environment.ELECTRON_RENDERER_URL;
				backend = spawn(
					python,
					["-I", "-m", "vera.desktop.server", "--port", "0", "--connection-file", connectionFile],
					{
						env: environment,
						windowsHide: true,
						stdio: ["ignore", "inherit", "inherit"],
					},
				);
				let backendError;
				backend.once("error", (error) => {
					backendError = error;
				});
				const deadline = Date.now() + 60000;
				let connected = false;
				while (!connected) {
					controller.signal.throwIfAborted();
					if (backendError) throw backendError;
					if (backend.exitCode !== null) throw new Error("The VERA service exited before startup completed.");
					if (Date.now() > deadline)
						throw new Error("The VERA service did not become ready within 60 seconds.");
					try {
						const connection = JSON.parse(await readFile(connectionFile, "utf8"));
						const response = await fetch(`${connection.url}/health`, {
							headers: { Authorization: `Bearer ${connection.token}` },
							signal: AbortSignal.timeout(2000),
						});
						connected = response.ok;
						await response.arrayBuffer();
					} catch {
						/* The connection record can precede the first accepted request. */
					}
					if (!connected) await new Promise((resolve) => setTimeout(resolve, 100));
				}
				controller.signal.throwIfAborted();
				const electron = createRequire(import.meta.url)("electron");
				desktop = spawn(electron, [packageRoot], {
					env: { ...environment, VERA_DESKTOP_CONNECTION_FILE: connectionFile },
					windowsHide: true,
					stdio: "inherit",
				});
				backend.once("exit", () => {
					void stop(desktop);
				});
				const code = await new Promise((resolve, reject) => {
					desktop.once("error", reject);
					desktop.once("exit", (code) => resolve(code ?? 1));
				});
				process.exitCode = code;
			}
		}
	} catch (error) {
		console.error(`VERA: ${error.message}`);
		process.exitCode = 1;
	} finally {
		await stop(desktop);
		await stop(backend);
		if (directory) await rm(directory, { recursive: true, force: true });
		process.off("SIGINT", interrupted);
		process.off("SIGTERM", interrupted);
	}
}
