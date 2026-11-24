// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it } from "vitest";
import {
	DeferredDetails,
	SessionViewContext,
} from "../../../../../src/renderer/src/components/ui/DeferredDetails";
import { useSessionViewStore } from "../../../../../src/renderer/src/stores/session-view";

let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
let previousActEnvironment: unknown;

beforeEach(() => {
	previousActEnvironment = Reflect.get(globalThis, "IS_REACT_ACT_ENVIRONMENT");
	Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", true);
	useSessionViewStore.setState({ bySession: {} });
	container = document.createElement("div");
	document.body.append(container);
	root = createRoot(container);
});

afterEach(async () => {
	await act(() => root.unmount());
	container.remove();
	useSessionViewStore.setState({ bySession: {} });
	if (previousActEnvironment === undefined) Reflect.deleteProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT");
	else Reflect.set(globalThis, "IS_REACT_ACT_ENVIRONMENT", previousActEnvironment);
});

async function render(live: boolean, sessionId: string | null) {
	if (sessionId) useSessionViewStore.getState().ensure(sessionId);
	await act(() =>
		root.render(
			<SessionViewContext.Provider value={sessionId}>
				<DeferredDetails viewKey="reasoning" summary="Reasoning" defaultOpen={live} followDefault>
					<p>Visible provider reasoning</p>
				</DeferredDetails>
			</SessionViewContext.Provider>,
		),
	);
}

async function toggle() {
	const summary = container.querySelector("summary");
	if (!summary) throw new Error("Missing reasoning disclosure");
	await act(() => summary.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
}

// Value: protects=live reasoning follows defaults until a reader chooses, independently per session;
// fails_when=automatic folding overwrites a choice or a choice in one session disables folding in another;
// why_new=existing disclosure tests never enabled followDefault; seam=none;
// no_claim=provider reasoning quality or native Electron layout.
it.each([null, "first-session"])(
	"follows live state and preserves reader choices with session %s",
	async (sessionId) => {
		await render(true, sessionId);
		expect(container.querySelector("details")?.open).toBe(true);
		await render(false, sessionId);
		expect(container.querySelector("details")?.open).toBe(false);
		if (sessionId)
			expect(useSessionViewStore.getState().bySession[sessionId]?.details.reasoning).toBeUndefined();
		await render(true, sessionId);
		expect(container.querySelector("details")?.open).toBe(true);
		await toggle();
		await render(false, sessionId);
		await render(true, sessionId);
		expect(container.querySelector("details")?.open).toBe(false);
		await toggle();
		await render(false, sessionId);
		expect(container.querySelector("details")?.open).toBe(true);
		if (sessionId) {
			await render(true, "second-session");
			expect(container.querySelector("details")?.open).toBe(true);
			await render(false, "second-session");
			expect(container.querySelector("details")?.open).toBe(false);
			await render(false, sessionId);
			expect(container.querySelector("details")?.open).toBe(true);
			await act(() => root.render(null));
			await render(false, sessionId);
			expect(container.querySelector("details")?.open).toBe(true);
		}
	},
);
