import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

/** 防止独立前端重新引入旧后端、SDK、SSH 或跨目录源码依赖。 */
const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
for (const dependency of Object.keys({ ...manifest.dependencies, ...manifest.devDependencies })) {
	assert(!/^@(?:percho|earendil-works)\//.test(dependency), `Forbidden backend dependency: ${dependency}`);
}
async function scan(directory) {
	for (const entry of await readdir(directory, { withFileTypes: true })) {
		const file = join(directory, entry.name);
		if (entry.isDirectory()) await scan(file);
		else if (/\.[cm]?[jt]sx?$/.test(entry.name) && !entry.name.includes(".test.")) {
			const code = await readFile(file, "utf8");
			assert(
				!/from\s+["'](?:@percho\/|@earendil-works\/|node:child_process)/.test(code),
				`Forbidden runtime import: ${file}`,
			);
			assert(
				!/from\s+["'][^"']*(?:packages\/backend|runtime\/ssh|remote-connection)["']/.test(code),
				`Old backend source reference: ${file}`,
			);
		}
	}
}
await scan(join(root, "src"));
console.log("PASS: standalone desktop frontend contains no legacy backend or agent SDK dependencies");
