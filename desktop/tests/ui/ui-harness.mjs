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
	try {
		const page = await application.firstWindow();
		page.setDefaultTimeout(8000);
		// These scenarios use Chinese accessibility labels on every runner locale.
		if ((await page.evaluate(() => localStorage.getItem("vera.lang"))) !== "zh") {
			await page.evaluate(() => localStorage.setItem("vera.lang", "zh"));
			await page.reload();
		}
		// Connection state remains authoritative while the sidebar is hidden behind startup UI.
		await page.locator('[data-backend-status="connected"]').waitFor({ state: "attached" });
		await page.locator("#splash").waitFor({ state: "detached", timeout: 20000 });
		return { application, page };
	} catch (error) {
		// A failed launch cannot return the application handle to the caller's cleanup.
		await application.evaluate(({ app }) => app.exit(1)).catch(() => {});
		throw error;
	}
}
