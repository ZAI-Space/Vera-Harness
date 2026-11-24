import { beforeEach, expect, it, vi } from "vitest";
import { usePermissionPolicyStore } from "../../../../src/renderer/src/stores/permission-policy";

const fixture = vi.hoisted(() => ({ request: vi.fn(), report: vi.fn() }));
vi.mock("../../../../src/renderer/src/harness-api", () => ({
	harness: fixture.request,
	isHarnessConnected: () => true,
	reportHarnessFailure: fixture.report,
}));

beforeEach(() => {
	fixture.request.mockReset();
	fixture.report.mockReset().mockResolvedValue(undefined);
	usePermissionPolicyStore.setState({ byTarget: {} });
});

it("failed queued writes restore the last confirmed policy rather than another optimistic value", async () => {
	fixture.request.mockResolvedValueOnce({ permissionPolicy: "human" });
	await usePermissionPolicyStore.getState().loadPolicy("confirmed");
	fixture.request.mockRejectedValue(new Error("offline"));
	const first = usePermissionPolicyStore.getState().savePolicy("confirmed", "yolo");
	const second = usePermissionPolicyStore.getState().savePolicy("confirmed", "confirm");
	expect(await first).toBe(false);
	expect(await second).toBe(false);
	expect(usePermissionPolicyStore.getState().byTarget.confirmed).toBe("human");
});

it("failed writes without a confirmed policy leave the fallback choice unset", async () => {
	fixture.request.mockRejectedValue(new Error("offline"));
	expect(await usePermissionPolicyStore.getState().savePolicy("unknown", "yolo")).toBe(false);
	expect(usePermissionPolicyStore.getState().byTarget.unknown).toBeUndefined();
});
