// @vitest-environment happy-dom
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { ConfirmDialog } from "../../../../../src/renderer/src/components/ui/ConfirmDialog";
import { Modal } from "../../../../../src/renderer/src/components/ui/Modal";

vi.mock("../../../../../src/renderer/src/i18n", () => ({ useT: () => (key: string) => key }));

it("IME Escape preserves the dialog, ordinary Escape closes only it, and links remain inside the focus trap", async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	const host = document.createElement("div");
	document.body.append(host);
	const root = createRoot(host);
	const close = vi.fn();
	const background = vi.fn();
	window.addEventListener("keydown", background);
	try {
		await act(() =>
			root.render(
				<Modal title="dialog" onClose={close}>
					<a href="#help">help</a>
				</Modal>,
			),
		);
		const link = document.querySelector<HTMLAnchorElement>('a[href="#help"]');
		if (!link) throw new Error("Missing link");
		link.focus();
		link.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
		expect(document.activeElement?.getAttribute("aria-label")).toBe("common.close");
		window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", isComposing: true }));
		expect(close).not.toHaveBeenCalled();
		background.mockClear();
		window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
		expect(close).toHaveBeenCalledOnce();
		expect(background).not.toHaveBeenCalled();
	} finally {
		window.removeEventListener("keydown", background);
		await act(() => root.unmount());
		host.remove();
		vi.unstubAllGlobals();
	}
});

it("nested confirmation traps both Tab boundaries, defaults to cancel and restores focus to its parent", async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	const host = document.createElement("div");
	document.body.append(host);
	const root = createRoot(host);
	function Nested() {
		const [confirming, setConfirming] = useState(false);
		return (
			<Modal title="detail" onClose={() => {}}>
				<button type="button" onClick={() => setConfirming(true)}>
					install
				</button>
				{confirming && (
					<ConfirmDialog
						title="confirm install"
						description="Confirm"
						confirmLabel="confirm"
						cancelLabel="cancel"
						onConfirm={() => {}}
						onCancel={() => setConfirming(false)}
					/>
				)}
			</Modal>
		);
	}
	try {
		await act(() => root.render(<Nested />));
		const opener = [...document.querySelectorAll("button")].find((item) => item.textContent === "install");
		if (!opener) throw new Error("Missing opener");
		opener.focus();
		await act(() => opener.click());
		const confirmation = document.querySelector('[aria-label="confirm install"]');
		if (!confirmation) throw new Error("Missing confirmation");
		expect(document.activeElement?.textContent).toBe("cancel");
		const buttons = [...confirmation.querySelectorAll("button")];
		const first = buttons[0],
			last = buttons.at(-1);
		last?.focus();
		window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", cancelable: true }));
		expect(document.activeElement).toBe(first);
		window.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, cancelable: true }));
		expect(document.activeElement).toBe(last);
		await act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
		expect(document.querySelector('[aria-label="confirm install"]')).toBeNull();
		expect(document.querySelector('[aria-label="detail"]')).not.toBeNull();
		expect(document.activeElement).toBe(opener);
	} finally {
		await act(() => root.unmount());
		host.remove();
		vi.unstubAllGlobals();
	}
});
