/** Run each isolated Electron acceptance flow and stop on the first failure. */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

for (const name of [
	"ui-settings-smoke.mjs",
	"ui-global-settings-smoke.mjs",
	"ui-market-smoke.mjs",
	"ui-model-config-smoke.mjs",
	"ui-general-assistant-smoke.mjs",
]) {
	const result = spawnSync(process.execPath, [fileURLToPath(new URL(name, import.meta.url))], {
		stdio: "inherit",
		windowsHide: true,
		timeout: 360000,
	});
	if (result.error) throw result.error;
	if (result.status !== 0) process.exit(result.status ?? 1);
}
