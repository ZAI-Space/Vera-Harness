/** Verify the API-only model form and stable configuration identity through Electron and Python. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launchDesktop } from "./ui-harness.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const python =
	process.env.VERA_PYTHON ??
	join(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const directory = await mkdtemp(join(tmpdir(), "vera-model-order-ui-"));
const connectionFile = join(directory, "connection.json");
const environment = {
	...process.env,
	PYTHONUTF8: "1",
	VERA_SILENT_STARTUP: "1",
	VERA_GLOBAL_CONFIG_DIR: join(directory, "global"),
	LITELLM_LOCAL_MODEL_COST_MAP: "True",
};
for (const name of Object.keys(environment)) {
	if (
		name.endsWith("_API_KEY") ||
		["VERA_DESKTOP_TOKEN", "VERA_DESKTOP_USER_DATA", "VERA_DESKTOP_BACKGROUND"].includes(name)
	)
		delete environment[name];
}
const children = [];
const checks = [];
const pageErrors = [];
let application;
let page;
let proxy;
let failNextLanRead = false;
let holdNextLanRead = false;
let heldLanRead = false;
let releaseLanRead = () => {};
const forwarding = new AbortController();
function start(args) {
	const child = spawn(python, args, {
		cwd: repository,
		env: environment,
		windowsHide: true,
		stdio: ["ignore", "pipe", "pipe"],
	});
	children.push(child);
	let log = "";
	child.stdout.on("data", (value) => {
		log += value.toString();
	});
	child.stderr.on("data", (value) => {
		log += value.toString();
	});
	child.on("exit", () => {
		void writeFile(join(directory, `process-${children.indexOf(child)}.log`), log);
	});
}
async function until(action, timeout = 30000) {
	const deadline = Date.now() + timeout;
	let failure;
	while (Date.now() < deadline) {
		try {
			return await action();
		} catch (error) {
			failure = error;
			await new Promise((resolve_) => setTimeout(resolve_, 100));
		}
	}
	throw failure;
}
async function invoke(method, args = {}) {
	const connection = JSON.parse(await readFile(connectionFile, "utf8"));
	const response = await fetch(`${connection.url}/invoke`, {
		method: "POST",
		headers: { Authorization: `Bearer ${connection.token}`, "Content-Type": "application/json" },
		body: JSON.stringify({ method, args }),
	});
	const payload = await response.json();
	if (!response.ok) throw new Error(payload.error);
	return payload.result;
}
async function check(name, action) {
	try {
		await action();
		checks.push({ name, status: "passed" });
		console.log(`PASS ${name}`);
	} catch (error) {
		checks.push({ name, status: "failed", error: String(error) });
		throw error;
	} finally {
		await writeFile(join(directory, "report.json"), JSON.stringify({ checks, pageErrors }, null, 2));
	}
}
async function settings(category) {
	const dialog = page
		.getByRole("dialog")
		.filter({ has: page.getByRole("heading", { name: "设置", exact: true }) });
	if (!(await dialog.count())) await page.getByRole("button", { name: "设置", exact: true }).click();
	await dialog.getByRole("button", { name: category, exact: true }).click();
	return dialog;
}
try {
	console.log(`EVIDENCE ${directory}`);
	start([
		"-m",
		"vera.desktop.server",
		"--port",
		"0",
		"--directory",
		join(directory, "backend"),
		"--connection-file",
		connectionFile,
	]);
	await until(() => access(connectionFile), 60000);
	// Exercise transport failure and reordered real responses without replacing IPC or service methods.
	const upstream = JSON.parse(await readFile(connectionFile, "utf8"));
	proxy = createServer(async (request, response) => {
		try {
			const chunks = [];
			for await (const chunk of request) chunks.push(chunk);
			const body = Buffer.concat(chunks);
			const method = body.length ? JSON.parse(body.toString()).method : undefined;
			if (method === "lanGetStatus" && failNextLanRead) {
				failNextLanRead = false;
				response.writeHead(503, { "Content-Type": "application/json" });
				response.end(JSON.stringify({ error: "Local acceptance: status read failed" }));
				return;
			}
			const reply = await fetch(upstream.url + request.url, {
				method: request.method,
				headers: { Authorization: `Bearer ${upstream.token}`, "Content-Type": "application/json" },
				...(body.length ? { body } : {}),
				signal: forwarding.signal,
			});
			const payload = await reply.text();
			if (method === "lanGetStatus" && holdNextLanRead) {
				holdNextLanRead = false;
				heldLanRead = true;
				await new Promise((resolve) => {
					releaseLanRead = resolve;
				});
			}
			response.writeHead(reply.status, { "Content-Type": "application/json" });
			response.end(payload);
		} catch (error) {
			if (!forwarding.signal.aborted) console.error(error);
			response.destroy();
		}
	});
	await new Promise((resolve, reject) => {
		proxy.once("error", reject);
		proxy.listen(0, "127.0.0.1", resolve);
	});
	await writeFile(
		connectionFile,
		JSON.stringify({ ...upstream, url: `http://127.0.0.1:${proxy.address().port}` }),
	);
	({ application, page } = await launchDesktop(connectionFile, join(directory, "frontend"), environment));
	page.on("pageerror", (error) => pageErrors.push(String(error)));
	const expand = page.getByRole("button", { name: "展开导航栏", exact: true });
	if (await expand.isVisible()) await expand.click();
	await check(
		"provider, API key and model ID order; no aliases; save and edit preserve stable identity",
		async () => {
			await settings("模型");
			await page.getByRole("button", { name: "添加服务商", exact: true }).click();
			await page.getByRole("button", { name: "DeepSeek", exact: true }).click();
			const providerBox = await page.getByText("服务商: DeepSeek", { exact: true }).boundingBox();
			const key = page.getByRole("textbox", { name: "API Key", exact: true });
			const model = page.getByRole("textbox", { name: "模型 ID", exact: true });
			const keyBox = await key.boundingBox(),
				modelBox = await model.boundingBox();
			assert.ok(providerBox.y < keyBox.y && keyBox.y < modelBox.y);
			assert.equal(await page.getByRole("textbox", { name: /连接名称|模型显示名称/ }).count(), 0);
			assert.equal(await page.getByRole("button", { name: "自动获取", exact: true }).isDisabled(), true);
			await key.fill("local-ui-only");
			await model.fill("deepseek-chat");
			assert.equal(await page.getByRole("button", { name: "自动获取", exact: true }).isEnabled(), true);
			await page.screenshot({ path: join(directory, "provider-key-model.png") });
			await page.getByRole("button", { name: "保存", exact: true }).click();
			await page.getByRole("region", { name: "DeepSeek", exact: true }).waitFor();
			const provider = (await invoke("listProviders")).find((value) => value.name === "DeepSeek");
			assert.equal(provider.customModels[0].id, "deepseek-chat");
			assert.equal(provider.customModels[0].name, undefined);
			await page.getByRole("button", { name: "管理 DeepSeek 的模型配置", exact: true }).click();
			assert.equal(await page.getByRole("textbox", { name: /连接名称|模型显示名称/ }).count(), 0);
			await page.getByRole("button", { name: "保存", exact: true }).click();
			assert.equal(
				(await invoke("listProviders")).find((value) => value.name === "DeepSeek").id,
				provider.id,
			);
		},
	);
	await check("API configuration has no authentication tabs or account login interface", async () => {
		assert.equal(await page.getByRole("tablist").count(), 0);
		assert.equal(await page.getByRole("tab").count(), 0);
		assert.equal(await page.getByRole("button", { name: /登录账号|重新登录|退出登录/ }).count(), 0);
		const providers = await invoke("listProviders");
		assert.ok(providers.every((provider) => !Object.hasOwn(provider, "oauth")));
		const missing = await page.evaluate(() =>
			["startProviderLogin", "cancelProviderLogin", "respondProviderLogin", "onProviderLoginEvent"].every(
				(key) => !(key in window.vera),
			),
		);
		assert.ok(missing);
		await page.screenshot({ path: join(directory, "api-only-model-settings.png") });
	});
	await check(
		"LAN disables unknown status, recovers on retry and ignores a stale read after toggling",
		async () => {
			failNextLanRead = true;
			await settings("跨设备互联");
			await page.getByText("局域网观察（可选）", { exact: true }).click();
			await page
				.getByRole("alert")
				.getByText("Local acceptance: status read failed", { exact: true })
				.waitFor();
			const toggle = page.getByRole("switch", { name: "跨设备互联", exact: true });
			assert.equal(await toggle.isEnabled(), false);
			assert.equal((await invoke("lanGetStatus")).enabled, false);
			await page.getByRole("alert").getByRole("button").click();
			await until(async () => assert.equal(await toggle.isEnabled(), true));
			await toggle.click();
			await until(async () => assert.equal(await toggle.getAttribute("aria-checked"), "true"));
			assert.equal((await invoke("lanGetStatus")).enabled, true);
			const remote = page.getByRole("switch", { name: "允许远程控制", exact: true });
			await remote.click();
			await until(async () => assert.equal((await invoke("lanGetStatus")).remoteControl, true));
			await page.screenshot({ path: join(directory, "lan-enabled.png") });
			await settings("模型");
			holdNextLanRead = true;
			await settings("跨设备互联");
			await page.getByText("局域网观察（可选）", { exact: true }).click();
			await until(() => assert.ok(heldLanRead));
			await toggle.click();
			await until(async () => assert.equal(await toggle.getAttribute("aria-checked"), "false"));
			releaseLanRead();
			await page.waitForTimeout(200);
			assert.equal(await toggle.getAttribute("aria-checked"), "false");
			const status = await invoke("lanGetStatus");
			assert.equal(status.enabled, false);
			assert.equal(status.remoteControl, false);
		},
	);
	assert.deepEqual(pageErrors, []);
} catch (error) {
	if (page && !page.isClosed()) {
		await page.screenshot({ path: join(directory, "failure.png") }).catch(() => {});
		await writeFile(join(directory, "failure-ui.txt"), await page.locator("body").innerText());
	}
	console.error(error);
	process.exitCode = 1;
} finally {
	releaseLanRead();
	forwarding.abort();
	proxy?.closeAllConnections();
	proxy?.close();
	await application?.evaluate(({ app }) => app.exit(0)).catch(() => {});
	const { execFileSync } = await import("node:child_process");
	for (const child of children) {
		if (child.exitCode === null && process.platform === "win32") {
			try {
				execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
					stdio: "ignore",
					windowsHide: true,
				});
			} catch {}
		} else child.kill();
	}
	console.log(`REPORT ${join(directory, "report.json")}`);
}
