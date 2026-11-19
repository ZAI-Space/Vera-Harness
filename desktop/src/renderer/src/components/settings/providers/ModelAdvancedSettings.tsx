import { useId, useState } from "react";
import { useT } from "../../../i18n";
import {
	DEFAULT_MODEL_ADVANCED,
	type ModelAdvancedOptions,
	validateModelAdvanced,
} from "../../../stores/model-advanced-preferences";
import { CloseIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Switch";
import { HintIcon } from "../HintIcon";
import { EMPTY_MODEL_ROW, type ModelRow, parseTokenCount } from "./model-rows";

const INPUT_CLASS =
	"w-full min-w-0 rounded-lg border border-border bg-transparent px-3 py-2 text-ui-12 text-ink outline-none focus:border-ink-faint disabled:text-ink-faint";

/** Token 数字段与快捷档位，支持手动填写 k/M 缩写；空值跟随模型默认。 */
function TokenField({
	label,
	value,
	presets,
	onChange,
}: {
	label: string;
	value: string;
	presets: readonly string[];
	onChange: (value: string) => void;
}) {
	const t = useT();
	const invalid = !!value.trim() && parseTokenCount(value) === null;
	return (
		<div className="flex flex-wrap items-center gap-2">
			<label className="flex min-w-0 flex-1 items-center rounded-lg border border-border text-ui-12 text-ink-dim">
				<span className="w-14 shrink-0 px-3">{label}</span>
				<input
					className={`${INPUT_CLASS} border-0`}
					aria-label={label}
					aria-invalid={invalid}
					placeholder={t("modelAdvanced.defaultValue")}
					value={value}
					onChange={(event) => onChange(event.target.value)}
				/>
			</label>
			<div className="flex gap-0.5">
				{presets.map((preset) => (
					<Button key={preset} size="sm" aria-label={`${label} ${preset}`} onClick={() => onChange(preset)}>
						{preset}
					</Button>
				))}
			</div>
		</div>
	);
}

/** 按模型编辑高级选项。已支持的能力留在模型行，其余选项只写前端偏好。 */
export function ModelAdvancedSettings({
	rows,
	onChange,
}: {
	rows: ModelRow[];
	onChange: (rows: ModelRow[]) => void;
}) {
	const t = useT();
	const id = useId();
	const [selected, setSelected] = useState(0);
	const [effort, setEffort] = useState("");
	const index = Math.min(selected, rows.length - 1);
	const row = rows[index];
	if (!row) return null;
	const advanced = row.advanced ?? DEFAULT_MODEL_ADVANCED;
	const error = validateModelAdvanced(advanced);
	const updateRow = (patch: Partial<ModelRow>) =>
		onChange(rows.map((item, position) => (position === index ? { ...item, ...patch } : item)));
	const update = (patch: Partial<ModelAdvancedOptions>) => updateRow({ advanced: { ...advanced, ...patch } });
	const addEffort = () => {
		const next = effort.trim();
		if (!next || next.length > 64 || advanced.reasoningValues.length >= 32) return;
		update({ reasoningValues: [...new Set([...advanced.reasoningValues, next])] });
		setEffort("");
	};
	return (
		<div className="flex flex-col gap-5 pb-2 pt-4">
			{rows.length > 1 && (
				<div className="flex items-center justify-between gap-3 text-ui-12 text-ink-dim">
					<span className="shrink-0">{t("modelAdvanced.model")}</span>
					<Select
						className="min-w-0 flex-1"
						ariaLabel={t("modelAdvanced.model")}
						value={String(index)}
						options={rows.map((item, position) => ({
							value: String(position),
							label: item.id || t("modelAdvanced.unnamed", { index: position + 1 }),
						}))}
						onChange={(value) => {
							setSelected(Number(value));
							setEffort("");
						}}
					/>
				</div>
			)}
			<fieldset className="flex min-w-0 flex-col gap-2">
				<legend className="mb-2 text-ui-12 font-medium text-ink-dim">{t("modelAdvanced.context")}</legend>
				<TokenField
					label={t("modelAdvanced.input")}
					value={row.contextWindow}
					presets={["128k", "256k", "512k", "1M"]}
					onChange={(contextWindow) => updateRow({ contextWindow })}
				/>
				<TokenField
					label={t("modelAdvanced.output")}
					value={row.maxTokens}
					presets={["4k", "16k", "32k", "128k"]}
					onChange={(maxTokens) => updateRow({ maxTokens })}
				/>
			</fieldset>
			<label className="flex flex-col gap-2 text-ui-12 text-ink-dim" htmlFor={`${id}-rounds`}>
				{t("modelAdvanced.toolCallLimit")}
				<input
					id={`${id}-rounds`}
					className={INPUT_CLASS}
					type="number"
					min={1}
					step={1}
					placeholder="500"
					value={advanced.toolCallLimit}
					onChange={(event) => update({ toolCallLimit: event.target.value })}
				/>
			</label>
			<fieldset>
				<legend className="mb-2 text-ui-12 font-medium text-ink-dim">{t("modelAdvanced.imageInput")}</legend>
				<div className="flex gap-5 text-ui-12 text-ink-dim">
					{[true, false].map((supported) => (
						<label key={String(supported)} className="flex items-center gap-2">
							<input
								type="radio"
								name={`${id}-image`}
								checked={row.imageInput === supported}
								onChange={() => updateRow({ imageInput: supported })}
							/>
							{t(supported ? "modelAdvanced.supported" : "modelAdvanced.unsupported")}
						</label>
					))}
				</div>
			</fieldset>
			<section className="flex flex-col gap-3">
				<div className="flex items-center justify-between gap-3">
					<div className="flex items-center gap-1.5 text-ui-12 font-medium text-ink-dim">
						{t("modelAdvanced.reasoning")}
						<HintIcon label={t("modelAdvanced.reasoningHint")} />
					</div>
					<Switch
						aria-label={t("modelAdvanced.reasoning")}
						checked={row.reasoning}
						onCheckedChange={(reasoning) => updateRow({ reasoning })}
					/>
				</div>
				<p className="text-ui-11 leading-relaxed text-ink-faint">{t("modelAdvanced.reasoningHint")}</p>
				<fieldset disabled={!row.reasoning} className="flex min-w-0 flex-col gap-2 disabled:opacity-50">
					<label className="flex flex-col gap-2 text-ui-12 text-ink-dim" htmlFor={`${id}-parameter`}>
						{t("modelAdvanced.reasoningParameter")}
						<input
							id={`${id}-parameter`}
							className={INPUT_CLASS}
							placeholder="reasoning_effort"
							value={advanced.reasoningParameter}
							onChange={(event) => update({ reasoningParameter: event.target.value })}
						/>
					</label>
					<div className="text-ui-12 text-ink-dim">{t("modelAdvanced.reasoningValues")}</div>
					<div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border p-2">
						{advanced.reasoningValues.map((value) => (
							<span
								key={value}
								className="flex items-center gap-1 rounded-md bg-hover px-2 py-1 text-ui-11 text-ink-dim"
							>
								{value === "default"
									? t("modelAdvanced.defaultReasoning")
									: value === "off"
										? t("modelAdvanced.offReasoning")
										: value}
								<button
									type="button"
									aria-label={t("modelAdvanced.removeValue", { value })}
									onClick={() =>
										update({ reasoningValues: advanced.reasoningValues.filter((item) => item !== value) })
									}
								>
									<CloseIcon size={10} />
								</button>
							</span>
						))}
						<input
							className="min-w-0 flex-1 bg-transparent px-1 py-1 text-ui-12 text-ink outline-none"
							aria-label={t("modelAdvanced.reasoningValues")}
							placeholder={t("modelAdvanced.reasoningPlaceholder")}
							value={effort}
							maxLength={64}
							onChange={(event) => setEffort(event.target.value)}
							onKeyDown={(event) => {
								if (event.key === "Enter" && !event.nativeEvent.isComposing) {
									event.preventDefault();
									addEffort();
								}
							}}
						/>
					</div>
				</fieldset>
			</section>
			<fieldset className="flex min-w-0 flex-col gap-2">
				<legend className="mb-2 text-ui-12 font-medium text-ink-dim">{t("modelAdvanced.sampling")}</legend>
				{(["temperature", "topP", "topK"] as const).map((field) => (
					<label
						key={field}
						className="flex min-w-0 items-center rounded-lg border border-border text-ui-12 text-ink-dim"
					>
						<span className="w-28 shrink-0 px-3">{t(`modelAdvanced.${field}`)}</span>
						<input
							aria-label={t(`modelAdvanced.${field}`)}
							className={`${INPUT_CLASS} border-0`}
							type="number"
							step={field === "topK" ? 1 : "any"}
							min={field === "topK" ? 1 : 0}
							max={field === "topK" ? 100 : field === "topP" ? 1 : 2}
							placeholder={t(`modelAdvanced.${field}Hint`)}
							value={advanced[field]}
							onChange={(event) => update({ [field]: event.target.value })}
						/>
					</label>
				))}
			</fieldset>
			{error && (
				<p role="alert" className="text-ui-11 text-err">
					{t(`modelAdvanced.errors.${error}`)}
				</p>
			)}
			<div className="flex justify-end">
				<Button
					size="sm"
					onClick={() => {
						updateRow({
							contextWindow: EMPTY_MODEL_ROW.contextWindow,
							maxTokens: EMPTY_MODEL_ROW.maxTokens,
							imageInput: false,
							reasoning: false,
							thinkingLevelMap: undefined,
							advanced: undefined,
						});
						setEffort("");
					}}
				>
					{t("modelAdvanced.resetModel")}
				</Button>
			</div>
			<p className="text-ui-11 leading-relaxed text-ink-faint">{t("modelAdvanced.frontendHint")}</p>
		</div>
	);
}
