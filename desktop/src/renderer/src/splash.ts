/**
 * 开屏动画（三圈彩球旋转 → 加速吸收 → 彩色迸发散场）控制。
 * 样式 = styles/splash.css（link 渲染阻塞，首帧前就绪）；DOM = splash-dom.ts 首帧前生成；
 * 数据准备与工作台共用同一份 DOM/时钟；只有工作台可挂载后才允许收场。
 */

import { animateSplashExit, SPLASH_EXIT_MS } from "./splash-orbits";

/** 最短展示时长：先看清 Logo 与外围旋转，之后才允许内聚吸收。 */
const MIN_DISPLAY_MS = 1600;
/** 工作台已可挂载后，首批模型数据加载的收场兜底；不覆盖数据准备阶段。 */
const MAX_DISPLAY_MS = 4500;
const EXIT_MS_REDUCED = 300;
/** 同次运行只播一次（macOS activate 重建窗口不重播；调试重播 = devtools 清此键） */
const PLAYED_KEY = "pi-splash-played";

let finished = false;
let initialized = false;
let released = false;
let skipAnimation = false;
let exitListener: (() => void) | undefined;

export function onSplashExit(listener: () => void): void {
	exitListener = listener;
}

export function setSplashMessage(message: string): void {
	const status = document.querySelector(".sp-status");
	if (status) status.textContent = message;
	document.querySelector(".sp-line")?.setAttribute("aria-label", message);
}

function markPlayed(): void {
	try {
		sessionStorage.setItem(PLAYED_KEY, "1");
	} catch {
		// sessionStorage 不可用时静默失败（下次重建窗口会重播，可接受）
	}
}

function alreadyPlayed(): boolean {
	try {
		return sessionStorage.getItem(PLAYED_KEY) === "1";
	} catch {
		return false;
	}
}

function removeSplash(): void {
	document.getElementById("splash")?.remove();
}

/** 首个 renderer 入口调用一次。重载只显示静态品牌，仍等待数据准备完成。 */
export function initSplash(): void {
	if (initialized) return;
	initialized = true;
	skipAnimation = alreadyPlayed();
	if (skipAnimation) document.documentElement.dataset.splashStatic = "true";
}

/** Only arm the fallback once the workbench can render, never while awaiting migration or a choice. */
export function releaseSplash(): void {
	if (released) return;
	released = true;
	window.setTimeout(finishSplash, MAX_DISPLAY_MS);
}

/** 应用就绪后调用（幂等）：满最短展示时长后触发收場 */
export function finishSplash(): void {
	if (finished || !released) return;
	finished = true;
	markPlayed();
	const setup = document.documentElement.dataset.startupView === "setup";
	const wait = setup || skipAnimation ? 0 : Math.max(0, MIN_DISPLAY_MS - performance.now());
	window.setTimeout(() => {
		exitListener?.();
		exitListener = undefined;
		const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
		const exitMs =
			setup || skipAnimation || reduced ? EXIT_MS_REDUCED : (animateSplashExit() ?? SPLASH_EXIT_MS);
		document.documentElement.dataset.appReady = "true";
		window.setTimeout(removeSplash, exitMs);
	}, wait);
}
