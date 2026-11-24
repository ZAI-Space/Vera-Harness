/** Current-source Electron/IPC/Python regression for marketplace overlays and JSON configuration. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launchDesktop } from "./ui-harness.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const python =
	process.env.VERA_PYTHON ??
	join(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const directory = await mkdtemp(join(tmpdir(), "vera-market-ui-"));
const connectionFile = join(directory, "connection.json");
const modelFile = join(directory, "model.json");
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
let modelProviderName;
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
	const source = join(directory, "publisher");
	await mkdir(join(source, ".agents/plugins"), { recursive: true });
	const entries = [];
	for (let number = 0; number < 12; number++) {
		const name = `review-${number}`;
		const root = join(source, "plugins", name);
		await mkdir(join(root, "assets"), { recursive: true });
		await mkdir(join(root, "skills/review"), { recursive: true });
		await writeFile(
			join(root, "plugin.json"),
			JSON.stringify({
				name,
				description: `Publisher description ${number}`,
				version: "1.0.0",
				interface: {
					displayName: `Review ${number}`,
					composerIcon: "./assets/icon.svg",
					longDescription: `Detailed publisher description ${number}`,
				},
			}),
		);
		await writeFile(
			join(root, "assets/icon.svg"),
			'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" rx="8" fill="#4564aa"/><path d="M10 20h20M20 10v20" stroke="white" stroke-width="3"/></svg>',
		);
		await writeFile(
			join(root, "skills/review/SKILL.md"),
			"---\nname: review\ndescription: Review files.\n---\nInspect files.\n",
		);
		entries.push({ name, source: `./plugins/${name}` });
	}
	await writeFile(
		join(source, ".agents/plugins/marketplace.json"),
		JSON.stringify({ name: "ui-market", plugins: entries }),
	);
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
	start(["-m", "tests.run.desktop_ui_fixture", "--connection-file", modelFile]);
	await until(() => access(connectionFile), 60000);
	await until(() => access(modelFile));
	modelProviderName = new URL(JSON.parse(await readFile(modelFile, "utf8")).url).host;
	await invoke("addPluginRepository", { source });
	({ application, page } = await launchDesktop(connectionFile, join(directory, "frontend"), environment));
	page.on("pageerror", (error) => pageErrors.push(String(error)));
	const expand = page.getByRole("button", { name: "展开导航栏", exact: true });
	if (await expand.isVisible()) await expand.click();
	await check(
		"publisher icons and descriptions render; details float above the retained grid after scrolling",
		async () => {
			await page.getByRole("button", { name: "插件", exact: true }).click();
			await page.getByRole("tab", { name: "插件市场", exact: true }).click();
			await page.getByRole("combobox", { name: "筛选来源", exact: true }).click();
			await page.getByRole("option", { name: "ui-market", exact: true }).click();
			await page.getByText("Publisher description 11", { exact: true }).waitFor();
			assert.equal(await page.locator("article").count(), 12);
			assert.equal(await page.locator("article img").count(), 12);
			assert.equal(
				await page
					.locator("article img")
					.first()
					.evaluate((image) => image.complete && image.naturalWidth > 0),
				true,
			);
			await page.locator("article").last().getByRole("button", { name: "查看详情", exact: true }).click();
			const detail = page.getByRole("dialog", { name: "查看详情", exact: true });
			await detail.getByText("Detailed publisher description 11", { exact: true }).waitFor();
			assert.equal(await page.locator("article").count(), 12);
			assert.equal(await detail.getByRole("button", { name: "关闭", exact: true }).count(), 1);
			assert.equal(
				await detail.evaluate(
					(element) =>
						element.parentElement.parentElement === document.body &&
						getComputedStyle(element.parentElement).position === "fixed",
				),
				true,
			);
			const box = await detail.boundingBox();
			assert.ok(box.y >= 0 && box.y + box.height <= (await page.evaluate(() => innerHeight)));
			await page.screenshot({ path: join(directory, "plugin-detail.png") });
			await detail.getByRole("button", { name: "安装插件", exact: true }).click();
			const confirm = page.getByRole("dialog", { name: "安装插件", exact: true });
			await confirm.getByRole("button", { name: "安装插件", exact: true }).click();
			await confirm.waitFor({ state: "detached" });
			const installed = await invoke("getPlugins");
			assert.equal(installed[0].description, "Publisher description 11");
			assert.ok(installed[0].icon.startsWith("data:image/svg+xml;base64,"));
			await page.keyboard.press("Escape");
			assert.equal(await page.getByRole("dialog").count(), 0);
		},
	);
	await check("MCP JSON validates, saves, probes real stdio and edits without disabling", async () => {
		await settings("MCP");
		assert.equal(await page.getByRole("button", { name: "添加服务器", exact: true }).count(), 0);
		await page.getByRole("button", { name: "添加 JSON", exact: true }).click();
		const json = page.getByRole("textbox", { name: "MCP JSON", exact: true });
		await json.fill("{ invalid");
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await page.getByRole("alert").waitFor();
		const config = { command: python, args: ["-u", join(repository, "tests/run/mcp_fixture.py")] };
		await json.fill(JSON.stringify({ mcpServers: { "ui-mcp": config } }));
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await json.waitFor({ state: "detached" });
		assert.equal((await invoke("mcpConfigList")).global[0].enabled, false);
		await page.getByRole("button", { name: "测试连接", exact: true }).click();
		await page
			.getByText("连接测试通过：2 个工具。任务开始时会重新连接。", { exact: true })
			.waitFor({ timeout: 30000 });
		await page.getByRole("button", { name: "启用", exact: true }).click();
		await until(async () => assert.equal((await invoke("mcpConfigList")).global[0].enabled, true));
		await page.getByRole("button", { name: "编辑", exact: true }).click();
		assert.deepEqual(JSON.parse(await json.inputValue()).mcpServers["ui-mcp"].args, config.args);
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await json.waitFor({ state: "detached" });
		assert.equal((await invoke("mcpConfigList")).global[0].enabled, true);
		await page.screenshot({ path: join(directory, "mcp-list.png") });
	});
	await check(
		"Docker curated marketplace opens, shows publisher metadata and registers a pinned service",
		async () => {
			await page.getByRole("button", { name: "从市场添加", exact: true }).click();
			const market = page.getByRole("dialog", { name: "MCP 市场", exact: true });
			await market.getByRole("textbox", { name: "MCP search", exact: true }).fill("playwright");
			await until(async () => {
				assert.equal(await market.getByRole("button", { name: "搜索", exact: true }).isEnabled(), true);
			});
			await market.getByRole("button", { name: "搜索", exact: true }).click();
			await market.locator("li").first().waitFor({ timeout: 60000 });
			await market.locator("li").first().getByRole("button").first().click();
			await market.getByRole("button", { name: "返回市场", exact: true }).waitFor();
			await until(
				async () =>
					assert.ok((await market.locator("pre").count()) || (await market.getByRole("alert").count())),
				60000,
			);
			assert.equal(await market.locator("pre").count(), 1, await market.innerText());
			await page.screenshot({ path: join(directory, "mcp-market.png") });
			const plan = JSON.parse(await market.locator("pre").innerText());
			const name = Object.keys(plan.mcpServers)[0];
			await market.getByRole("button", { name: "添加服务", exact: true }).click();
			await market.waitFor({ state: "detached" });
			assert.equal((await invoke("mcpConfigList")).global.find((row) => row.name === name).enabled, false);
		},
	);
	await check("model presets open above settings; actual discovery populates selectable models", async () => {
		await settings("模型");
		await page.getByRole("button", { name: "添加服务商", exact: true }).click();
		await page.getByRole("button", { name: /自定义服务商/ }).click();
		await page
			.getByRole("textbox", { name: "baseUrl，如 https://api.example.com/v1", exact: true })
			.fill(JSON.parse(await readFile(modelFile, "utf8")).url);
		await page.getByRole("textbox", { name: "API Key", exact: true }).fill("local-ui-fixture");
		await page.getByRole("button", { name: "自动获取", exact: true }).click();
		await page.getByRole("checkbox", { name: "gpt-4o-mini", exact: true }).check();
		await page.getByRole("button", { name: "添加所选 · 1", exact: true }).click();
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await page.getByRole("region", { name: modelProviderName, exact: true }).waitFor();
		assert.equal((await invoke("listModels")).length, 1);
	});
	await check(
		"LAN settings pair a separate mobile window, gate remote commands and revoke access",
		async () => {
			const session = await invoke("createSession", { options: { cwd: directory } });
			await invoke("setSessionSelections", { sessionId: session.sessionId, permissionPolicy: "human" });
			await settings("跨设备互联");
			await page.getByText("局域网观察（可选）", { exact: true }).click();
			const toggle = page.getByRole("switch", { name: "跨设备互联", exact: true });
			await until(async () => assert.equal(await toggle.isEnabled(), true));
			await toggle.click();
			await until(async () => assert.equal((await invoke("lanGetStatus")).enabled, true));
			const status = await invoke("lanGetStatus");
			const url = new URL(status.urls[0]);
			url.hostname = "127.0.0.1";
			const mobileWindow = application.waitForEvent("window");
			await application.evaluate(({ BrowserWindow }, address) => {
				const window = new BrowserWindow({
					show: false,
					width: 390,
					height: 844,
					webPreferences: {
						sandbox: true,
						contextIsolation: true,
						nodeIntegration: false,
						backgroundThrottling: false,
						offscreen: true,
					},
				});
				void window.loadURL(address);
			}, url.href);
			const mobile = await mobileWindow;
			mobile.on("pageerror", (error) => pageErrors.push(String(error)));
			await mobile.getByText("已连接 · 只读", { exact: true }).waitFor();
			assert.equal(await mobile.locator("#composer").isVisible(), false);
			await page.getByRole("switch", { name: "允许远程控制", exact: true }).click();
			await mobile.getByText("已连接 · 可远程控制", { exact: true }).waitFor();
			await mobile
				.getByRole("textbox", { name: "发送消息", exact: true })
				.fill("printf phone-ok > phone.txt");
			await mobile.getByRole("button", { name: "发送", exact: true }).click();
			await until(async () => assert.equal(await readFile(join(directory, "phone.txt"), "utf8"), "phone-ok"));
			await mobile.screenshot({ path: join(directory, "lan-mobile.png") });
			await page.screenshot({ path: join(directory, "lan-settings.png") });
			await page.getByRole("switch", { name: "允许远程控制", exact: true }).click();
			await mobile.getByText("已连接 · 只读", { exact: true }).waitFor();
			await toggle.click();
			await until(async () => assert.equal((await invoke("lanGetStatus")).enabled, false));
			await mobile.close();
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
	await application?.evaluate(({ app }) => app.exit(0)).catch(() => {});
	for (const child of children) child.kill();
	console.log(`REPORT ${join(directory, "report.json")}`);
}
