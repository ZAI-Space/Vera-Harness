import {
	type CustomProviderInput,
	KNOWN_APIS,
	type ProviderInfo,
	type UpstreamModelInfo,
} from "@vera/contracts";
import { useEffect, useMemo, useState } from "react";
import { useT } from "../../../i18n";
import { readModelAdvanced, saveModelAdvanced } from "../../../stores/model-advanced-preferences";
import { useSettingsStore } from "../../../stores/settings";
import { pushToast } from "../../../stores/toasts";
import { ChevronRightIcon, InfoIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { Select } from "../../ui/Select";
import { Switch } from "../../ui/Switch";
import { ModelAdvancedSettings } from "./ModelAdvancedSettings";
import { ModelRowsEditor } from "./ModelRowsEditor";
import { EMPTY_MODEL_ROW, type ModelRow, modelsToRows, rowsToModelInputs, rowsValid } from "./model-rows";
import { createUpstreamModelsLoader, EMPTY_UPSTREAM_MODELS_STATE } from "./upstream-models-loader";

const EMPTY_UPSTREAM_MODELS: UpstreamModelInfo[] = [];

interface ProviderFormState {
	template?: string;
	fullUrl?: boolean;
	configured?: boolean;
	id: string;
	name: string;
	baseUrl: string;
	api: string;
	/** 逐模型行（id/上下文/输出/思考/图像），提交时经 rowsToModelInputs 转换 */
	models: ModelRow[];
	apiKey: string;
}

const EMPTY_FORM: ProviderFormState = {
	id: "",
	name: "",
	baseUrl: "",
	api: "openai-completions",
	models: [{ ...EMPTY_MODEL_ROW }],
	apiKey: "",
};

/** 配置使用稳定内部标识；编辑与重置沿用原 id，自动生成的标签不改变引用。 */
function createFormState(initial: ProviderFormState, retainedId?: string): ProviderFormState {
	const preferences = readModelAdvanced(initial.id);
	return {
		...initial,
		id: initial.id || retainedId || `connection-${crypto.randomUUID()}`,
		models: initial.models.map((row) => ({
			...row,
			...(!row.advanced && Object.hasOwn(preferences, row.id) ? { advanced: preferences[row.id] } : {}),
		})),
	};
}

function toInput(form: ProviderFormState): CustomProviderInput {
	return {
		id: form.id,
		template: form.template ?? "custom",
		fullUrl: form.fullUrl ?? false,
		name: form.name || undefined,
		baseUrl: form.baseUrl,
		api: form.api,
		models: rowsToModelInputs(form.models),
		apiKey: form.apiKey || undefined,
	};
}

/** User-facing labels are derived from the provider; stable IDs remain internal references. */
function providerHostname(address: string): string {
	try {
		return new URL(address).host;
	} catch {
		return "Custom";
	}
}

const inputClass =
	"w-full rounded-lg border border-border px-2.5 py-1.5 text-ui-12 outline-none focus:border-ink-faint disabled:cursor-not-allowed disabled:text-ink-faint";

/** 服务商配置表单（添加/编辑共用）：协议与地址、API Key、模型 ID、高级配置。布局由调用方控制 */
function ProviderConfigForm({
	title,
	initial,
	lockId,
	embedded,
	requireModels = false,
	onSubmit,
	onCancel,
}: {
	title: string;
	initial: ProviderFormState;
	/** 编辑模式锁定 ID：它是 models.json/auth.json/会话模型引用的主键，不可改 */
	lockId?: boolean;
	/** 嵌在 provider 卡片里展开：只画一条分隔线，不再套第二层边框 */
	embedded?: boolean;
	/** API_KEY 新建流程必须明确添加模型，不能静默沿用内置服务商的完整目录。 */
	requireModels?: boolean;
	onSubmit: (form: ProviderFormState) => Promise<void>;
	onCancel: () => void;
}) {
	const t = useT();
	const listUpstreamModels = useSettingsStore((s) => s.listUpstreamModels);
	const [form, setForm] = useState(() => createFormState(initial));
	const isPreset = !!form.template && form.template !== "custom";
	const isLocal = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(?=[:/]|$)/i.test(form.baseUrl);
	const canFetch =
		!!form.baseUrl.trim() && (!!form.apiKey.trim() || !!form.configured || (!isPreset && isLocal));
	const [advancedOpen, setAdvancedOpen] = useState(false);
	const [submitting, setSubmitting] = useState(false);
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [upstream, setUpstream] = useState(EMPTY_UPSTREAM_MODELS_STATE);
	/** 后端探测补全过的基址（站点根 → .../v1）：非空时取代静态提示 */
	const [normalizedBaseUrl, setNormalizedBaseUrl] = useState<string | null>(null);
	const upstreamLoader = useMemo(
		() => createUpstreamModelsLoader(listUpstreamModels, setUpstream),
		[listUpstreamModels],
	);
	useEffect(() => () => upstreamLoader.dispose(), [upstreamLoader]);

	/** 密钥留空时由所属后端经 SDK 解析已有凭证，失败就地显示。 */
	const fetchUpstream = async () => {
		const result = await upstreamLoader.load({
			providerId: lockId ? form.id : undefined,
			baseUrl: form.baseUrl,
			api: form.api,
			apiKey: form.apiKey,
			template: form.template,
			fullUrl: form.fullUrl,
		});
		if (!result) return;
		// 中转站面板给的「API 地址」常是站点根，后端探测出真实端点后回填，保存的就是这个地址
		if (form.fullUrl || result.baseUrl === form.baseUrl.trim().replace(/\/+$/, "")) return;
		setForm((f) => ({ ...f, baseUrl: result.baseUrl }));
		setNormalizedBaseUrl(result.baseUrl);
	};

	const update = (field: "baseUrl" | "api" | "apiKey", value: string) => {
		upstreamLoader.invalidate();
		setNormalizedBaseUrl(null);
		setForm((f) => ({ ...f, [field]: value }));
	};
	const set = (field: "baseUrl" | "apiKey") => (e: { target: { value: string } }) =>
		update(field, e.target.value);

	const submit = async () => {
		if (!rowsValid(form.models)) return;
		if (requireModels && !form.models.some((model) => model.id.trim())) return;
		setSubmitting(true);
		setSubmitError(null);
		try {
			await onSubmit({
				...form,
				name: isPreset ? initial.name : providerHostname(form.baseUrl),
			});
		} catch (error) {
			setSubmitError(error instanceof Error ? error.message : String(error));
		} finally {
			setSubmitting(false);
		}
	};

	// models.json 里的 api 理论上必是 KnownApiId；防御性兜底，不在表内也照常显示当前值
	const apiOptions = (KNOWN_APIS as readonly string[]).includes(form.api)
		? KNOWN_APIS
		: [form.api, ...KNOWN_APIS];

	return (
		<div className={embedded ? "mt-2 border-t border-border pt-2.5" : "rounded-xl border border-border p-3"}>
			<h3 className="text-ui-13 font-medium text-ink">{title}</h3>
			{isPreset ? (
				<div className="mt-4 rounded-lg border border-border p-3 text-ui-12 text-ink-dim">
					{t("modelForm.manufacturer")}: {initial.name}
				</div>
			) : (
				<div className="mt-4 flex flex-col gap-3">
					<div className="flex flex-col gap-2 text-ui-12 text-ink-dim">
						{t("modelAccess.protocol")}
						<Select
							ariaLabel={t("modelAccess.protocol")}
							value={form.api}
							options={apiOptions.map((api) => ({ value: api, label: api }))}
							onChange={(api) => {
								update("api", api);
								setForm((current) => ({ ...current, fullUrl: false }));
							}}
						/>
					</div>
					<div className="flex items-center justify-between gap-3 text-ui-12 text-ink-dim">
						<span>{t("settings.providers.customBaseUrl")}</span>
						<div className="flex items-center gap-2">
							{t("modelForm.fullUrl")}
							<Switch
								aria-label={t("modelForm.fullUrl")}
								checked={form.fullUrl ?? false}
								disabled={form.api === "google-generative-ai"}
								onCheckedChange={(fullUrl) => {
									upstreamLoader.invalidate();
									setForm((current) => ({ ...current, fullUrl }));
								}}
							/>
						</div>
					</div>
					<input
						aria-label={t("settings.providers.customBaseUrl")}
						className={inputClass}
						placeholder="https://api.example.com/v1"
						value={form.baseUrl}
						onChange={set("baseUrl")}
					/>
					<p className="text-ui-11 leading-relaxed text-ink-faint">
						{normalizedBaseUrl
							? t("settings.providers.upstreamBaseUrlFixed", { baseUrl: normalizedBaseUrl })
							: t(form.fullUrl ? "modelForm.fullUrlHint" : "settings.providers.customBaseUrlHint")}
					</p>
				</div>
			)}
			<label className="mt-4 flex flex-col gap-2 text-ui-12 text-ink-dim">
				API Key
				<input
					aria-label="API Key"
					className={inputClass}
					placeholder={lockId ? t("settings.providers.customKeyKeep") : "API Key"}
					type="password"
					autoComplete="off"
					value={form.apiKey}
					onChange={set("apiKey")}
				/>
				<span className="text-ui-11 leading-relaxed text-ink-faint">{t("modelForm.keyHint")}</span>
			</label>
			<div className="mt-4">
				<ModelRowsEditor
					rows={form.models}
					onChange={(models) => setForm((current) => ({ ...current, models }))}
					upstream={upstream.models ?? EMPTY_UPSTREAM_MODELS}
					fetching={upstream.loading}
					fetchError={
						upstream.error ?? (upstream.models?.length === 0 ? t("settings.providers.upstreamEmpty") : null)
					}
					fetchDisabled={!canFetch}
					onFetch={() => void fetchUpstream()}
				/>
			</div>
			<div className="mt-4">
				<button
					type="button"
					className="flex items-center gap-2 rounded-lg py-2 text-ui-12 text-ink-dim hover:text-ink"
					aria-expanded={advancedOpen}
					onClick={() => setAdvancedOpen(!advancedOpen)}
				>
					<span>{t("modelAdvanced.title")}</span>
					<ChevronRightIcon className={`transition-transform ${advancedOpen ? "rotate-90" : ""}`} />
				</button>
				{advancedOpen && (
					<ModelAdvancedSettings
						mode={isPreset ? "preset" : "custom"}
						rows={form.models}
						onChange={(models) => setForm((current) => ({ ...current, models }))}
					/>
				)}
			</div>
			{!rowsValid(form.models) && (
				<p role="alert" className="mt-2 text-ui-11 text-err">
					{t("modelAdvanced.checkValues")}
				</p>
			)}
			{submitError && (
				<p role="alert" className="mt-2 text-ui-11 text-err">
					{submitError}
				</p>
			)}
			<div className="mt-3 border-t border-border pt-3">
				<p className="flex items-start gap-1.5 text-ui-11 leading-relaxed text-ink-faint">
					<InfoIcon size={13} />
					<span>
						{t("modelAdvanced.testHint")} {t("modelAdvanced.testPending")}
					</span>
				</p>
				<div className="mt-3 flex flex-wrap justify-end gap-2">
					<Button
						size="sm"
						disabled={submitting}
						onClick={() => {
							setForm(createFormState(initial, form.id));
							upstreamLoader.invalidate();
							setNormalizedBaseUrl(null);
							setAdvancedOpen(false);
						}}
					>
						{t("modelAdvanced.reset")}
					</Button>
					<button
						type="button"
						className="rounded-lg px-3 py-1.5 text-ui-12 text-ink-dim transition-colors hover:bg-hover"
						onClick={onCancel}
					>
						{t("common.cancel")}
					</button>
					<button
						type="button"
						className="rounded-lg bg-ink px-3 py-1.5 text-ui-12 font-medium text-on-ink transition-colors hover:bg-ink-2 disabled:opacity-40"
						onClick={() => void submit()}
						disabled={
							submitting ||
							!form.id.trim() ||
							!form.baseUrl.trim() ||
							!rowsValid(form.models) ||
							(requireModels && !form.models.some((model) => model.id.trim()))
						}
					>
						{submitting ? t("settings.providers.submitting") : t("common.save")}
					</button>
				</div>
			</div>
		</div>
	);
}

/** 添加自定义 provider：折叠按钮 + 展开表单（取消/保存后收起即重置） */
export function CustomProviderForm({
	initiallyOpen = false,
	preset,
	onDone,
}: {
	initiallyOpen?: boolean;
	preset?: { template?: string; id: string; name: string; baseUrl: string; api: string; models: ModelRow[] };
	onDone?: () => void;
} = {}) {
	const t = useT();
	const addCustom = useSettingsStore((s) => s.addCustom);
	const [show, setShow] = useState(initiallyOpen);
	const close = () => {
		setShow(false);
		onDone?.();
	};

	if (!show) {
		return (
			<button
				type="button"
				className="mt-3 w-full rounded-lg border border-dashed border-border py-2 text-ui-13 text-ink-dim transition-colors hover:border-border-strong hover:bg-hover"
				onClick={() => setShow(true)}
			>
				{t("settings.providers.addCustom")}
			</button>
		);
	}

	return (
		<div className="mt-3">
			<ProviderConfigForm
				title={t("modelAdvanced.connectionTitle")}
				initial={
					preset
						? { ...EMPTY_FORM, ...preset, models: preset.models.map((model) => ({ ...model })) }
						: EMPTY_FORM
				}
				requireModels={initiallyOpen}
				onSubmit={async (form) => {
					await addCustom(toInput(form));
					if (!saveModelAdvanced(form.id, form.models)) pushToast("warning", "modelAdvanced.storageError");
					close();
				}}
				onCancel={close}
			/>
		</div>
	);
}

/** 编辑已添加的自定义 provider（API 配置卡片）：全字段可改，ID 锁定，Key 留空保持不变 */
export function CustomProviderEditForm({
	provider,
	onDone,
	embedded,
}: {
	provider: ProviderInfo;
	onDone: () => void;
	embedded?: boolean;
}) {
	const t = useT();
	const updateCustom = useSettingsStore((s) => s.updateCustom);

	return (
		<ProviderConfigForm
			title={t("modelAdvanced.editConnection")}
			initial={{
				...EMPTY_FORM,
				id: provider.id,
				template: provider.template,
				fullUrl: provider.fullUrl,
				configured: provider.configured,
				// 显示名称可修改；provider.id 始终保留，避免破坏既有模型引用。
				name: provider.name,
				baseUrl: provider.requestUrl ?? provider.baseUrl ?? "",
				api: provider.api ?? "openai-completions",
				// 只预填已落盘的自定义模型定义（避免把 runtime 全量内置模型写回 models.json）
				models: modelsToRows(provider.customModels ?? []),
			}}
			lockId
			embedded={embedded}
			onSubmit={async (form) => {
				await updateCustom(toInput(form));
				if (!saveModelAdvanced(form.id, form.models)) pushToast("warning", "modelAdvanced.storageError");
				onDone();
			}}
			onCancel={onDone}
		/>
	);
}
