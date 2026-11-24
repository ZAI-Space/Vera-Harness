/** Prepare a versioned private Python environment; never install into system Python. */
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { access, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

export function pythonCandidates(environment = process.env, platform = process.platform) {
	if (environment.VERA_PYTHON) return [[environment.VERA_PYTHON, []]];
	return platform === "win32"
		? [
				["py", ["-3.12"]],
				["py", ["-3.11"]],
				["py", ["-3.10"]],
				["python", []],
				["python3", []],
			]
		: [
				["python3.12", []],
				["python3.11", []],
				["python3.10", []],
				["python3", []],
				["python", []],
			];
}

export function findPython(environment = process.env) {
	for (const [command, prefix] of pythonCandidates(environment)) {
		try {
			execFileSync(
				command,
				[...prefix, "-I", "-c", "import sys; assert (3,10) <= sys.version_info[:2] < (3,14)"],
				{
					env: environment,
					stdio: "ignore",
					windowsHide: true,
					timeout: 15000,
				},
			);
			return { command, prefix };
		} catch {
			/* Try the next installed interpreter without invoking a shell. */
		}
	}
	throw new Error("Install Python 3.10–3.13 (3.12 recommended), or set VERA_PYTHON to its executable path.");
}

export function runtimeDirectory(version, wheelHash, environment = process.env) {
	const base =
		environment.VERA_RUNTIME_DIR ||
		(process.platform === "win32"
			? join(environment.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "VERA", "runtimes")
			: join(environment.XDG_CACHE_HOME || join(homedir(), ".cache"), "vera-harness", "runtimes"));
	return join(base, `${version}-${wheelHash.slice(0, 16)}`);
}

export function run(command, args, options = {}) {
	return new Promise((resolve, reject) => {
		const { signal, ...spawnOptions } = options;
		signal?.throwIfAborted();
		const child = spawn(command, args, {
			stdio: "inherit",
			windowsHide: true,
			...spawnOptions,
		});
		const abort = () => {
			if (process.platform === "win32" && child.pid) {
				try {
					execFileSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
						stdio: "ignore",
						windowsHide: true,
					});
				} catch {
					/* The child can exit before taskkill observes it. */
				}
			} else child.kill("SIGTERM");
		};
		signal?.addEventListener("abort", abort, { once: true });
		child.once("error", (error) => {
			signal?.removeEventListener("abort", abort);
			reject(error);
		});
		child.once("exit", (code, exitSignal) => {
			signal?.removeEventListener("abort", abort);
			if (signal?.aborted) reject(new Error("Operation aborted."));
			else if (code === 0) resolve();
			else reject(new Error(`${command} failed (${exitSignal || code}).`));
		});
	});
}

export async function verifyWheel(packageRoot, runtime) {
	if (!/^vera_harness-[a-zA-Z0-9_.-]+\.whl$/.test(runtime.wheel))
		throw new Error("Invalid bundled runtime filename.");
	const wheel = join(packageRoot, "python", runtime.wheel);
	const hash = createHash("sha256")
		.update(await readFile(wheel))
		.digest("hex");
	if (hash !== runtime.sha256)
		throw new Error("Bundled Python runtime checksum mismatch. Reinstall this npm package.");
	return wheel;
}

/** Serialize first-time setup; a failed install never receives a ready marker. */
export async function prepareRuntime(packageRoot, manifest, runtime, { signal } = {}) {
	signal?.throwIfAborted();
	const wheel = await verifyWheel(packageRoot, runtime);
	const directory = runtimeDirectory(manifest.version, runtime.sha256);
	const python = join(directory, process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
	const marker = join(directory, ".vera-ready");
	async function ready() {
		try {
			await access(python);
			return (await readFile(marker, "utf8")) === runtime.sha256;
		} catch {
			return false;
		}
	}
	if (await ready()) return python;
	const interpreter = findPython();
	await mkdir(directory, { recursive: true });
	const lock = join(directory, ".setup-lock");
	const deadline = Date.now() + 600000;
	let owned = false;
	while (!owned) {
		signal?.throwIfAborted();
		try {
			await mkdir(lock);
			owned = true;
		} catch (error) {
			if (error.code !== "EEXIST") throw error;
			if (await ready()) return python;
			if (Date.now() >= deadline)
				throw new Error(`Another setup is running or was interrupted. Check ${lock} before retrying.`);
			await new Promise((resolve) => setTimeout(resolve, 500));
		}
	}
	try {
		if (await ready()) return python;
		console.log("VERA: preparing a private Python runtime (first launch requires Internet access)…");
		await run(interpreter.command, [...interpreter.prefix, "-I", "-m", "venv", directory], { signal });
		await run(
			python,
			["-I", "-m", "pip", "install", "--disable-pip-version-check", `${wheel}[mcp,channels]`],
			{ signal },
		);
		await run(python, ["-I", "-c", "from vera.desktop.server import DesktopServer"], {
			signal,
		});
		signal?.throwIfAborted();
		await writeFile(marker, runtime.sha256, { mode: 0o600 });
		return python;
	} finally {
		await rm(lock, { recursive: true, force: true });
	}
}
