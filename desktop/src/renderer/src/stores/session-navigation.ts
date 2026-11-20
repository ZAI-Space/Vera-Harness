/** Process-local activation and user intent answer different questions; neither lives in a store. */
let activationSeq = 0;
let userIntentSeq = 0;
const userIntentListeners = new Set<() => void>();

/** Claim before any await; earlier navigation may land data but cannot commit focus. */
export function claimActivation(): number {
	return ++activationSeq;
}

/** Already on the draft page, '+' records user intent without invalidating promotion. */
export function noteUserIntent(): void {
	userIntentSeq += 1;
	for (const listener of userIntentListeners) listener();
}

/** UI 在自己的生命周期订阅导航意图，保持此模块不依赖 store 或 React。 */
export function onSessionNavigationIntent(listener: () => void): () => void {
	userIntentListeners.add(listener);
	return () => {
		userIntentListeners.delete(listener);
	};
}

export function currentNavigationToken(): number {
	return activationSeq;
}
export function isLatestNavigation(token: number): boolean {
	return token === activationSeq;
}
export const isLatestActivation = isLatestNavigation;

export function currentUserIntentToken(): number {
	return userIntentSeq;
}
export function isLatestUserIntent(token: number): boolean {
	return token === userIntentSeq;
}
