/** Real Electron/IPC/Python acceptance. Run after `npm run build`; no user profile is opened. */
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { access, copyFile, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launchDesktop } from "./ui-harness.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const python =
	process.env.VERA_PYTHON ??
	join(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const directory = await mkdtemp(join(tmpdir(), "vera-settings-ui-"));
const connectionFile = join(directory, "connection.json");
const modelFile = join(directory, "model.json");
const profile = join(directory, "frontend");
const environment = {
	...process.env,
	VERA_GLOBAL_CONFIG_DIR: join(directory, "global"),
	VERA_SILENT_STARTUP: "1",
	PYTHONUTF8: "1",
	LITELLM_LOCAL_MODEL_COST_MAP: "True",
};
for (const name of Object.keys(environment)) {
	if (
		name.endsWith("_API_KEY") ||
		["VERA_DESKTOP_TOKEN", "VERA_DESKTOP_USER_DATA", "VERA_DESKTOP_BACKGROUND"].includes(name)
	)
		delete environment[name];
}
const processes = [];
const checks = [];
const errors = [];
let application;
let page;
let modelProviderName;

function start(arguments_) {
	const child = spawn(python, arguments_, {
		cwd: repository,
		env: environment,
		windowsHide: true,
		stdio: ["ignore", "pipe", "pipe"],
	});
	child.stderr.on("data", (value) => errors.push(value.toString()));
	child.stdout.resume();
	processes.push(child);
	return child;
}

async function until(action, timeout = 15000) {
	const deadline = Date.now() + timeout;
	let lastError;
	while (Date.now() < deadline) {
		try {
			return await action();
		} catch (error) {
			lastError = error;
			await new Promise((resolve_) => setTimeout(resolve_, 100));
		}
	}
	throw lastError;
}

async function invoke(method, args = {}) {
	const connection = JSON.parse(await readFile(connectionFile, "utf8"));
	const response = await fetch(`${connection.url}/invoke`, {
		method: "POST",
		headers: { Authorization: `Bearer ${connection.token}`, "Content-Type": "application/json" },
		body: JSON.stringify({ method, args }),
	});
	const result = await response.json();
	if (!response.ok) throw new Error(result.error);
	return result.result;
}

async function check(name, action) {
	try {
		await action();
		checks.push({ name, status: "passed" });
		console.log(`PASS ${name}`);
	} catch (error) {
		checks.push({ name, status: "failed", error: String(error) });
		if (page && !page.isClosed()) {
			await page.screenshot({ path: join(directory, `failure-${checks.length}.png`) }).catch(() => {});
			await writeFile(
				join(directory, "failure-ui.txt"),
				await page
					.locator("body")
					.innerText()
					.catch(() => ""),
			);
		}
		throw error;
	} finally {
		await writeFile(join(directory, "report.json"), JSON.stringify({ checks }, null, 2));
	}
}

async function open() {
	({ application, page } = await launchDesktop(connectionFile, profile, environment));
	page.on("pageerror", (error) => errors.push(String(error)));
	await page.getByText("后端已连接", { exact: true }).waitFor();
}

async function settings(category) {
	const dialog = page
		.getByRole("dialog")
		.filter({ has: page.getByRole("heading", { name: "设置", exact: true }) });
	if (!(await dialog.count())) {
		const expand = page.getByRole("button", { name: "展开导航栏", exact: true });
		if (await expand.isVisible()) await expand.click();
		await page.getByRole("button", { name: "设置", exact: true }).click();
	}
	if (category) await dialog.getByRole("button", { name: category, exact: true }).click();
	return dialog;
}

async function closeSettings() {
	await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click();
}

async function choose(label, option) {
	const trigger = page.getByRole("combobox", { name: label, exact: true });
	await until(async () => {
		await trigger.scrollIntoViewIfNeeded();
		if ((await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click();
		await page.getByRole("option", { name: option, exact: true }).click();
	});
}

try {
	console.log(`EVIDENCE ${directory}`);
	await mkdir(join(directory, "backend/skills/ui-skill"), { recursive: true });
	await writeFile(
		join(directory, "backend/skills/ui-skill/SKILL.md"),
		"---\nname: ui-skill\ndescription: Actual installed user skill.\n---\nRead project files.\n",
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
	await until(() => access(connectionFile));
	await until(() => access(modelFile));
	modelProviderName = new URL(JSON.parse(await readFile(modelFile, "utf8")).url).host;
	await open();

	await check("empty model configuration has no phantom selected model", async () => {
		assert.deepEqual(await invoke("listModels"), []);
		await page.getByRole("button", { name: /^选择模型/ }).waitFor();
		assert.equal(
			await application.evaluate(({ BrowserWindow }) =>
				BrowserWindow.getAllWindows().every((window) => !window.isVisible()),
			),
			true,
		);
	});
	await check("user skills load from disk while their removed settings page stays absent", async () => {
		await settings("模型");
		assert.equal(await page.getByRole("button", { name: "Skills", exact: true }).count(), 0);
		assert.ok((await invoke("getLoadedResources")).skills.some((skill) => skill.name === "ui-skill"));
	});
	await check("settings navigation includes the current About page", async () => {
		assert.equal(
			await page
				.getByRole("dialog")
				.getByRole("button", { name: /^(关于|About)$/ })
				.count(),
			1,
		);
	});
	await check("model creation fetches, selects and saves the actual catalog", async () => {
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
		await page.getByRole("button", { name: "测试", exact: true }).click();
		await page.getByText("连接正常 · gpt-4o-mini", { exact: true }).waitFor({ timeout: 30000 });
	});
	await check("model visibility updates execution catalogs", async () => {
		await page.getByRole("button", { name: `展开 ${modelProviderName} 的模型`, exact: true }).click();
		await page.getByRole("switch", { name: "在模型列表中显示 gpt-4o-mini", exact: true }).click();
		await until(async () => assert.deepEqual(await invoke("listModels"), []));
		await closeSettings();
		await page.getByRole("button", { name: /^选择模型/ }).waitFor();
		await settings("模型");
		await page.getByRole("button", { name: `展开 ${modelProviderName} 的模型`, exact: true }).click();
		await page.getByRole("switch", { name: "在模型列表中显示 gpt-4o-mini", exact: true }).click();
		await until(async () => assert.equal((await invoke("listModels")).length, 1));
		await closeSettings();
	});
	await check("Confirm blocks actual effects until approval", async () => {
		await page.getByRole("button", { name: "选择项目", exact: true }).click();
		await page.getByRole("main").getByRole("button", { name: "日常", exact: true }).click();
		await page
			.getByRole("textbox", { name: "随便问点什么，/ 命令，@ 上下文", exact: true })
			.fill("UI_CONFIRM verify the local file.");
		await page.getByRole("button", { name: "发送", exact: true }).click();
		await page.getByRole("button", { name: "允许一次", exact: true }).waitFor({ timeout: 60000 });
		await assert.rejects(access(join(profile, "workspace/qa-approved.txt")));
		await page.getByRole("button", { name: "允许一次", exact: true }).click();
		await page.getByText("vera-ui-done", { exact: true }).waitFor();
		await page.getByRole("button", { name: "发送", exact: true }).waitFor();
		assert.equal(await readFile(join(profile, "workspace/qa-approved.txt"), "utf8"), "vera-ui-ok");
	});
	await check("Human executes direct Bash and restores policy after frontend restart", async () => {
		await until(async () => {
			const [session] = await invoke("listAllSessions");
			assert.equal(
				(await invoke("getSessionBaseline", { sessionId: session.sessionId })).transcript.agentActive,
				false,
			);
		});
		await page.getByRole("button", { name: "权限模式", exact: true }).click();
		await page.getByRole("menuitemradio", { name: /^Human/ }).click();
		await until(async () => {
			const sessions = await invoke("listAllSessions");
			assert.equal(
				(await invoke("getSessionSelections", { sessionId: sessions[0].sessionId })).permissionPolicy,
				"human",
			);
		});
		await page
			.getByRole("textbox", { name: "随便问点什么，/ 命令，@ 上下文", exact: true })
			.fill(
				"printf ui-human > ui-human.txt; echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; printf ui-human-done",
			);
		await page.getByRole("button", { name: "发送", exact: true }).click();
		await page.getByText("ui-human-done", { exact: true }).waitFor({ timeout: 30000 });
		await page.getByRole("button", { name: "发送", exact: true }).waitFor();
		assert.equal(await readFile(join(profile, "workspace/ui-human.txt"), "utf8"), "ui-human");
		await application.evaluate(({ app }) => app.exit(0)).catch(() => {});
		await open();
		const expand = page.getByRole("button", { name: "展开导航栏", exact: true });
		if (await expand.isVisible()) await expand.click();
		await page
			.getByRole("complementary", { name: "导航", exact: true })
			.getByRole("button", { name: "UI_CONFIRM verify the local file.", exact: true })
			.click();
		await until(async () =>
			assert.equal(await page.getByRole("button", { name: "权限模式", exact: true }).innerText(), "Human"),
		);
	});
	await check("Yolo runs without approval", async () => {
		await page.getByRole("button", { name: "权限模式", exact: true }).click();
		await page.getByRole("menuitemradio", { name: /^Yolo/ }).click();
		await page.getByRole("button", { name: "了解风险并开启", exact: true }).click();
		await page
			.getByRole("textbox", { name: "随便问点什么，/ 命令，@ 上下文", exact: true })
			.fill("UI_YOLO verify without approval.");
		await page.getByRole("button", { name: "发送", exact: true }).click();
		await until(
			async () => assert.equal(await page.getByText("vera-ui-done", { exact: true }).count(), 2),
			60000,
		);
		assert.equal(await page.getByRole("button", { name: "允许一次", exact: true }).count(), 0);
	});
	await check("slash help renders runtime commands through the composer", async () => {
		await until(async () => {
			const [session] = await invoke("listAllSessions");
			assert.equal(
				(await invoke("getSessionBaseline", { sessionId: session.sessionId })).transcript.agentActive,
				false,
			);
		});
		await page.getByRole("textbox", { name: "随便问点什么，/ 命令，@ 上下文", exact: true }).fill("/help");
		await page.getByRole("button", { name: "发送", exact: true }).click();
		await until(async () => {
			const content = await page.getByRole("main").innerText();
			assert.match(content, /\/goal/);
			assert.match(content, /\/skill/);
		});
	});
	await check("MCP save/test/edit/delete uses actual stdio and persists no enablement", async () => {
		const serverFile = join(directory, "MCP server.py");
		await copyFile(join(repository, "tests/run/mcp_fixture.py"), serverFile);
		await settings("MCP");
		await page.getByRole("button", { name: "添加 JSON", exact: true }).click();
		await page
			.getByRole("textbox", { name: "MCP JSON", exact: true })
			.fill(JSON.stringify({ mcpServers: { "ui-mcp": { command: python, args: ["-u", serverFile] } } }));
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await page.getByRole("button", { name: "测试连接", exact: true }).click();
		await page
			.getByText("连接测试通过：2 个工具。任务开始时会重新连接。", { exact: true })
			.waitFor({ timeout: 30000 });
		await page.getByRole("button", { name: "2 个工具", exact: true }).click();
		await page.getByText("echo", { exact: true }).waitFor();
		const config = (await invoke("mcpConfigList")).global[0];
		assert.equal(config.enabled, false);
		assert.equal(config.verification.ok, true);
		await page.getByRole("button", { name: "启用", exact: true }).click();
		await until(async () => assert.equal((await invoke("mcpConfigList")).global[0].enabled, true));
		await page.getByRole("button", { name: "编辑", exact: true }).click();
		assert.deepEqual(
			JSON.parse(await page.getByRole("textbox", { name: "MCP JSON", exact: true }).inputValue()).mcpServers[
				"ui-mcp"
			].args,
			["-u", serverFile],
		);
		await page
			.getByRole("textbox", { name: "MCP JSON", exact: true })
			.fill(JSON.stringify({ mcpServers: { "ui-mcp": { command: "vera-ui-nonexistent-command" } } }));
		await page.getByRole("button", { name: "保存", exact: true }).click();
		await page.getByRole("button", { name: "测试连接", exact: true }).click();
		await until(async () => assert.equal((await invoke("mcpConfigList")).global[0].verification?.ok, false));
		await page.getByRole("button", { name: "删除", exact: true }).click();
		await page.getByRole("button", { name: "删除", exact: true }).last().click();
		await until(async () => assert.deepEqual((await invoke("mcpConfigList")).global, []));
	});
	await check("Subagent create edit disable persists independently of a model catalog", async () => {
		await settings("Subagent");
		await page.getByRole("button", { name: "创建 Subagent", exact: true }).click();
		await page.getByRole("textbox", { name: /^名称/ }).fill("ui-reader");
		await page.getByRole("textbox", { name: /^简介/ }).fill("UI read role");
		await page.getByRole("textbox", { name: /^角色指令/ }).fill("Inspect files without modifying them.");
		await page.getByRole("textbox", { name: /^允许的工具/ }).fill("project_read");
		assert.equal(
			await page.getByRole("combobox", { name: "模型", exact: true }).getByRole("option").count(),
			2,
		);
		await page.getByRole("button", { name: "保存角色草稿", exact: true }).click();
		await page.getByRole("button", { name: "编辑 ui-reader", exact: true }).click();
		await page.getByRole("textbox", { name: /^简介/ }).fill("UI edited role");
		await page.getByRole("button", { name: "保存角色草稿", exact: true }).click();
		await page.getByRole("switch", { name: "启用 ui-reader 草稿", exact: true }).click();
		await until(async () => {
			const roles = await invoke("getSubagentRoles");
			assert.equal(roles[0].description, "UI edited role");
			assert.equal(roles[0].enabled, false);
		});
	});
	await check("sandbox selector follows actual backend availability", async () => {
		await settings("行为");
		await choose("权限模式", "Human");
		await until(async () => assert.equal((await invoke("getBehaviorSettings")).permissionPolicy, "human"));
		await page.getByRole("button", { name: "添加配置", exact: true }).click();
		await page.getByRole("textbox", { name: "配置名称", exact: true }).fill("ui-docker");
		await page.getByRole("button", { name: "保存配置草稿", exact: true }).click();
		await page.getByText("ui-docker", { exact: true }).waitFor();
		const status = (await invoke("getSandboxProfiles")).status.choices.find(
			(row) => row.name === "ui-docker",
		);
		await page.getByRole("combobox", { name: "默认环境", exact: true }).scrollIntoViewIfNeeded();
		await page.getByRole("combobox", { name: "默认环境", exact: true }).click();
		assert.equal(await page.getByRole("option", { name: /^ui-docker/ }).isDisabled(), !status.available);
		await page.keyboard.press("Escape");
		await closeSettings();
	});
	await check("archive and restore refreshes the sidebar without a reload", async () => {
		const sidebar = page.getByRole("complementary", { name: "导航", exact: true });
		const session = sidebar.getByRole("button", { name: "UI_CONFIRM verify the local file.", exact: true });
		await session.click({ button: "right" });
		await page.getByRole("menuitem", { name: "归档", exact: true }).click();
		await settings("已归档的聊天");
		await page.getByRole("button", { name: "取消归档", exact: true }).click();
		await until(async () =>
			assert.equal(await page.getByRole("button", { name: "取消归档", exact: true }).count(), 0),
		);
		await closeSettings();
		await session.waitFor();
	});
	await check("scheduled Run now produces a completed receipt and real file", async () => {
		await page.getByRole("button", { name: "定时任务", exact: true }).click();
		await page.getByRole("button", { name: "新建任务", exact: true }).first().click();
		await page.getByRole("textbox", { name: "任务名称", exact: true }).fill("UI schedule");
		await page
			.getByRole("textbox", { name: "任务内容", exact: true })
			.fill("QA_SCHEDULE write the acceptance marker.");
		await choose("模型", `${modelProviderName} · gpt-4o-mini`);
		await choose("权限策略", "Yolo");
		await choose("重复频率", "手动触发");
		await page.getByRole("button", { name: "保存任务", exact: true }).click();
		await page.getByRole("button", { name: "立即运行", exact: true }).click();
		await until(async () => {
			const snapshot = await invoke("getScheduledTasks");
			assert.equal(snapshot.runs[0]?.status, "completed");
		}, 60000);
		await until(async () => assert.match(await page.locator("body").innerText(), /已完成/));
		assert.equal(await readFile(join(profile, "workspace/qa-scheduled.txt"), "utf8"), "vera-ui-ok");
		assert.equal(await page.getByRole("switch", { name: "启用此任务", exact: true }).isDisabled(), true);
	});
	await check("deleting the provider clears the picker and stays deleted after restart", async () => {
		await settings("模型");
		await page.getByRole("button", { name: `删除 ${modelProviderName} 的配置`, exact: true }).click();
		const confirm = page
			.getByRole("dialog")
			.filter({ has: page.getByRole("button", { name: "删除", exact: true }) });
		await confirm.getByRole("button", { name: "删除", exact: true }).click();
		await until(async () => assert.deepEqual(await invoke("listModels"), []));
		await closeSettings();
		await application.evaluate(({ app }) => app.exit(0)).catch(() => {});
		await open();
		await page.getByRole("button", { name: /^选择模型/ }).waitFor();
		await settings("模型");
		assert.equal(await page.getByRole("region", { name: modelProviderName, exact: true }).count(), 0);
	});
	await page.screenshot({ path: join(directory, "verified-settings.png") });
	console.log(`VERIFIED ${checks.length} real UI flows`);
} catch (error) {
	console.error(String(error));
	process.exitCode = 1;
} finally {
	if (application) await application.evaluate(({ app }) => app.exit(0)).catch(() => {});
	try {
		execFileSync(
			python,
			[
				"-c",
				"from pathlib import Path;from vera.scheduler.engine import stop_service;import sys;stop_service(Path(sys.argv[1]))",
				join(directory, "backend/scheduler"),
			],
			{ cwd: repository, env: environment, timeout: 10000, windowsHide: true, stdio: "ignore" },
		);
	} catch {}
	for (const child of processes.reverse()) {
		if (child.exitCode !== null) continue;
		if (process.platform === "win32") {
			try {
				execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
					stdio: "ignore",
					windowsHide: true,
				});
			} catch {}
		} else child.kill("SIGTERM");
	}
	await writeFile(join(directory, "diagnostics.log"), errors.join("\n"));
	console.log(`REPORT ${join(directory, "report.json")}`);
}
