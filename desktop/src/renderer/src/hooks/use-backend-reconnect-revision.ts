import { useEffect, useState } from "react";
import { getDesktopApi } from "../api";

/** Invalidate backend-derived views on reconnect; unsubscribe when inactive or unmounted. */
export function useBackendReconnectRevision(enabled = true): number {
	const [revision, setRevision] = useState(0);
	useEffect(() => {
		if (!enabled) return;
		return getDesktopApi().onBackendStatusChanged(({ connected }) => {
			if (connected) setRevision((value) => value + 1);
		});
	}, [enabled]);
	return revision;
}
