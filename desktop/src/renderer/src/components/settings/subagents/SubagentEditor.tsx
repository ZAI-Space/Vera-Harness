// Editor flow adapted from PI-Desktop SubagentEditorSheet.tsx, LGPL-3.0-only.
import { useState } from "react";
import { useT } from "../../../i18n";
import { useSessionsStore } from "../../../stores/sessions";
import {
	type SubagentDraft,
	type SubagentDraftError,
	useSubagentDraftsStore,
} from "../../../stores/subagent-drafts";
import { ArrowLeftIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { Switch } from "../../ui/Switch";
import { SUBAGENT_PRESETS, type SubagentPreset } from "./subagent-presets";
import { applySubagentPreset, resetSubagentTemplate } from "./subagent-template";

const INPUT_CLASS =
	"w-full min-w-0 rounded-lg border border-border bg-transparent px-3 py-2 text-ui-12 text-ink outline-none focus:border-ink-faint";
const names = (value: string) => value.split(/[\s,，]+/).filter(Boolean);

/** 独立编辑副本；提交成功才更新目录，取消和写盘失败均不丢失原记录。 */
export function SubagentEditor({
	draft,
	originalId,
	presetId,
	onClose,
}: {
	draft: SubagentDraft;
	originalId?: string;
	presetId?: SubagentPreset["id"];
	onClose: () => void;
}) {
	const t = useT();
	const models = useSessionsStore((state) => state.models);
	const [value, setValue] = useState(() => ({ ...draft }));
	const [tools, setTools] = useState(draft.tools.join(", "));
	const [skills, setSkills] = useState(draft.skills.join(", "));
	const [error, setError] = useState<SubagentDraftError | null>(null);
	const [selectedPreset, setSelectedPreset] = useState<SubagentPreset["id"] | "" | null>(
		presetId ?? (draft.name ? null : ""),
	);
	const save = useSubagentDraftsStore((s) => s.saveDraft);
	const update = (patch: Partial<SubagentDraft>) => setValue((current) => ({ ...current, ...patch }));
	const selectPreset = (id: SubagentPreset["id"] | "") => {
		const preset = SUBAGENT_PRESETS.find((item) => item.id === id);
		const next = preset ? applySubagentPreset(value, preset) : resetSubagentTemplate(value);
		setValue(next);
		setTools(next.tools.join(", "));
		setSelectedPreset(id);
		setError(null);
	};
	return (
		<form
			className="flex flex-col gap-5"
			aria-label={t(originalId ? "subagents.edit" : "subagents.create")}
			onSubmit={async (event) => {
				event.preventDefault();
				const failure = await save({ ...value, tools: names(tools), skills: names(skills) }, originalId);
				if (failure) {
					setError(failure);
					return;
				}
				onClose();
			}}
		>
			<div className="flex items-center justify-between gap-3">
				<h2 className="text-ui-14 font-semibold text-ink">
					{t(originalId ? "subagents.edit" : "subagents.create")}
				</h2>
				<Button size="sm" onClick={onClose} className="flex items-center gap-1.5">
					<ArrowLeftIcon />
					{t("common.cancel")}
				</Button>
			</div>
			{!originalId && (
				<fieldset className="min-w-0">
					<legend className="mb-2 text-ui-12 font-medium text-ink-dim">{t("subagents.templateLabel")}</legend>
					<div className="flex flex-wrap gap-2">
						{SUBAGENT_PRESETS.map((preset) => (
							<Button
								key={preset.id}
								size="sm"
								variant={selectedPreset === preset.id ? "primary" : "ghost"}
								aria-pressed={selectedPreset === preset.id}
								onClick={() => selectPreset(preset.id)}
							>
								{t(`subagents.presets.${preset.id}.name`)}
							</Button>
						))}
						<Button
							size="sm"
							variant={selectedPreset === "" ? "primary" : "ghost"}
							aria-pressed={selectedPreset === ""}
							onClick={() => selectPreset("")}
						>
							{t("subagents.blankTemplate")}
						</Button>
					</div>
					<p className="mt-2 text-ui-11 leading-relaxed text-ink-faint">{t("subagents.templateHint")}</p>
				</fieldset>
			)}
			<label htmlFor="subagent-name" className="flex flex-col gap-2 text-ui-12 text-ink-dim">
				{t("subagents.name")}
				<input
					id="subagent-name"
					className={INPUT_CLASS}
					value={value.name}
					required
					maxLength={48}
					placeholder="code-reviewer"
					onChange={(event) => update({ name: event.target.value })}
				/>
				<span className="text-ui-11 text-ink-faint">{t("subagents.nameHint")}</span>
			</label>
			<label htmlFor="subagent-model" className="flex flex-col gap-2 text-ui-12 text-ink-dim">
				{t("subagents.model")}
				<select
					id="subagent-model"
					className={INPUT_CLASS}
					value={value.model ? `${value.model.provider}/${value.model.modelId}` : ""}
					onChange={(event) => {
						const [provider, ...rest] = event.target.value.split("/");
						update({
							model: event.target.value ? { provider: provider ?? "", modelId: rest.join("/") } : undefined,
						});
					}}
				>
					<option value="">{t("subagents.followParentModel")}</option>
					{models.map((model) => (
						<option key={`${model.provider}/${model.id}`} value={`${model.provider}/${model.id}`}>
							{model.label}
						</option>
					))}
				</select>
			</label>
			<label htmlFor="subagent-description" className="flex flex-col gap-2 text-ui-12 text-ink-dim">
				{t("subagents.description")}
				<input
					id="subagent-description"
					className={INPUT_CLASS}
					value={value.description}
					required
					maxLength={320}
					onChange={(event) => update({ description: event.target.value })}
				/>
				<span className="text-ui-11 text-ink-faint">{t("subagents.descriptionHint")}</span>
			</label>
			<label htmlFor="subagent-instructions" className="flex flex-col gap-2 text-ui-12 text-ink-dim">
				{t("subagents.instructions")}
				<textarea
					id="subagent-instructions"
					className={`${INPUT_CLASS} min-h-48 resize-y font-mono leading-relaxed`}
					value={value.instructions}
					required
					maxLength={16000}
					onChange={(event) => update({ instructions: event.target.value })}
				/>
				<span className="text-ui-11 text-ink-faint">{t("subagents.instructionsHint")}</span>
			</label>
			<label htmlFor="subagent-tools" className="flex flex-col gap-2 text-ui-12 text-ink-dim">
				{t("subagents.tools")}
				<input
					id="subagent-tools"
					className={INPUT_CLASS}
					value={tools}
					placeholder="bash"
					onChange={(event) => setTools(event.target.value)}
				/>
				<span className="text-ui-11 text-ink-faint">{t("subagents.toolsHint")}</span>
			</label>
			<label htmlFor="subagent-skills" className="flex flex-col gap-2 text-ui-12 text-ink-dim">
				{t("subagents.skills")}
				<input
					id="subagent-skills"
					className={INPUT_CLASS}
					value={skills}
					onChange={(event) => setSkills(event.target.value)}
				/>
				<span className="text-ui-11 text-ink-faint">{t("subagents.skillsHint")}</span>
			</label>
			<details className="rounded-xl bg-hover/40 p-3">
				<summary className="cursor-pointer text-ui-12 font-medium text-ink-dim">
					{t("subagents.budgets")}
				</summary>
				<div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
					{(
						[
							{ field: "step_limit", label: "steps", min: 1, max: 200, step: 1 },
							{ field: "cost_limit", label: "cost", min: 0, max: undefined, step: "any" },
							{ field: "wall_time_limit_seconds", label: "timeout", min: 1, max: 3600, step: 1 },
						] as const
					).map(({ field, label, ...limits }) => (
						<label
							key={field}
							htmlFor={`subagent-${field}`}
							className="flex min-w-0 flex-col gap-2 text-ui-11 text-ink-dim"
						>
							{t(`subagents.${label}`)}
							<input
								id={`subagent-${field}`}
								type="number"
								className={INPUT_CLASS}
								required
								{...limits}
								value={Number.isFinite(value[field]) ? value[field] : ""}
								onChange={(event) => update({ [field]: event.target.valueAsNumber })}
							/>
						</label>
					))}
				</div>
				<p className="mt-3 text-ui-11 leading-relaxed text-ink-faint">{t("subagents.budgetHint")}</p>
			</details>
			<div className="flex items-center justify-between gap-3 text-ui-12 text-ink-dim">
				<span>{t("subagents.enabled")}</span>
				<Switch
					aria-label={t("subagents.enabled")}
					checked={value.enabled}
					onCheckedChange={(enabled) => update({ enabled })}
				/>
			</div>
			{error && (
				<p role="alert" className="text-ui-12 text-danger">
					{t(`subagents.errors.${error}`)}
				</p>
			)}
			<div className="flex justify-end gap-2">
				<Button onClick={onClose}>{t("common.cancel")}</Button>
				<Button type="submit" variant="primary">
					{t("subagents.save")}
				</Button>
			</div>
		</form>
	);
}
