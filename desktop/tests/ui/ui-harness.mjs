/** Launch the actual Electron shell with a private profile and no desktop window. */
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { _electron } = require("playwright-core");
const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

/** Reuses a real backend discovery file; never replaces preload or IPC handlers. */
export async function launchDesktop(connectionFile, profileDirectory, environmentOverrides = {}) {
	const environment = {
		...globalThis.process?.env,
		...environmentOverrides,
		VERA_DESKTOP_BACKGROUND: "1",
		VERA_DESKTOP_USER_DATA: profileDirectory,
		VERA_DESKTOP_CONNECTION_FILE: connectionFile,
	};
	delete environment.ELECTRON_RUN_AS_NODE;
	const application = await _electron.launch({
		executablePath: require("electron"),
		args: [resolve(desktopRoot, "out/main/index.js"), "--vera-ui-acceptance"],
		env: environment,
	});
	const page = await application.firstWindow();
	page.setDefaultTimeout(8000);
	// These scenarios use Chinese accessibility labels on every runner locale.
	if ((await page.evaluate(() => localStorage.getItem("vera.lang"))) !== "zh") {
		await page.evaluate(() => localStorage.setItem("vera.lang", "zh"));
		await page.reload();
	}
	await page.getByText(/^(后端已连接|Backend connected)$/).waitFor();
	// The workbench can be mounted behind the splash while its root is still transparent.
	await page.locator("#splash").waitFor({ state: "detached", timeout: 20000 });
	return { application, page };
}
