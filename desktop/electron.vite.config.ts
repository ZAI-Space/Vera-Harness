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
		plugins: [
			{
				name: "vera-katex-woff2",
				enforce: "pre",
				transform(code, id) {
					if (!/[/\\]katex[^/\\]*\.css(?:\?|$)/.test(id)) return;
					// 在 Vite 收集资产之前移除旧格式，保留每个公式字族的 WOFF2。
					return code.replace(/src:([^;}]+)/g, (declaration, sources: string) => {
						const woff2 = sources.split(",").filter((source) => source.includes(".woff2"));
						return woff2.length ? `src:${woff2.join(",")}` : declaration;
					});
				},
			},
			react(),
			tailwindcss(),
		],
	},
});
