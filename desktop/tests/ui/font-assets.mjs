/** Inspect the actual Electron output for duplicated mathematical font formats. */
import assert from "node:assert/strict";
import { readdir, stat } from "node:fs/promises";
import { resolve } from "node:path";

const directory = resolve(import.meta.dirname, "../../out/renderer/assets");
const names = await readdir(directory);
const fonts = names.filter((name) => /\.(woff2?|ttf|otf)$/.test(name));
assert(fonts.some((name) => name.startsWith("KaTeX_") && name.endsWith(".woff2")));
assert(fonts.some((name) => name.startsWith("codicon-") && name.endsWith(".ttf")));
assert.deepEqual(
	fonts.filter((name) => /^KaTeX_.*\.(woff|ttf)$/.test(name)),
	[],
);
const bytes = (await Promise.all(fonts.map((name) => stat(resolve(directory, name))))).reduce(
	(total, file) => total + file.size,
	0,
);
console.log(`PASS font assets: ${fonts.length} files, ${bytes} bytes; no legacy KaTeX formats`);
