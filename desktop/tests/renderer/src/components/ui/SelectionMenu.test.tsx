// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it } from "vitest";
import { Select } from "../../../../../src/renderer/src/components/ui/Select";

it("keeps a picker open during background chat scroll and closes when its own anchor moves", async () => {
	const host = document.createElement("div");
	const background = document.createElement("div");
	document.body.append(host, background);
	const root = createRoot(host);
	try {
		await act(() =>
			root.render(<Select value="one" options={[{ value: "one", label: "One" }]} onChange={() => {}} />),
		);
		await act(() => host.querySelector<HTMLButtonElement>("button")?.click());
		expect(document.querySelector('[role="listbox"]')).not.toBeNull();
		await act(() => background.dispatchEvent(new Event("scroll")));
		expect(document.querySelector('[role="listbox"]')).not.toBeNull();
		await act(() => host.dispatchEvent(new Event("scroll")));
		expect(document.querySelector('[role="listbox"]')).toBeNull();
	} finally {
		await act(() => root.unmount());
		host.remove();
		background.remove();
	}
});
