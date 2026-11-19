/**
 * 三圈彩球待机旋转；真实就绪后加速内聚并随接近距离连续缩小，在 Logo 边缘归零。
 * 大部分小球吸收完成后，独立的彩色粒子与双环接管迸发散场。
 */
/** 原版后半段完整时长，包含双环散场和工作台淡入。 */
export const LEGACY_SCATTER_MS = 2400;
/** 加上最长吸收时间的清理上限；实际收场返回准确时长。 */
export const SPLASH_EXIT_MS = 3060;
const ORBITS = [
	{ radius: 135, count: 44, size: 15, offset: 0 },
	{ radius: 161, count: 40, size: 20, offset: 4.5 },
	{ radius: 187, count: 36, size: 25, offset: 5 },
];
type Point = { x: number; y: number };

function dotColor(turn: number): string {
	const colorTurn = ((turn % 1) + 1) % 1;
	const firstColor = Math.floor(colorTurn * 4);
	const weight = ((1 - (colorTurn * 4 - firstColor)) * 100).toFixed(2);
	return `color-mix(in srgb, var(--sp-color-${firstColor}) ${weight}%, var(--sp-color-${(firstColor + 1) % 4}))`;
}

/** 以 420px 为基准生成百分比坐标；球径、间距随窗口一起缩放。 */
export function buildSplashOrbits(): string {
	return ORBITS.map((orbit, ring) => {
		const dots = Array.from({ length: orbit.count }, (_, index) => {
			const turn = index / orbit.count;
			const angle = (turn * 360 + orbit.offset - 90) * (Math.PI / 180);
			const x = ((Math.cos(angle) * orbit.radius) / 420) * 100;
			const y = ((Math.sin(angle) * orbit.radius) / 420) * 100;
			const size = (orbit.size / 420) * 100;
			const color = dotColor(turn + orbit.offset / 360);
			return `<i class="sp-dot" style="--x:${x.toFixed(4)}%;--y:${y.toFixed(4)}%;--size:${size.toFixed(4)}%;--sp-dot-color:${color}"></i>`;
		}).join("");
		return `<div class="sp-orbit" data-ring="${ring}">${dots}</div>`;
	}).join("");
}

/** 原版 64 粒子黄金角布局、球径、透明度和飞出距离原样保留，仅改变颜色。 */
function buildLegacyScatter(): string {
	let html = "";
	for (let index = 1; index <= 64; index++) {
		const radius = 13.2 * Math.sqrt(index);
		const angle = index * 137.508 * (Math.PI / 180);
		const x = Math.round(radius * Math.cos(angle)),
			y = Math.round(radius * Math.sin(angle));
		const size = Math.max(3, 13.5 - radius * 0.1 + ((index * 7) % 3) - 1);
		const opacity = Math.min(1, Math.max(0.35, 1.02 - radius * 0.0065));
		const exitX = Math.round(x * 3 + Math.cos(angle) * 1100);
		const exitY = Math.round(y * 3 + Math.sin(angle) * 1100);
		html += `<i class="sp-burst-dot" style="--x:${x}px;--y:${y}px;--ex:${exitX}px;--ey:${exitY}px;--s:${size.toFixed(1)}px;--o:${opacity.toFixed(2)};--sp-dot-color:${dotColor(angle / (Math.PI * 2) + 0.25)}"></i>`;
	}
	return `<div class="sp-legacy-swarm"><div class="sp-legacy-in"><div class="sp-legacy-breathe">${html}</div></div></div>`;
}

/** 一次读取 PNG 的可见边界，坐标相对整个动效中心，不使用椭圆或统一停靠圈。 */
function readLogoOutline(image: HTMLImageElement, bounds: DOMRect, center: Point): Point[] {
	if (!image.complete || !image.naturalWidth) return [];
	try {
		const canvas = document.createElement("canvas");
		canvas.width = image.naturalWidth;
		canvas.height = image.naturalHeight;
		const context = canvas.getContext("2d");
		if (!context) return [];
		context.drawImage(image, 0, 0);
		const { data: pixels } = context.getImageData(0, 0, canvas.width, canvas.height);
		const isOpaque = (x: number, y: number) =>
			x >= 0 &&
			x < canvas.width &&
			y >= 0 &&
			y < canvas.height &&
			(pixels[(y * canvas.width + x) * 4 + 3] ?? 0) > 32;
		const outline: Point[] = [];
		for (let y = 0; y < canvas.height; y++)
			for (let x = 0; x < canvas.width; x++) {
				if (!isOpaque(x, y)) continue;
				if (isOpaque(x - 1, y) && isOpaque(x + 1, y) && isOpaque(x, y - 1) && isOpaque(x, y + 1)) continue;
				outline.push({
					x: bounds.left + ((x + 0.5) / canvas.width) * bounds.width - center.x,
					y: bounds.top + ((y + 0.5) / canvas.height) * bounds.height - center.y,
				});
			}
		return outline;
	} catch {
		// 品牌图读取失败时改用图像边框，仍完成吸收与散场，不阻塞工作台。
		return [];
	}
}

/** 选择离小球最近的可见边界，让从透明断层方向接近的球也能落到真实图形上。 */
function nearestLogoPoint(origin: Point, outline: Point[], bounds: DOMRect, center: Point): Point {
	let closest: Point = {
		x: Math.max(bounds.left, Math.min(bounds.right, origin.x + center.x)) - center.x,
		y: Math.max(bounds.top, Math.min(bounds.bottom, origin.y + center.y)) - center.y,
	};
	let nearest = Infinity;
	for (const point of outline) {
		const distance = (point.x - origin.x) ** 2 + (point.y - origin.y) ** 2;
		if (distance < nearest) {
			closest = point;
			nearest = distance;
		}
	}
	return closest;
}

/**
 * 仅在工作台真正就绪后调用一次。冻结当前球位，按距离决定到达时刻，
 * 小球在整个靠近过程中连续缩小，抵达原 PNG 边缘时完全消失；96% 吸收完毕再开始迸发。
 * Canvas 不可用时回退到图像边框。不修改加载状态；返回吸收和原版散场的总时长。
 */
export function animateSplashExit(): number {
	const host = document.getElementById("splash");
	const swarm = host?.querySelector<HTMLElement>(".sp-swarm");
	const logo = host?.querySelector<HTMLImageElement>(".sp-word");
	if (!host || !swarm || !logo) return LEGACY_SCATTER_MS;
	const bounds = swarm.getBoundingClientRect();
	const center = { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 };
	const layoutScale = Math.max(bounds.width / 420, 0.1);
	const logoBounds = logo.getBoundingClientRect();
	const outline = readLogoOutline(logo, logoBounds, center);
	const dots = Array.from(swarm.querySelectorAll<HTMLElement>(".sp-orbit .sp-dot"), (dot) => {
		const bounds = dot.getBoundingClientRect();
		const origin = {
			x: bounds.left + bounds.width / 2 - center.x,
			y: bounds.top + bounds.height / 2 - center.y,
		};
		const target = nearestLogoPoint(origin, outline, logoBounds, center);
		const distance = Math.hypot(target.x - origin.x, target.y - origin.y);
		// 同一加速趋势，远处的球稍晚抵达，球径随剩余距离缩小。
		const duration = Math.round(300 + Math.sqrt(distance / layoutScale) * 22);
		return {
			dot,
			origin,
			target,
			duration: Math.min(640, duration),
			size: Number.parseFloat(getComputedStyle(dot).width),
		};
	});
	const arrivals = dots.map((dot) => dot.duration).sort((first, second) => first - second);
	const burstAt = Math.min(660, (arrivals[Math.floor((arrivals.length - 1) * 0.96)] ?? 560) + 18);
	for (const orbit of swarm.querySelectorAll<HTMLElement>(".sp-orbit")) orbit.style.animation = "none";
	for (const { dot, origin, target, duration, size } of dots) {
		const translate = (point: Point, scale = 1) =>
			`translate3d(${point.x - size / 2}px, ${point.y - size / 2}px, 0) scale(${scale})`;
		const position = (progress: number): Point => ({
			x: origin.x + (target.x - origin.x) * progress,
			y: origin.y + (target.y - origin.y) * progress,
		});
		dot.style.left = "50%";
		dot.style.top = "50%";
		dot.style.width = `${size}px`;
		dot.style.height = `${size}px`;
		dot.animate(
			[
				{ transform: translate(origin), opacity: 1, offset: 0 },
				{ transform: translate(position(0.6), 0.4), opacity: 1, offset: 0.6 },
				{ transform: translate(position(0.9), 0.1), opacity: 1, offset: 0.9 },
				{ transform: translate(target, 0), opacity: 0, offset: 1 },
			],
			{ duration, easing: "cubic-bezier(.65,0,.82,.35)", fill: "forwards" },
		);
	}
	const burst = document.createElement("div");
	burst.className = "sp-burst";
	burst.setAttribute("aria-hidden", "true");
	burst.innerHTML = buildLegacyScatter();
	swarm.append(burst);
	document.documentElement.style.setProperty("--sp-scatter-delay", `${burstAt}ms`);
	host.classList.add("sp-exiting");
	return burstAt + LEGACY_SCATTER_MS;
}
