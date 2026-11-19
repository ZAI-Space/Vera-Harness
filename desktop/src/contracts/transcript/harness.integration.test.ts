import { execFile } from "node:child_process";
import { resolve } from "node:path";
import { promisify } from "node:util";
import { expect, it } from "vitest";
import type { SessionEvent } from "../session";
import { reduceEvent } from "./reducer";
import { emptyTranscript } from "./types";

/** Cross-language acceptance: consume events produced by a real Python worker. */
it("renders actual runtime text, reasoning, tool results and completion without duplicate output", async () => {
	const root = resolve(process.cwd(), "..");
	const python =
		process.env.VERA_PYTHON ??
		resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
	const { stdout } = await promisify(execFile)(python, [resolve(root, "scripts/desktop_contract_trace.py")], {
		cwd: root,
		env: { ...process.env, VERA_SILENT_STARTUP: "1", PYTHONUTF8: "1" },
		timeout: 45000,
		maxBuffer: 2_000_000,
	});
	const trace = JSON.parse(stdout) as { events: SessionEvent[]; output: string };
	let state = emptyTranscript();
	for (const event of trace.events) state = reduceEvent(state, event);
	expect(trace.output).toBe("contract-ok");
	expect(state.agentActive).toBe(false);
	expect(state.streaming).toBeNull();
	expect(state.messages.filter((row) => row.kind === "user")).toHaveLength(1);
	expect(
		state.messages.some(
			(row) => row.kind === "assistant" && row.thinking.includes("Visible provider reasoning"),
		),
	).toBe(true);
	expect(state.messages.some((row) => row.kind === "assistant" && row.text.includes("contract-ok"))).toBe(
		true,
	);
	expect(
		state.messages
			.flatMap((row) => (row.kind === "assistant" ? row.tools : []))
			.filter((tool) => tool.state === "done"),
	).toHaveLength(2);
}, 60000);
