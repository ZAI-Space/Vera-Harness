import { environmentEntityKey, type TaskNotificationClick } from "@vera/contracts";
import { getDesktopApi } from "../api";
import { currentUserIntentToken } from "./session-navigation";
import { useSessionsStore } from "./sessions";
import { pushToast } from "./toasts";

/** Installed after workbench bootstrap, never gated by a particular session's history ACK. */
export function initTaskNotificationNavigation() {
	const intentAtReady = currentUserIntentToken();
	let disposed = false;
	let attempt = 0;
	const open = async ({ target, queued }: TaskNotificationClick) => {
		const ownAttempt = ++attempt;
		const intent = currentUserIntentToken();
		if (queued && currentUserIntentToken() !== intentAtReady) return;
		if (target?.environment.kind !== "local") {
			pushToast("warning", "notifications.targetUnavailable");
			return;
		}
		const id = environmentEntityKey(target.environment, target.sessionId);
		let started = false;
		const current = () =>
			!disposed && ownAttempt === attempt && (started || intent === currentUserIntentToken());
		if (!current()) return;
		if (useSessionsStore.getState().sessions.some((meta) => meta.sessionId === id)) {
			useSessionsStore.getState().switchSession(id);
			return;
		}
		if (!target.sessionFile) {
			pushToast("warning", "notifications.targetUnavailable");
			return;
		}
		started = true;
		const result = await useSessionsStore
			.getState()
			.openFromHistory(
				environmentEntityKey(target.environment, target.sessionFile),
				(meta) => current() && meta.sessionId === id,
			);
		if (result.ok && result.meta.sessionId !== id && current())
			pushToast("warning", "notifications.targetUnavailable");
	};
	const unsubscribe = getDesktopApi().onTaskNotificationClick((click) => {
		void open(click).catch(() => {
			if (!disposed) pushToast("warning", "notifications.targetUnavailable");
		});
	});
	void getDesktopApi()
		.setTaskNotificationNavigationReady({ ready: true })
		.catch(() => {});
	return () => {
		disposed = true;
		attempt++;
		unsubscribe();
		void getDesktopApi()
			.setTaskNotificationNavigationReady({ ready: false })
			.catch(() => {});
	};
}
