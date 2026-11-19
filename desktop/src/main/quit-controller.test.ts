import { afterEach, describe, expect, it, vi } from "vitest";
import { QuitController } from "./quit-controller";

afterEach(() => vi.useRealTimers());
describe("desktop quit confirmation", () => {
	it("keeps the window open after the dialog acknowledges, then exits on confirmation", () => {
		vi.useFakeTimers();
		const request = vi.fn(),
			exit = vi.fn();
		const controller = new QuitController(request, exit);
		expect(controller.canClose()).toBe(true);
		controller.setEnabled(true);
		expect(controller.canClose()).toBe(false);
		expect(request).toHaveBeenCalledOnce();
		controller.acknowledge();
		vi.advanceTimersByTime(2000);
		expect(exit).not.toHaveBeenCalled();
		controller.confirm();
		expect(exit).toHaveBeenCalledOnce();
		expect(controller.canClose()).toBe(true);
	});
	it("falls back to exit if the renderer cannot acknowledge", () => {
		vi.useFakeTimers();
		const exit = vi.fn();
		const controller = new QuitController(vi.fn(), exit);
		controller.setEnabled(true);
		controller.canClose();
		vi.advanceTimersByTime(1500);
		expect(exit).toHaveBeenCalledOnce();
	});
});
