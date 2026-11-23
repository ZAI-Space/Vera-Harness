import { randomUUID } from "node:crypto";
import { copyFile, mkdir, realpath, stat, writeFile } from "node:fs/promises";
import { basename, extname, isAbsolute, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { SUBSCRIPTION_TABLE } from "@vera/contracts";
import {
	app,
	BrowserWindow,
	dialog,
	ipcMain,
	Menu,
	Notification,
	nativeTheme,
	net,
	protocol,
	shell,
} from "electron";
import { Preferences } from "./preferences";
import { QuitController } from "./quit-controller";
import { validateDesktopRequest } from "./request";
import { BackendBridge } from "./services/backend";
import { HttpTransport } from "./services/http-transport";

/** VERA 的最小桌面壳：窗口、本机对话框、通知和 UI 偏好，业务执行统一交给外部适配器。 */
app.setName("VERA");
app.setPath("userData", process.env.VERA_DESKTOP_USER_DATA ?? join(app.getPath("appData"), "VERA-frontend"));
if (process.platform === "win32") app.setAppUserModelId("app.vera.desktop.frontend");
protocol.registerSchemesAsPrivileged([
	{ scheme: "vera-bg", privileges: { secure: true, standard: true, supportFetchAPI: true } },
]);

let mainWindow: BrowserWindow | null = null;
let isQuitting = false;
const listeners = new Set(Object.keys(SUBSCRIPTION_TABLE));
const backend = new BackendBridge((method, payload) => {
	if (listeners.has(method)) mainWindow?.webContents.send("vera:event", { method, payload });
});

function fileTarget(target: string, cwd: string | null): string {
	if (target.startsWith("vera-env-v1:")) throw new Error("不能将服务端路径作为本机路径打开");
	if (isAbsolute(target)) return resolve(target);
	if (!cwd || !isAbsolute(cwd)) throw new Error("相对路径需要本机工作目录");
	return resolve(cwd, target);
}

async function start(): Promise<void> {
	const directory = app.getPath("userData");
	await mkdir(directory, { recursive: true });
	const preferences = new Preferences(directory);
	const saved = (await preferences.read("ui-state")) as {
		theme?: string;
		windowBounds?: { width: number; height: number };
	} | null;
	nativeTheme.themeSource = saved?.theme === "dark" || saved?.theme === "light" ? saved.theme : "system";
	const background = join(directory, "backgrounds");
	await mkdir(background, { recursive: true });
	protocol.handle("vera-bg", async (request) => {
		const url = new URL(request.url);
		const name = decodeURIComponent(url.pathname.slice(1));
		if (url.hostname !== "background" || !/^[\w-]+\.(png|jpe?g|webp|gif)$/i.test(name))
			return new Response(null, { status: 404 });
		return net.fetch(pathToFileURL(join(background, name)).href);
	});

	const width = Math.max(960, Math.min(1920, saved?.windowBounds?.width || 1280));
	const height = Math.max(640, Math.min(1440, saved?.windowBounds?.height || 840));
	const window = new BrowserWindow({
		title: "VERA",
		// Keep isolated UI acceptance runs from taking over the user's desktop.
		show: process.env.VERA_DESKTOP_BACKGROUND !== "1",
		width,
		height,
		minWidth: 900,
		minHeight: 600,
		icon: app.isPackaged
			? join(process.resourcesPath, "app-icon.png")
			: join(import.meta.dirname, "../../build/icon.png"),
		backgroundColor: nativeTheme.shouldUseDarkColors ? "#17171a" : "#fafafa",
		...(process.platform === "win32"
			? {
					titleBarStyle: "hidden" as const,
					titleBarOverlay: {
						color: nativeTheme.shouldUseDarkColors ? "#17171a" : "#fafafa",
						symbolColor: nativeTheme.shouldUseDarkColors ? "#fafafa" : "#17171a",
						height: 48,
					},
				}
			: {}),
		...(process.platform === "darwin"
			? { titleBarStyle: "hiddenInset" as const, trafficLightPosition: { x: 16, y: 16 } }
			: {}),
		webPreferences: {
			backgroundThrottling: process.env.VERA_DESKTOP_BACKGROUND !== "1",
			offscreen: process.env.VERA_DESKTOP_BACKGROUND === "1",
			preload: join(import.meta.dirname, "../preload/index.cjs"),
			contextIsolation: true,
			sandbox: true,
			nodeIntegration: false,
		},
	});
	mainWindow = window;
	Menu.setApplicationMenu(null);
	window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
	window.webContents.on("will-navigate", (event, url) => {
		if (url !== window.webContents.getURL()) event.preventDefault();
	});
	const quit = new QuitController(
		() => window.webContents.send("vera:event", { method: "onQuitRequested" }),
		() => app.quit(),
	);
	window.on("close", (event) => {
		if (!isQuitting && !quit.canClose()) {
			event.preventDefault();
			return;
		}
		void preferences.update("ui-state", { windowBounds: window.getNormalBounds() });
	});

	const desktop: Record<string, (args: any) => unknown> = {
		getBackendStatus: () => ({ connected: backend.isConnected }),
		loadUiState: () => preferences.read("ui-state"),
		saveUiState: async ({ state }) => {
			await preferences.update("ui-state", state);
			if (state.theme) {
				nativeTheme.themeSource = state.theme;
				const dark = nativeTheme.shouldUseDarkColors;
				window.setBackgroundColor(dark ? "#17171a" : "#fafafa");
				if (process.platform === "win32")
					window.setTitleBarOverlay({
						color: dark ? "#17171a" : "#fafafa",
						symbolColor: dark ? "#fafafa" : "#17171a",
						height: 48,
					});
			}
		},
		loadEnvironmentUiState: () => preferences.read("navigation"),
		saveEnvironmentUiState: ({ state }) => preferences.write("navigation", state),
		getAppInfo: () => ({
			name: "VERA",
			version: app.getVersion(),
			releaseChannel: app.isPackaged ? "stable" : "dev",
			platform: process.platform,
			arch: process.arch,
			electron: process.versions.electron,
			chrome: process.versions.chrome,
			node: process.versions.node,
			repoUrl: "",
		}),
		pickDirectory: async () => {
			const result = await dialog.showOpenDialog(window, { properties: ["openDirectory"] });
			return result.canceled ? null : result.filePaths[0] || null;
		},
		validateProjectDirectory: async ({ path }) => {
			if (!isAbsolute(path) || !(await stat(path)).isDirectory()) throw new Error("请选择有效的本机目录");
			return realpath(path);
		},
		getDailyDir: async () => {
			const path = join(directory, "workspace");
			await mkdir(path, { recursive: true });
			return path;
		},
		resolvePath: async ({ target, cwd }) => {
			const path = fileTarget(target, cwd);
			await stat(path);
			return path;
		},
		openPath: async ({ target, cwd }) => {
			const error = await shell.openPath(fileTarget(target, cwd));
			if (error) throw new Error(error);
		},
		revealPath: ({ target, cwd }) => shell.showItemInFolder(fileTarget(target, cwd)),
		openExternal: ({ url }) => {
			if (!["https:", "http:"].includes(new URL(url).protocol)) throw new Error("不支持的链接类型");
			return shell.openExternal(url);
		},
		saveFileDialog: async ({ defaultName, content }) => {
			const result = await dialog.showSaveDialog(window, { defaultPath: basename(defaultName) });
			if (result.canceled || !result.filePath) return null;
			await writeFile(result.filePath, content, "utf8");
			return result.filePath;
		},
		pickBackgroundImage: async () => {
			const result = await dialog.showOpenDialog(window, {
				properties: ["openFile"],
				filters: [{ name: "图片", extensions: ["png", "jpg", "jpeg", "webp", "gif"] }],
			});
			const source = result.filePaths[0];
			if (result.canceled || !source) return null;
			const name = `${randomUUID()}${extname(source).toLowerCase()}`;
			await copyFile(source, join(background, name));
			return name;
		},
		testTaskNotification: () => {
			if (!Notification.isSupported()) return "unsupported";
			new Notification({
				title: "VERA",
				body: "任务通知已开启",
				icon: join(import.meta.dirname, "../../build/icon.png"),
			}).show();
			return "submitted";
		},
		setNotificationLanguage: () => {},
		setTaskNotificationNavigationReady: () => {},
		setQuitGuard: ({ enabled }) => quit.setEnabled(enabled),
		quitDialogShown: () => quit.acknowledge(),
		confirmQuit: () => quit.confirm(),
		showComposerEditMenu: () =>
			Menu.buildFromTemplate([
				{ role: "cut" },
				{ role: "copy" },
				{ role: "paste" },
				{ role: "selectAll" },
			]).popup({ window }),
		cancelComposerEditMenu: () => {},
		uiPluginsGetConfig: () => ({ enabled: false, plugins: {}, assignments: {} }),
		uiPluginsList: () => [],
	};

	ipcMain.handle("vera:invoke", async (event, request: { method: string; args: unknown }) => {
		if (event.sender !== window.webContents) throw new Error("Untrusted desktop sender");
		request = validateDesktopRequest(request);
		const handler = desktop[request.method];
		if (handler) return handler(request.args);
		return backend.invoke(request.method, request.args);
	});
	if (process.env.VERA_DESKTOP_CONNECTION_FILE) {
		await backend.connect(await HttpTransport.fromFile(process.env.VERA_DESKTOP_CONNECTION_FILE));
	}
	if (!app.isPackaged && process.env.ELECTRON_RENDERER_URL)
		await window.loadURL(process.env.ELECTRON_RENDERER_URL);
	else await window.loadFile(join(import.meta.dirname, "../renderer/index.html"));
	if (process.env.VERA_DESKTOP_BACKGROUND !== "1") window.show();
}

app
	.whenReady()
	.then(start)
	.catch((error) => {
		console.error(error);
		app.quit();
	});
app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => {
	isQuitting = true;
	void backend.connect(null);
});
