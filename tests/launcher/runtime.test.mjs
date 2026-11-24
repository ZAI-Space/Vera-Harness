/** Regression tests for the published desktop launcher's setup and isolation boundary. */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
	prepareRuntime,
	pythonCandidates,
	run,
	runtimeDirectory,
	verifyWheel,
} from "../../packages/desktop-launcher/bin/runtime.mjs";

async function withFixture(action) {
	const directory = await mkdtemp(join(tmpdir(), "vera-launcher-test-"));
	try {
		await action(directory);
	} finally {
		await rm(directory, { recursive: true, force: true });
	}
}

test("explicit Python paths remain one command rather than split arguments", () => {
	assert.deepEqual(pythonCandidates({ VERA_PYTHON: "C:/Python path/python.exe" }, "win32"), [
		["C:/Python path/python.exe", []],
	]);
	assert.deepEqual(pythonCandidates({}, "win32")[0], ["py", ["-3.12"]]);
});

test("runtime cache separates package versions and exact bundled content", () => {
	const env = { VERA_RUNTIME_DIR: "/private/cache" };
	const first = runtimeDirectory("0.1.0-alpha.1", "a".repeat(64), env);
	assert.notEqual(first, runtimeDirectory("0.1.0-alpha.2", "a".repeat(64), env));
	assert.notEqual(first, runtimeDirectory("0.1.0-alpha.1", "b".repeat(64), env));
});

test("wheel validation rejects modified bytes and path traversal", async () =>
	withFixture(async (directory) => {
		await mkdir(join(directory, "python"));
		const wheel = "vera_harness-0.1.0a1-py3-none-any.whl";
		await writeFile(join(directory, "python", wheel), "bundled-wheel");
		const runtime = {
			wheel,
			sha256: createHash("sha256").update("bundled-wheel").digest("hex"),
		};
		assert.equal(await verifyWheel(directory, runtime), join(directory, "python", wheel));
		await writeFile(join(directory, "python", wheel), "tampered");
		await assert.rejects(verifyWheel(directory, runtime), /checksum mismatch/);
		await assert.rejects(verifyWheel(directory, { ...runtime, wheel: "../../secret" }), /Invalid bundled/);
	}));

test("subprocess failures and cancellation propagate without a shell", async () => {
	await assert.rejects(run(process.execPath, ["-e", "process.exit(7)"], { stdio: "ignore" }), /failed \(7\)/);
	const controller = new AbortController();
	const child = run(process.execPath, ["-e", "setTimeout(() => {}, 60000)"], {
		signal: controller.signal,
		stdio: "ignore",
	});
	controller.abort();
	await assert.rejects(child, /aborted/);
});

test("cancelled setup stops before touching runtime cache", async () =>
	withFixture(async (directory) => {
		const controller = new AbortController();
		controller.abort();
		await assert.rejects(
			prepareRuntime(directory, { version: "test" }, {}, { signal: controller.signal }),
			/aborted/,
		);
	}));

test("help and version work without an available Python runtime", async () => {
	const launcher = new URL("../../packages/desktop-launcher/bin/vera-harness.mjs", import.meta.url);
	const { fileURLToPath } = await import("node:url");
	const env = { ...process.env, VERA_PYTHON: "/does-not-exist" };
	assert.match(
		execFileSync(process.execPath, [fileURLToPath(launcher), "--help"], {
			env,
			encoding: "utf8",
		}),
		/private/,
	);
	const manifest = JSON.parse(
		await readFile(new URL("../../packages/desktop-launcher/package.json", import.meta.url), "utf8"),
	);
	assert.equal(
		execFileSync(process.execPath, [fileURLToPath(launcher), "--version"], {
			env,
			encoding: "utf8",
		}).trim(),
		manifest.version,
	);
});
