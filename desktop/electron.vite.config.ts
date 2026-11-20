import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

const alias = { "@vera/contracts": resolve(import.meta.dirname, "src/contracts/index.ts") };
export default defineConfig({
	main: { plugins: [externalizeDepsPlugin()], resolve: { alias } },
	preload: {
		plugins: [externalizeDepsPlugin({ exclude: ["semver"] })],
		resolve: { alias },
		build: { rollupOptions: { output: { format: "cjs", entryFileNames: "index.cjs" } } },
	},
	renderer: {
		resolve: { alias },
		server: { port: 5180, strictPort: true },
		plugins: [react(), tailwindcss()],
	},
});
