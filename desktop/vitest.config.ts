import { resolve } from "node:path";
import { defineConfig } from "vitest/config";
export default defineConfig({
	resolve: { alias: { "@vera/contracts": resolve(import.meta.dirname, "src/contracts/index.ts") } },
	esbuild: { jsx: "automatic" },
	test: { maxWorkers: 2, server: { deps: { inline: [/markstream-react/] } } },
});
