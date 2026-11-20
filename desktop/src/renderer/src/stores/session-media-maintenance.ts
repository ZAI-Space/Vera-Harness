import type { SessionMeta } from "@vera/contracts";
import { create } from "zustand";

export const useSessionMediaMaintenanceStore = create<{
	session: SessionMeta | null;
	open: (session: SessionMeta) => void;
	close: () => void;
}>((set) => ({ session: null, open: (session) => set({ session }), close: () => set({ session: null }) }));
