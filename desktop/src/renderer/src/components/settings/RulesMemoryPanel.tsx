import { useCallback, useEffect, useState } from "react";
import { harness } from "../../harness-api";
import { useT } from "../../i18n";
import { errText } from "../../lib/error-text";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Modal } from "../ui/Modal";
import { Switch } from "../ui/Switch";

interface ContextEntry {
	id?: string;
	kind: "rule" | "memory";
	title: string;
	content: string;
	enabled: boolean;
	updatedAt?: string;
}

/** User-authored global instructions. Every mutation is acknowledged before the visible list changes. */
export function RulesMemoryPanel() {
	const t = useT();
	const [entries, setEntries] = useState<ContextEntry[]>([]);
	const [kind, setKind] = useState<ContextEntry["kind"]>("rule");
	const [editor, setEditor] = useState<ContextEntry | null>(null);
	const [removing, setRemoving] = useState<ContextEntry | null>(null);
	const [busy, setBusy] = useState(false);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [removeError, setRemoveError] = useState<string | null>(null);
	const load = useCallback(async () => {
		setLoading(true);
		try {
			const result = await harness<{ entries: ContextEntry[] }>("getUserContext");
			setEntries(result.entries);
			setError(null);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setLoading(false);
		}
	}, []);
	useEffect(() => {
		void load();
	}, [load]);
	const save = async (entry: ContextEntry) => {
		setBusy(true);
		setError(null);
		try {
			await harness("saveUserContextEntry", { entry });
			await load();
			setEditor(null);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	return (
		<section className="flex flex-col gap-4" aria-label={t("rulesMemory.title")}>
			<p className="text-ui-12 leading-relaxed text-ink-dim">{t("rulesMemory.hint")}</p>
			<div className="flex flex-wrap items-center justify-between gap-3">
				<div className="flex rounded-lg bg-hover p-1" role="tablist" aria-label={t("rulesMemory.title")}>
					{(["rule", "memory"] as const).map((item) => (
						<button
							key={item}
							type="button"
							role="tab"
							aria-selected={kind === item}
							onClick={() => setKind(item)}
							className={`rounded-md px-3 py-2 text-ui-12 ${kind === item ? "bg-surface text-ink shadow-soft" : "text-ink-dim"}`}
						>
							{t(item === "rule" ? "rulesMemory.rules" : "rulesMemory.memories")}
						</button>
					))}
				</div>
				<Button disabled={busy} onClick={() => setEditor({ kind, title: "", content: "", enabled: true })}>
					{t(kind === "rule" ? "rulesMemory.addRule" : "rulesMemory.addMemory")}
				</Button>
			</div>
			<p className="text-ui-11 text-ink-faint">
				{t(kind === "rule" ? "rulesMemory.ruleHint" : "rulesMemory.memoryHint")}
			</p>
			{error && (
				<div role="alert" className="text-ui-12 text-err">
					{error}
					<Button onClick={() => void load()}>{t("rulesMemory.retry")}</Button>
				</div>
			)}
			{loading ? (
				<p role="status" className="py-8 text-center text-ui-12 text-ink-faint">
					{t("rulesMemory.loading")}
				</p>
			) : entries.filter((entry) => entry.kind === kind).length === 0 ? (
				<p className="py-10 text-center text-ui-13 text-ink-faint">{t("rulesMemory.empty")}</p>
			) : (
				entries
					.filter((entry) => entry.kind === kind)
					.map((entry) => (
						<article key={entry.id} className="rounded-xl border border-border p-4">
							<div className="flex items-start justify-between gap-4">
								<div className="min-w-0">
									<h3 className="break-words text-ui-13 font-medium text-ink">{entry.title}</h3>
									<p className="mt-1 text-ui-11 text-ink-faint">{t("rulesMemory.scope")}</p>
								</div>
								<Switch
									aria-label={t("rulesMemory.enabled", { name: entry.title })}
									checked={entry.enabled}
									disabled={busy}
									onCheckedChange={(enabled) => void save({ ...entry, enabled })}
								/>
							</div>
							<p className="mt-3 line-clamp-3 whitespace-pre-wrap break-words text-ui-12 leading-relaxed text-ink-dim">
								{entry.content}
							</p>
							<div className="mt-3 flex justify-end gap-2">
								<Button disabled={busy} onClick={() => setEditor({ ...entry })}>
									{t("rulesMemory.edit")}
								</Button>
								<Button
									disabled={busy}
									onClick={() => {
										setRemoveError(null);
										setRemoving(entry);
									}}
								>
									{t("rulesMemory.remove")}
								</Button>
							</div>
						</article>
					))
			)}
			{editor && (
				<Modal
					title={t(
						editor.id
							? "rulesMemory.edit"
							: editor.kind === "rule"
								? "rulesMemory.addRule"
								: "rulesMemory.addMemory",
					)}
					onClose={() => {
						if (!busy) setEditor(null);
					}}
				>
					<form
						className="flex flex-col gap-4"
						onSubmit={(event) => {
							event.preventDefault();
							void save(editor);
						}}
					>
						<label className="flex flex-col gap-2 text-ui-12 text-ink-dim">
							{t("rulesMemory.titleField")}
							<input
								required
								maxLength={128}
								className="rounded-lg border border-border bg-canvas px-3 py-2 text-ink"
								value={editor.title}
								onChange={(event) => setEditor({ ...editor, title: event.target.value })}
							/>
						</label>
						<label className="flex flex-col gap-2 text-ui-12 text-ink-dim">
							{t("rulesMemory.content")}
							<textarea
								required
								maxLength={16000}
								rows={12}
								className="resize-y rounded-lg border border-border bg-canvas p-3 font-mono text-ui-12 leading-relaxed text-ink"
								value={editor.content}
								onChange={(event) => setEditor({ ...editor, content: event.target.value })}
							/>
						</label>
						{error && (
							<p role="alert" className="text-ui-12 text-err">
								{error}
							</p>
						)}
						<div className="flex justify-end gap-2">
							<Button disabled={busy} onClick={() => setEditor(null)}>
								{t("rulesMemory.cancel")}
							</Button>
							<Button
								type="submit"
								variant="primary"
								disabled={busy || !editor.title.trim() || !editor.content.trim()}
							>
								{t("rulesMemory.save")}
							</Button>
						</div>
					</form>
				</Modal>
			)}
			{removing && (
				<ConfirmDialog
					title={t("rulesMemory.removeTitle")}
					description={t("rulesMemory.removeHint", { name: removing.title })}
					confirmLabel={t("rulesMemory.remove")}
					cancelLabel={t("rulesMemory.cancel")}
					danger
					confirmDisabled={busy}
					onCancel={() => setRemoving(null)}
					onConfirm={async () => {
						setBusy(true);
						setRemoveError(null);
						try {
							await harness("removeUserContextEntry", { id: removing.id });
							await load();
							setRemoving(null);
						} catch (failure) {
							setRemoveError(errText(failure) ?? String(failure));
						} finally {
							setBusy(false);
						}
					}}
				>
					{removeError && (
						<p role="alert" className="mt-3 text-ui-12 text-err">
							{removeError}
						</p>
					)}
				</ConfirmDialog>
			)}
		</section>
	);
}
