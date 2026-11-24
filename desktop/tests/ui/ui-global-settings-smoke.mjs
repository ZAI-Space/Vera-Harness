/** Current-source Electron/IPC/Python regression for marketplace overlays and JSON configuration. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launchDesktop } from "./ui-harness.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const python =
	process.env.VERA_PYTHON ??
	join(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const directory = await mkdtemp(join(tmpdir(), "vera-global-settings-ui-"));
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
	environment.VERA_TASKBOARD_HOME = process.env.VERA_TASKBOARD_HOME;
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
	({ application, page } = await launchDesktop(connectionFile, join(directory, "frontend"), environment));
	page.on("pageerror", (error) => pageErrors.push(String(error)));
	const expand = page.getByRole("button", { name: "展开导航栏", exact: true });
	if (await expand.isVisible()) await expand.click();
	await check("settings order and global rule CRUD persist through backend and remount", async () => {
		const dialog = await settings("规则与记忆");
		const categories = await dialog.locator("nav button").allTextContents();
		assert.equal(categories[1].trim(), "行为");
		assert.equal(categories[2].trim(), "规则与记忆");
		assert.equal(categories.at(-2).trim(), "统计数据");
		assert.equal(categories.at(-1).trim(), "关于");
		assert.ok(!categories.some((value) => value.trim() === "扩展"));
		await dialog.getByRole("button", { name: "创建规则", exact: true }).click();
		const editor = page.getByRole("dialog", { name: "创建规则", exact: true });
		await editor.getByRole("textbox", { name: "标题", exact: true }).fill("全局验收规则");
		await editor.getByRole("textbox", { name: "内容", exact: true }).fill("请始终使用中文沟通 {{ literal }}");
		await editor.getByRole("button", { name: "保存", exact: true }).click();
		await dialog.getByRole("heading", { name: "全局验收规则", exact: true }).waitFor();
		assert.equal((await invoke("getUserContext")).entries[0].content, "请始终使用中文沟通 {{ literal }}");
		await dialog.getByRole("switch", { name: "启用 全局验收规则", exact: true }).click();
		await until(async () => assert.equal((await invoke("getUserContext")).entries[0].enabled, false));
		await settings("行为");
		await settings("规则与记忆");
		assert.equal(
			await page.getByRole("switch", { name: "启用 全局验收规则", exact: true }).getAttribute("aria-checked"),
			"false",
		);
		await page.screenshot({ path: join(directory, "rules.png") });
	});
	await check("preset and custom layouts, key guard, field order, persisted advanced settings", async () => {
		await settings("模型");
		await page.getByRole("button", { name: "添加服务商", exact: true }).click();
		await page.getByRole("button", { name: "DeepSeek", exact: true }).click();
		assert.equal(
			await page
				.getByRole("textbox", { name: "baseUrl，如 https://api.example.com/v1", exact: true })
				.count(),
			0,
		);
		assert.equal(await page.getByRole("button", { name: "自动获取", exact: true }).isDisabled(), true);
		await page.getByRole("button", { name: "高级配置", exact: true }).click();
		assert.equal(await page.getByRole("textbox", { name: "参数名", exact: true }).count(), 0);
		await page.screenshot({ path: join(directory, "preset.png") });
		await page.getByRole("button", { name: "取消", exact: true }).click();
		await page.getByRole("button", { name: "添加服务商", exact: true }).click();
		await page.getByRole("button", { name: "自定义服务商", exact: true }).click();
		await page
			.getByRole("textbox", { name: "baseUrl，如 https://api.example.com/v1", exact: true })
			.fill(JSON.parse(await readFile(modelFile, "utf8")).url);
		assert.equal(await page.getByRole("button", { name: "自动获取", exact: true }).isEnabled(), true);
		const fetchBox = await page.getByRole("button", { name: "自动获取", exact: true }).boundingBox();
		const modelBox = await page.getByRole("textbox", { name: "模型 ID", exact: true }).boundingBox();
		assert.ok(fetchBox.y < modelBox.y);
		await page.getByRole("button", { name: "自动获取", exact: true }).click();
		await page.getByRole("checkbox", { name: "gpt-4o-mini", exact: true }).check();
		await page.getByRole("button", { name: "添加所选 · 1", exact: true }).click();
		const keyBox = await page.getByRole("textbox", { name: "API Key", exact: true }).boundingBox();
		assert.ok(keyBox.y < modelBox.y);
		assert.equal(await page.getByRole("textbox", { name: /连接名称|模型显示名称/ }).count(), 0);
		await page.getByRole("button", { name: "高级配置", exact: true }).click();
		await page.getByRole("switch", { name: "思考模式", exact: true }).click();
		await page.getByRole("textbox", { name: "可选值列表", exact: true }).fill("enabled");
		await page.getByRole("textbox", { name: "可选值列表", exact: true }).press("Enter");
		await page.getByRole("spinbutton", { name: "Temperature", exact: true }).fill("0");
		await page.getByRole("spinbutton", { name: "工具调用轮数", exact: true }).fill("42");
		await page.screenshot({ path: join(directory, "custom.png") });
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await page.getByRole("region", { name: modelProviderName, exact: true }).waitFor();
		const providers = await invoke("listProviders");
		const provider = providers.find((value) => value.name === modelProviderName);
		assert.equal(provider.customModels[0].advanced.temperature, 0);
		assert.equal(provider.customModels[0].advanced.toolCallLimit, 42);
		assert.equal(provider.customModels[0].name, undefined);
		await page.getByRole("dialog", { name: "添加服务商", exact: true }).waitFor({ state: "detached" });
		await page
			.getByRole("dialog")
			.filter({ has: page.getByRole("heading", { name: "设置", exact: true }) })
			.getByRole("button", { name: "关闭", exact: true })
			.click();
		await page
			.getByRole("button", { name: /^(选择模型|gpt-4o-mini)/ })
			.first()
			.click();
		await page.getByRole("button", { name: "gpt-4o-mini", exact: true }).click();
		const slider = page.getByRole("slider", { name: "思考深度", exact: true });
		await slider.focus();
		await slider.press("End");
		await until(async () => assert.equal(await slider.getAttribute("aria-valuetext"), "enabled"));
		await slider.press("ArrowLeft");
		await until(async () => assert.equal(await slider.getAttribute("aria-valuetext"), "高"));
		await page.keyboard.press("Escape");
		const meta = await invoke("createSession", {
			options: { cwd: directory, provider: provider.id, modelId: "gpt-4o-mini" },
		});
		await invoke("setSessionSelections", {
			sessionId: meta.sessionId,
			permissionPolicy: "yolo",
			selections: {},
		});
		await invoke("prompt", { sessionId: meta.sessionId, text: "Complete this local acceptance task" });
		await until(
			async () =>
				assert.equal(
					(await invoke("getSessionBaseline", { sessionId: meta.sessionId })).transcript.agentActive,
					false,
				),
			60000,
		);
	});
	await check("statistics render real usage and filters with unknown cache coverage", async () => {
		const usage = await invoke("getUsageStatistics", { days: 7 });
		assert.ok(usage.totals.requests >= 1 && usage.totals.totalTokens > 0);
		assert.equal(usage.totals.cacheHitRate, null);
		await settings("统计数据");
		await page.getByRole("img", { name: "最近半年用量", exact: true }).waitFor();
		assert.equal(
			await page.getByRole("img", { name: "最近半年用量", exact: true }).locator("rect").count(),
			180,
		);
		await page.getByRole("img", { name: "Token 与缓存趋势", exact: true }).waitFor();
		await page.getByRole("combobox", { name: "按模型筛选", exact: true }).click();
		await page.getByRole("option", { name: usage.modelLabels[usage.models[0]], exact: true }).click();
		await page.getByRole("combobox", { name: "按项目筛选", exact: true }).click();
		await page.getByRole("option", { name: new RegExp(directory.split(/[\\/]/).at(-1)) }).click();
		await page.screenshot({ path: join(directory, "statistics.png") });
		await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click();
	});
	await check("original taskboard starts inside the iframe and creates a persisted task", async () => {
		const prerequisites = await invoke("getTaskboardStatus");
		assert.equal(prerequisites.installed, true, "Set VERA_TASKBOARD_HOME to a built Taskboard installation");
		assert.equal(prerequisites.nodeAvailable, true, "Taskboard requires Node.js on PATH");
		await page.getByRole("button", { name: "任务面板", exact: true }).click();
		await page.getByRole("button", { name: "启动任务面板", exact: true }).click();
		const frame = page.frameLocator('iframe[title="dashi-taskboard"]');
		await frame.locator("body").waitFor();
		await frame.getByText("所有项目", { exact: true }).first().waitFor({ timeout: 20000 });
		const board = await invoke("getTaskboardStatus");
		const response = await fetch(`${board.url}api/tasks`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ title: "VERA iframe acceptance" }),
		});
		assert.equal(response.status, 201);
		await frame.getByText("VERA iframe acceptance", { exact: true }).first().waitFor();
		await page.screenshot({ path: join(directory, "taskboard.png") });
		await page.getByRole("button", { name: "停止服务", exact: true }).click();
		await until(async () => assert.equal((await invoke("getTaskboardStatus")).running, false));
	});
	assert.deepEqual(pageErrors, []);
} catch (error) {
	if (page && !page.isClosed()) {
		await page.screenshot({ path: join(directory, "failure.png") }).catch(() => {});
		await writeFile(join(directory, "failure-ui.txt"), await page.locator("body").innerText());
	}
	console.error(error);
	process.exitCode = 1;
} finally {
	await invoke("stopTaskboard").catch(() => {});
	await application?.evaluate(({ app }) => app.exit(0)).catch(() => {});
	for (const child of children) child.kill();
	console.log(`REPORT ${join(directory, "report.json")}`);
}
