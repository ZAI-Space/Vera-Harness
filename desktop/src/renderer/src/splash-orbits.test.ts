// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { animateSplashExit, buildSplashOrbits, LEGACY_SCATTER_MS, SPLASH_EXIT_MS } from "./splash-orbits";

afterEach(() => {
	document.body.innerHTML = "";
	vi.restoreAllMocks();
});

function required<Value>(value: Value | undefined): Value {
	if (value === undefined) throw new Error("Missing orbit fixture value");
	return value;
}

type CapturedAnimation = { target: HTMLElement; frames: Keyframe[]; options: KeyframeAnimationOptions };

/** 以可控的图标位置和已经旋转的球位检查动画接管，不依赖 happy-dom 布局。 */
function setupExitFixture(): CapturedAnimation[] {
	document.body.innerHTML = `<div id="splash"><div class="sp-swarm">${buildSplashOrbits()}</div><div class="sp-wave"></div><div class="sp-wave"></div><img class="sp-word" alt="VERA" /></div>`;
	const swarm = document.querySelector<HTMLElement>(".sp-swarm");
	const logo = document.querySelector<HTMLImageElement>(".sp-word");
	if (!swarm || !logo) throw new Error("Missing splash fixture");
	vi.spyOn(swarm, "getBoundingClientRect").mockReturnValue(new DOMRect(100, 100, 420, 420));
	vi.spyOn(logo, "getBoundingClientRect").mockReturnValue(new DOMRect(226, 270, 168, 80));
	for (const wave of document.querySelectorAll<HTMLElement>(".sp-wave"))
		vi.spyOn(wave, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 220, 220));
	for (const dot of document.querySelectorAll<HTMLElement>(".sp-dot")) {
		dot.style.width = "10px";
		vi.spyOn(dot, "getBoundingClientRect").mockReturnValue(new DOMRect(403, 303, 14, 14));
	}
	const captured: CapturedAnimation[] = [];
	vi.spyOn(HTMLElement.prototype, "animate").mockImplementation(function (
		this: HTMLElement,
		frames,
		options,
	) {
		captured.push({
			target: this,
			frames: frames as Keyframe[],
			options: options as KeyframeAnimationOptions,
		});
		return {} as Animation;
	});
	return captured;
}

describe("splash orbit handoff", () => {
	it("keeps dense staggered rings, a clear center and the shared four-color palette", () => {
		document.body.innerHTML = buildSplashOrbits();
		const radii: number[] = [];
		const sizes: number[] = [];
		for (const ring of document.querySelectorAll<HTMLElement>(".sp-orbit")) {
			const dots = [...ring.querySelectorAll<HTMLElement>(".sp-dot")];
			const positions = dots.map(
				(dot) =>
					[
						Number.parseFloat(dot.style.getPropertyValue("--x")),
						Number.parseFloat(dot.style.getPropertyValue("--y")),
					] as const,
			);
			const first = required(positions[0]),
				second = required(positions[1]);
			const radius = Math.hypot(...first);
			radii.push(radius);
			sizes.push(Number.parseFloat(required(dots[0]).style.getPropertyValue("--size")));
			const spacing = Math.hypot(second[0] - first[0], second[1] - first[1]);
			const size = required(sizes.at(-1));
			expect(spacing).toBeGreaterThan(size * 1.1);
			expect(spacing).toBeLessThan(size * 1.5);
			for (let index = 0; index < dots.length; index++) {
				const current = required(positions[index]),
					next = required(positions[(index + 1) % dots.length]);
				expect(Math.hypot(...current)).toBeCloseTo(radius, 3);
				expect(Math.hypot(next[0] - current[0], next[1] - current[1])).toBeCloseTo(spacing, 3);
				expect(required(dots[index]).style.getPropertyValue("--sp-dot-color")).toContain("color-mix");
			}
		}
		expect(radii).toHaveLength(3);
		expect(required(radii[0])).toBeGreaterThan(30);
		expect(required(radii[0])).toBeLessThan(required(radii[1]));
		expect(required(radii[1])).toBeLessThan(required(radii[2]));
		expect(required(sizes[0])).toBeLessThan(required(sizes[1]));
		expect(required(sizes[1])).toBeLessThan(required(sizes[2]));
	});

	it("shrinks throughout the approach and reaches zero size on the actual opaque PNG boundary", () => {
		const captured = setupExitFixture();
		const logo = document.querySelector<HTMLImageElement>(".sp-word");
		if (!logo) throw new Error("Missing logo");
		Object.defineProperties(logo, {
			complete: { value: true },
			naturalWidth: { value: 4 },
			naturalHeight: { value: 4 },
		});
		// 图中只有一个可见像素，故目标必须落到该像素，不能以图像矩形或椭圆替代。
		const pixels = new Uint8ClampedArray(4 * 4 * 4);
		pixels[(1 * 4 + 3) * 4 + 3] = 255;
		const context = { drawImage: vi.fn(), getImageData: () => ({ data: pixels }) };
		vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
			context as unknown as CanvasRenderingContext2D,
		);
		animateSplashExit();
		const originals = captured.filter((animation) => animation.target.matches(".sp-orbit .sp-dot"));
		expect(originals).toHaveLength(120);
		const animation = required(originals[0]);
		expect(required(animation.frames[0]).transform).toBe("translate3d(95px, -5px, 0) scale(1)");
		expect(animation.frames.at(-1)?.transform).toBe("translate3d(58px, -15px, 0) scale(0)");
		expect(animation.frames.at(-1)?.opacity).toBe(0);
		expect(animation.target.style.width).toBe("10px");
		expect(animation.options.easing).toBe("cubic-bezier(.65,0,.82,.35)");
		const scales = animation.frames.map((frame) =>
			Number(String(frame.transform).match(/scale\(([\d.]+)\)/)?.[1]),
		);
		for (let index = 1; index < scales.length; index++) {
			expect(required(scales[index])).toBeLessThan(required(scales[index - 1]));
		}
		expect(required(scales[1])).toBeLessThan(0.5);
		expect(Number(animation.options.duration)).toBeLessThan(SPLASH_EXIT_MS);
		expect(captured.some((animation) => animation.target === logo)).toBe(false);
	});

	it("starts the original 64-particle scatter after absorption and retains its full 2400 ms exit", () => {
		const captured = setupExitFixture();
		const duration = animateSplashExit();
		const originals = captured.filter((animation) => animation.target.matches(".sp-orbit .sp-dot"));
		const particles = [...document.querySelectorAll<HTMLElement>(".sp-burst-dot")];
		expect(originals).toHaveLength(120);
		expect(particles).toHaveLength(64);
		const burstAt = Number.parseFloat(document.documentElement.style.getPropertyValue("--sp-scatter-delay"));
		const absorbed = originals.filter((animation) => Number(animation.options.duration) <= burstAt);
		expect(absorbed.length / originals.length).toBeGreaterThanOrEqual(0.96);
		expect(duration).toBe(burstAt + LEGACY_SCATTER_MS);
		expect(LEGACY_SCATTER_MS).toBe(2400);
		for (const particle of particles) {
			const radius = Math.hypot(
				Number.parseFloat(particle.style.getPropertyValue("--x")),
				Number.parseFloat(particle.style.getPropertyValue("--y")),
			);
			expect(radius).toBeLessThan(107);
			expect(Number.parseFloat(particle.style.getPropertyValue("--s"))).toBeLessThan(15);
			expect(particle.style.getPropertyValue("--sp-dot-color")).toContain("color-mix");
		}
		expect(document.getElementById("splash")?.classList.contains("sp-exiting")).toBe(true);
	});
});
