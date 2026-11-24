import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Preferences } from "../../src/main/preferences";

const directories: string[] = [];
afterEach(async () => {
	for (const directory of directories.splice(0)) await rm(directory, { recursive: true, force: true });
});

describe("desktop preferences", () => {
	it("serializes patches without dropping concurrent UI changes", async () => {
		const directory = await mkdtemp(join(tmpdir(), "vera-ui-"));
		directories.push(directory);
		const preferences = new Preferences(directory);
		expect(await preferences.read("ui-state")).toBeNull();
		await Promise.all([
			preferences.update("ui-state", { theme: "dark" }),
			preferences.update("ui-state", { uiFontSize: 15 }),
		]);
		expect(JSON.parse(await readFile(join(directory, "ui-state.json"), "utf8"))).toEqual({
			theme: "dark",
			uiFontSize: 15,
		});
	});
});
