/** Real assistant conversation, approval and tool execution through Electron/IPC/Python. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launchDesktop } from "./ui-harness.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const python =
	process.env.VERA_PYTHON ??
	join(repository, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const directory = await mkdtemp(join(tmpdir(), "vera-general-chat-ui-"));
const connectionFile = join(directory, "connection.json");
const modelFile = join(directory, "model.json");
const releaseFile = join(directory, "release-model");
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
	start([
		"-m",
		"tests.run.general_assistant_ui_fixture",
		"--connection-file",
		modelFile,
		"--release-file",
		releaseFile,
	]);
	await until(() => access(connectionFile), 60000);
	await until(() => access(modelFile));
	const baseUrl = JSON.parse(await readFile(modelFile, "utf8")).url;
	await invoke("addCustomProvider", {
		input: {
			id: "general-local",
			name: "General local",
			baseUrl,
			api: "openai-completions",
			models: [{ id: "deepseek-flash" }],
		},
	});
	({ application, page } = await launchDesktop(connectionFile, join(directory, "frontend"), environment));
	page.on("pageerror", (error) => pageErrors.push(String(error)));
	const expand = page.getByRole("button", { name: "展开导航栏", exact: true });
	if (await expand.isVisible()) await expand.click();
	await check(
		"self introduction completes as text, without tools or pricing, and tokens persist",
		async () => {
			await page.getByRole("button", { name: /^(选择模型|deepseek-flash)/ }).click();
			await page.getByRole("button", { name: "deepseek-flash", exact: true }).click();
			await page.keyboard.press("Escape");
			await page.getByRole("button", { name: "选择项目", exact: true }).click();
			await page.getByRole("main").getByRole("button", { name: "日常", exact: true }).click();
			await page
				.getByRole("textbox", { name: "随便问点什么，/ 命令，@ 上下文", exact: true })
				.fill("你好，请你做一个自我介绍！");
			await page.getByRole("button", { name: "发送", exact: true }).click();
			await page
				.getByText(
					"我是 VERA，可以帮助你问答、写作和编程。我会根据你的任务选择工具，自我介绍不需要读取项目文件。",
					{ exact: true },
				)
				.waitFor({ timeout: 60000 });
			await until(async () => {
				const sessions = await invoke("listAllSessions");
				assert.equal(
					(await invoke("getSessionBaseline", { sessionId: sessions[0].sessionId })).transcript.agentActive,
					false,
				);
			}, 60000);
			const session = (await invoke("listAllSessions"))[0];
			const messages = await invoke("getSessionMessages", { sessionId: session.sessionId });
			assert.equal(messages.filter((row) => row.kind === "assistant").length, 1);
			assert.ok(messages.every((row) => !row.tools?.length));
			assert.equal(
				await page.getByText("Worker exited without a completion receipt.", { exact: true }).count(),
				0,
			);
			assert.equal(await page.getByText("Run stopped: Submitted", { exact: true }).count(), 0);
			const usage = await invoke("getUsageStatistics");
			assert.equal(usage.totals.requests, 1);
			assert.equal(usage.totals.totalTokens, 18);
			await page.screenshot({ path: join(directory, "general-conversation.png") });
			await page.getByRole("button", { name: "设置", exact: true }).click();
			await page.getByRole("dialog").getByRole("button", { name: "统计数据", exact: true }).click();
			const statistics = page.getByRole("region", { name: "统计数据", exact: true });
			await statistics.getByText("18", { exact: true }).first().waitFor();
			await page.screenshot({ path: join(directory, "token-usage.png") });
		},
	);
	await check("coding workflow is an optional editable role template", async () => {
		await page.getByRole("dialog").getByRole("button", { name: "Subagent", exact: true }).click();
		await page.getByRole("button", { name: "创建 Subagent", exact: true }).click();
		await page.getByRole("button", { name: "编程任务流程", exact: true }).click();
		const instructions = await page.getByRole("textbox", { name: /^角色指令/ }).inputValue();
		assert.ok(instructions.includes("Reproduce") && instructions.includes("subagent_finish"));
		await page.getByRole("textbox", { name: /^简介/ }).fill("Opt-in coding workflow acceptance");
		await page.getByRole("button", { name: "保存角色草稿", exact: true }).click();
		await until(async () => assert.equal((await invoke("getSubagentRoles"))[0].name, "coding-workflow"));
		await page.screenshot({ path: join(directory, "coding-workflow-role.png") });
	});
	await check(
		"queued messages run in order; send now stops the active task and retains older inputs",
		async () => {
			await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click();
			await page.getByRole("dialog").waitFor({ state: "hidden" });
			const sessionId = (await invoke("listAllSessions"))[0].sessionId;
			const editor = page.locator('[contenteditable="true"]').first();
			const send = async (text, immediately = false) => {
				await editor.fill(text);
				await page.getByRole("button", { name: immediately ? "立即发送" : "发送", exact: true }).click();
			};
			const settled = () =>
				until(
					async () =>
						assert.equal((await invoke("getSessionBaseline", { sessionId })).transcript.agentActive, false),
					60000,
				);
			await send("queue-hold-one");
			await page.getByText("完成：queue-hold-one", { exact: true }).waitFor({ timeout: 30000 });
			await send("queue-two");
			await send("queue-three");
			await until(async () =>
				assert.deepEqual(await invoke("getFollowUpMessages", { sessionId }), ["queue-two", "queue-three"]),
			);
			await page.screenshot({ path: join(directory, "queued-messages.png") });
			await writeFile(releaseFile, "release");
			await settled();
			let messages = await invoke("getSessionMessages", { sessionId });
			assert.deepEqual(
				messages
					.filter((row) => row.kind === "user")
					.slice(-3)
					.map((row) => row.text),
				["queue-hold-one", "queue-two", "queue-three"],
			);
			await unlink(releaseFile);
			await send("queue-hold-two");
			await page.getByText("完成：queue-hold-two", { exact: true }).waitFor({ timeout: 30000 });
			await send("queue-later");
			await send("queue-urgent", true);
			await settled();
			await writeFile(releaseFile, "release");
			messages = await invoke("getSessionMessages", { sessionId });
			assert.deepEqual(
				messages
					.filter((row) => row.kind === "user")
					.slice(-3)
					.map((row) => row.text),
				["queue-hold-two", "queue-urgent", "queue-later"],
			);
			assert.deepEqual(await invoke("getFollowUpMessages", { sessionId }), []);
			await page.getByText("完成：queue-later", { exact: true }).waitFor();
			await page.screenshot({ path: join(directory, "priority-message-completed.png") });
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
