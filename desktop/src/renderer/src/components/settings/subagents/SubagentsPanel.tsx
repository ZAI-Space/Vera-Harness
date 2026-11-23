// List, template-copy and editor flow adapted from PI-Desktop AgentSubagentsPage.tsx, LGPL-3.0-only.
import { useState } from "react";
import { useT } from "../../../i18n";
import { type SubagentDraft, useSubagentDraftsStore } from "../../../stores/subagent-drafts";
import { CopyIcon, EditIcon, PlusIcon, SearchIcon, SubagentIcon, TrashIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { Switch } from "../../ui/Switch";
import { SubagentEditor } from "./SubagentEditor";
import { SUBAGENT_PRESETS, type SubagentPreset } from "./subagent-presets";
import { applySubagentPreset, createSubagentDraft } from "./subagent-template";

/** 设置中的本机角色目录；模板填充创建表单，保存后由共享 Runtime 装配执行。 */
export function SubagentsPanel() {
	const t = useT();
	const drafts = useSubagentDraftsStore((s) => s.drafts);
	const storageError = useSubagentDraftsStore((s) => s.storageError);
	const toggle = useSubagentDraftsStore((s) => s.toggleDraft);
	const remove = useSubagentDraftsStore((s) => s.removeDraft);
	const [search, setSearch] = useState("");
	const [editor, setEditor] = useState<{
		draft: SubagentDraft;
		originalId?: string;
		presetId?: SubagentPreset["id"];
	} | null>(null);
	const [deleting, setDeleting] = useState<SubagentDraft | null>(null);
	const templates = SUBAGENT_PRESETS.map((preset) => ({
		draft: applySubagentPreset(createSubagentDraft(), preset),
		presetId: preset.id,
		label: t(`subagents.presets.${preset.id}.name`),
		caption: t(`subagents.presets.${preset.id}.description`),
	}));
	const query = search.trim().toLocaleLowerCase();
	const matches = (draft: SubagentDraft) =>
		`${draft.name} ${draft.description}`.toLocaleLowerCase().includes(query);
	const owned = drafts.filter(matches);
	const presets = templates.filter(
		(template) =>
			matches(template.draft) || `${template.label} ${template.caption}`.toLocaleLowerCase().includes(query),
	);
	const copy = (draft: SubagentDraft, presetId?: SubagentPreset["id"]) => {
		let name = draft.name;
		for (let suffix = 2; drafts.some((item) => item.name === name); suffix++) {
			const ending = `-${suffix}`;
			name = `${draft.name.slice(0, 48 - ending.length)}${ending}`;
		}
		setEditor({ draft: { ...draft, id: "", name }, presetId });
	};
	return (
		<div className="flex flex-col gap-5">
			{editor ? (
				<SubagentEditor key={editor.originalId ?? "new"} {...editor} onClose={() => setEditor(null)} />
			) : (
				<>
					<header>
						<h2 className="text-ui-14 font-semibold text-ink">{t("subagents.title")}</h2>
						<p className="mt-1 text-ui-12 text-ink-dim">{t("subagents.caption")}</p>
					</header>
					<div className="flex items-center gap-3">
						<label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg bg-hover/50 px-3 py-2 text-ink-faint">
							<SearchIcon />
							<input
								type="search"
								aria-label={t("subagents.search")}
								placeholder={t("subagents.search")}
								className="min-w-0 flex-1 bg-transparent text-ui-12 text-ink outline-none"
								value={search}
								onChange={(event) => setSearch(event.target.value)}
							/>
						</label>
						<Button
							size="sm"
							variant="primary"
							className="flex shrink-0 items-center gap-1.5"
							onClick={() => setEditor({ draft: createSubagentDraft() })}
						>
							<PlusIcon />
							{t("subagents.create")}
						</Button>
					</div>
					<section aria-labelledby="subagent-owned-title">
						<h3 id="subagent-owned-title" className="mb-2 text-ui-11 font-medium text-ink-faint">
							{t("subagents.mine")} · {owned.length}
						</h3>
						{owned.length ? (
							<ul className="flex flex-col gap-1.5">
								{owned.map((draft) => (
									<li
										key={draft.id}
										className="flex items-center rounded-xl bg-hover/30 p-3"
										data-subagent-row={draft.name}
									>
										<div
											className={`flex w-2/3 min-w-0 items-center gap-2.5 pr-3 ${draft.enabled ? "text-ink-dim" : "text-ink-faint"}`}
										>
											<span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-hover/70">
												<SubagentIcon size={20} />
											</span>
											<div className="min-w-0 flex-1">
												<button
													type="button"
													className="block max-w-full truncate text-left text-ui-13 font-medium hover:text-ink"
													onClick={() => setEditor({ draft, originalId: draft.id })}
												>
													{draft.name}
												</button>
												<p className="mt-1 truncate text-ui-12 text-ink-faint" data-subagent-description>
													{draft.description}
												</p>
											</div>
										</div>
										<div className="flex flex-1 items-center justify-end gap-0.5">
											<Button
												size="sm"
												aria-label={t("subagents.copyNamed", { name: draft.name })}
												onClick={() => copy(draft)}
											>
												<CopyIcon />
											</Button>
											<Button
												size="sm"
												aria-label={t("subagents.editNamed", { name: draft.name })}
												onClick={() => setEditor({ draft, originalId: draft.id })}
											>
												<EditIcon />
											</Button>
											<Button
												size="sm"
												aria-label={t("subagents.removeNamed", { name: draft.name })}
												onClick={() => setDeleting(draft)}
											>
												<TrashIcon />
											</Button>
											<Switch
												className="ml-1"
												aria-label={t("subagents.toggleNamed", { name: draft.name })}
												checked={draft.enabled}
												onCheckedChange={() => toggle(draft.id)}
											/>
										</div>
									</li>
								))}
							</ul>
						) : (
							<p className="rounded-xl bg-hover/30 px-4 py-5 text-ui-12 leading-relaxed text-ink-faint">
								{t(query ? "subagents.noMatches" : "subagents.empty")}
							</p>
						)}
					</section>
					{presets.length > 0 && (
						<section aria-labelledby="subagent-templates-title">
							<h3 id="subagent-templates-title" className="mb-2 text-ui-11 font-medium text-ink-faint">
								{t("subagents.templates")}
							</h3>
							<ul className="flex flex-col gap-1.5">
								{presets.map(({ draft, presetId, label, caption }) => (
									<li
										key={draft.name}
										className="flex items-center rounded-xl bg-hover/30 p-3"
										data-subagent-row={draft.name}
									>
										<div className="flex w-2/3 min-w-0 items-center gap-2.5 pr-3 text-ink-dim">
											<span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-hover/70">
												<SubagentIcon size={20} />
											</span>
											<div className="min-w-0 flex-1">
												<p className="truncate text-ui-13 font-medium">{label}</p>
												<p className="mt-1 truncate text-ui-12 text-ink-faint" data-subagent-description>
													{caption}
												</p>
											</div>
										</div>
										<div className="flex flex-1 justify-end">
											<Button size="sm" onClick={() => copy(draft, presetId)}>
												{t("subagents.useTemplate")}
											</Button>
										</div>
									</li>
								))}
							</ul>
						</section>
					)}
				</>
			)}
			<p className="text-ui-11 leading-relaxed text-ink-faint">{t("subagents.frontendNotice")}</p>
			{storageError && (
				<p role="alert" className="text-ui-12 text-danger">
					{t("subagents.storageError")}
				</p>
			)}
			{deleting && (
				<ConfirmDialog
					title={t("subagents.remove")}
					description={t("subagents.removeHint", { name: deleting.name })}
					confirmLabel={t("common.delete")}
					cancelLabel={t("common.cancel")}
					danger
					onCancel={() => setDeleting(null)}
					onConfirm={() => {
						remove(deleting.id);
						setDeleting(null);
					}}
				/>
			)}
		</div>
	);
}
