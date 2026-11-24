/** Exercise role selection and cancellation through the real Electron composer. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launchDesktop } from "./ui-harness.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const directory = await mkdtemp(join(tmpdir(), "vera-subagent-picker-ui-"));
const connectionFile = join(directory, "connection.json");
const environment = {
	...process.env,
	VERA_GLOBAL_CONFIG_DIR: join(directory, "global"),
	VERA_SILENT_STARTUP: "1",
	PYTHONUTF8: "1",
};
for (const key of Object.keys(environment)) {
	if (
		key.endsWith("_API_KEY") ||
		["VERA_DESKTOP_TOKEN", "VERA_DESKTOP_USER_DATA", "VERA_DESKTOP_BACKGROUND"].includes(key)
	)
		delete environment[key];
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
let serverLog = "";
server.stdout.on("data", (value) => {
	serverLog += value.toString();
});
server.stderr.on("data", (value) => {
	serverLog += value.toString();
});
let application, page;
const pageErrors = [],
	checks = [];
async function until(action) {
	const deadline = Date.now() + 30000;
	let failure;
	while (Date.now() < deadline) {
		try {
			return await action();
		} catch (error) {
			failure = error;
			await new Promise((resolve) => setTimeout(resolve, 100));
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
	const result = await response.json();
	if (!response.ok) throw new Error(result.error);
	return result.result;
}
async function check(name, action) {
	await action();
	checks.push(name);
	console.log(`PASS ${name}`);
}
try {
	console.log(`EVIDENCE ${directory}`);
	const role = {
		id: "reader",
		name: "content-reader",
		description: "提炼文章内容",
		instructions: "Read the assigned article.",
		tools: [],
		skills: [],
		step_limit: 4,
		cost_limit: 0.1,
		wall_time_limit_seconds: 30,
		enabled: true,
	};
	await until(() =>
		invoke("saveSubagentRoles", {
			roles: [role, { ...role, id: "disabled", name: "disabled-reader", enabled: false }],
		}),
	);
	({ application, page } = await launchDesktop(connectionFile, join(directory, "frontend"), environment));
	page.on("pageerror", (error) => pageErrors.push(String(error)));
	await page.getByRole("button", { name: "选择项目", exact: true }).click();
	await page.getByRole("button", { name: "日常", exact: true }).last().click();
	const editor = page.locator('[contenteditable="true"]');
	const cancel = page.getByRole("button", { name: "取消所选命令", exact: true });
	const option = page.getByRole("button").filter({ hasText: "/subagent:content-reader" });
	async function chooseRole() {
		await editor.fill("/subagent");
		await option.waitFor();
		assert.equal(await page.getByRole("button").filter({ hasText: "/subagent:disabled-reader" }).count(), 0);
		await option.click();
		await cancel.waitFor();
	}
	await check("slash menu selects the enabled role without creating a session", async () => {
		await chooseRole();
		assert.equal((await invoke("listAllSessions")).length, 0);
		assert.equal((await editor.innerText()).trim(), "");
		await page.screenshot({ path: join(directory, "selected-role.png") });
	});
	for (const key of ["Backspace", "Delete", "Escape"]) {
		await check(`${key} removes the empty role chip without restoring the command`, async () => {
			if (!(await cancel.count())) await chooseRole();
			await editor.focus();
			await page.keyboard.press(key);
			await until(async () => assert.equal(await cancel.count(), 0));
			assert.equal((await editor.innerText()).trim(), "");
		});
	}
	for (const action of ["click", "Escape", "Backspace"]) {
		await check(`${action} cancels selection and retains the task text`, async () => {
			await chooseRole();
			await editor.fill("提炼两篇文章的共同观点");
			if (action === "click") await cancel.click();
			else {
				if (action === "Backspace") {
					await page.keyboard.press("Home");
					// Native cursor movement dispatches selectionchange asynchronously.
					await until(async () =>
						assert.equal(
							await editor.evaluate((element) => {
								const selection = window.getSelection();
								return (
									document.activeElement === element && selection?.isCollapsed && selection.anchorOffset === 0
								);
							}),
							true,
						),
					);
				}
				await page.keyboard.press(action);
			}
			await until(async () => assert.equal(await cancel.count(), 0));
			assert.equal(await editor.innerText(), "提炼两篇文章的共同观点");
		});
	}
	await check("typed command can be selected and deleted as ordinary editable text", async () => {
		await editor.fill("/subagent");
		await page.keyboard.press("ControlOrMeta+a");
		await page.keyboard.press("Backspace");
		assert.equal((await editor.innerText()).trim(), "");
		assert.equal(await cancel.count(), 0);
	});
	assert.equal((await invoke("listAllSessions")).length, 0);
	assert.deepEqual(pageErrors, []);
	await page.screenshot({ path: join(directory, "cancelled-role.png") });
} catch (error) {
	if (page && !page.isClosed()) {
		await page.screenshot({ path: join(directory, "failure.png") }).catch(() => {});
		await writeFile(join(directory, "failure-ui.txt"), await page.locator("body").innerText());
	}
	console.error(error);
	process.exitCode = 1;
} finally {
	await application?.evaluate(({ app }) => app.exit(0)).catch(() => {});
	server.kill();
	await writeFile(join(directory, "server.log"), serverLog);
	await writeFile(join(directory, "report.json"), JSON.stringify({ checks, pageErrors }, null, 2));
	console.log(`REPORT ${join(directory, "report.json")}`);
}
