import { afterEach, expect, it } from "vitest";
import {
	claimActivation,
	currentUserIntentToken,
	isLatestActivation,
	noteUserIntent,
} from "./session-navigation";
import { initWorkspaceNavigation, navigateWorkspacePage, useWorkspacePageStore } from "./workspace-page";

afterEach(() => useWorkspacePageStore.setState({ page: "chat" }));

it("opening a workspace page cancels an older session activation and returning does not need a different session id", () => {
	const stop = initWorkspaceNavigation();
	try {
		const oldActivation = claimActivation();
		const previousIntent = currentUserIntentToken();
		navigateWorkspacePage("plugins");
		expect(useWorkspacePageStore.getState().page).toBe("plugins");
		expect(isLatestActivation(oldActivation)).toBe(false);
		expect(currentUserIntentToken()).toBeGreaterThan(previousIntent);
		noteUserIntent();
		expect(useWorkspacePageStore.getState().page).toBe("chat");
		navigateWorkspacePage("scheduled");
		expect(useWorkspacePageStore.getState().page).toBe("scheduled");
	} finally {
		stop();
	}
});

it("navigation subscriptions are released on root unmount", () => {
	const stop = initWorkspaceNavigation();
	stop();
	stop();
	navigateWorkspacePage("scheduled");
	noteUserIntent();
	expect(useWorkspacePageStore.getState().page).toBe("scheduled");
});
