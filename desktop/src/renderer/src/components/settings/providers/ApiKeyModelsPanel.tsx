import { isModelVisible, type ModelPrefs, type ProviderInfo } from "@vera/contracts";
import { useState } from "react";
import { useT } from "../../../i18n";
import { useSettingsStore } from "../../../stores/settings";
import { ChevronRightIcon, EditIcon, PlusIcon, TestIcon, TrashIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { Modal } from "../../ui/Modal";
import { Switch } from "../../ui/Switch";
import { BuiltinProviderEditForm } from "./BuiltinProviderEditForm";
import { CustomProviderEditForm, CustomProviderForm } from "./CustomProviderForm";
import { EMPTY_MODEL_ROW, type ModelRow } from "./model-rows";

const PROVIDER_PRESETS: Array<{
	id: string;
	template?: string;
	name: string;
	baseUrl: string;
	api: string;
	models: ModelRow[];
}> = [
	{
		id: "deepseek",
		name: "DeepSeek",
		baseUrl: "https://api.deepseek.com",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "zai",
		name: "Z.AI",
		baseUrl: "https://api.z.ai/api/paas/v4",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "kimi",
		name: "Kimi",
		baseUrl: "https://api.moonshot.cn/v1",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "minimax",
		name: "MiniMax",
		baseUrl: "https://api.minimax.cn/v1",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "mimo",
		name: "Mimo",
		baseUrl: "https://api.xiaomimimo.com/v1",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "gemini",
		name: "Gemini",
		baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "claude",
		name: "Claude",
		baseUrl: "https://api.anthropic.com",
		api: "anthropic-messages",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "chatgpt",
		name: "ChatGPT",
		baseUrl: "https://api.openai.com/v1",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
	{
		id: "grok",
		name: "Grok",
		baseUrl: "https://api.x.ai/v1",
		api: "openai-completions",
		models: [{ ...EMPTY_MODEL_ROW }],
	},
];

const EMPTY_PREFS: ModelPrefs = { hiddenModels: {}, subagentModels: {} };

/** API 配置页展示已保存的服务商及模型，支持预设厂商和自定义接口。 */
export function ApiKeyModelsPanel({ providers }: { providers: ProviderInfo[] }) {
	const t = useT();
	const prefs = useSettingsStore((s) => s.modelPrefs) ?? EMPTY_PREFS;
	const setModelHidden = useSettingsStore((s) => s.setModelHidden);
	const removeCustom = useSettingsStore((s) => s.removeCustom);
	const removeCredential = useSettingsStore((s) => s.removeCredential);
	const test = useSettingsStore((s) => s.test);
	const testResults = useSettingsStore((s) => s.testResults);
	const [editor, setEditor] = useState<string | null>(null);
	const [adding, setAdding] = useState(false);
	const [preset, setPreset] = useState<(typeof PROVIDER_PRESETS)[number] | null>(null);
	const [deleting, setDeleting] = useState<ProviderInfo | null>(null);
	const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
	const connections = providers.filter((provider) => provider.custom || provider.configured);
	return (
		<div className="flex flex-col gap-4">
			<header className="flex items-start justify-between gap-3">
				<div>
					<h3 className="text-ui-13 font-medium text-ink-2">{t("modelAccess.configuredModels")}</h3>
					<p className="mt-1 text-ui-12 text-ink-faint">{t("modelAccess.apiHint")}</p>
				</div>
				<Button
					size="sm"
					className="flex shrink-0 items-center gap-1.5"
					onClick={() => {
						setAdding(true);
						setPreset(null);
						setEditor(null);
					}}
				>
					<PlusIcon />
					{t("modelAccess.addConnection")}
				</Button>
			</header>
			{adding && !preset && (
				<Modal title={t("modelAccess.addConnection")} onClose={() => setAdding(false)}>
					<div className="grid grid-cols-2 gap-2">
						<Button
							className="col-span-2 justify-start"
							onClick={() =>
								setPreset({
									id: `connection-${crypto.randomUUID()}`,
									name: "",
									template: "custom",
									baseUrl: "",
									api: "openai-completions",
									models: [{ ...EMPTY_MODEL_ROW }],
								})
							}
						>
							{t("modelAccess.customProvider")}
						</Button>
						{PROVIDER_PRESETS.map((item) => (
							<Button
								key={item.id}
								className="justify-start"
								onClick={() =>
									setPreset({
										...item,
										template: item.id,
										id: `connection-${item.id}-${crypto.randomUUID().slice(0, 8)}`,
									})
								}
							>
								{item.name}
							</Button>
						))}
					</div>
				</Modal>
			)}
			{adding && preset && (
				<div>
					<Modal title={preset.name || t("modelAccess.addConnection")} onClose={() => setAdding(false)}>
						<p className="mb-3 text-ui-12 text-ink-dim">{t("modelAccess.connectionHint")}</p>
						<CustomProviderForm
							initiallyOpen
							preset={preset}
							onDone={() => {
								setAdding(false);
								setPreset(null);
							}}
						/>
					</Modal>
				</div>
			)}
			{connections.length === 0 && !adding && (
				<p className="rounded-xl bg-hover/40 p-5 text-ui-12 leading-relaxed text-ink-faint">
					{t("modelAccess.empty")}
				</p>
			)}
			{connections.map((provider) => {
				const models = provider.customModels?.length ? provider.customModels : provider.models;
				const fullEdit =
					provider.custom && (!provider.overridesBuiltin || (provider.customModels?.length ?? 0) > 0);
				const result = testResults[provider.id];
				const isExpanded = expanded.has(provider.id);
				return (
					<section key={provider.id} aria-label={provider.name} className="rounded-xl bg-hover/30 p-3">
						<div className="mb-2 flex min-w-0 items-center justify-between gap-2">
							<button
								type="button"
								className="min-w-0 flex-1 text-left"
								aria-label={t("modelAccess.expandConnection", { name: provider.name })}
								aria-expanded={isExpanded}
								onClick={() =>
									setExpanded((current) => {
										const next = new Set(current);
										if (next.has(provider.id)) next.delete(provider.id);
										else next.add(provider.id);
										return next;
									})
								}
							>
								<span className="flex min-w-0 items-center gap-2">
									<ChevronRightIcon
										className={`shrink-0 transition-transform ${isExpanded ? "rotate-90" : ""}`}
									/>
									<span className="truncate text-ui-13 font-medium text-ink-2">{provider.name}</span>
									<span className="ml-auto shrink-0 text-ui-11 text-ink-faint">
										{t("modelAccess.modelCount", { count: models.length })}
									</span>
								</span>
								<span className="mt-1 block truncate text-ui-11 text-ink-faint">
									{provider.baseUrl ?? provider.id}
								</span>
								{!provider.configured && (
									<span className="mt-1 block text-ui-11 text-ink-faint">
										{t("modelAccess.missingCredential")}
									</span>
								)}
							</button>
							<div className="flex shrink-0 items-center gap-1">
								{provider.configured && (
									<Button
										size="sm"
										aria-label={t("settings.providers.test")}
										disabled={testResults[provider.id] === "testing"}
										onClick={() => void test(provider.id)}
									>
										<TestIcon />
									</Button>
								)}
								<Button
									size="sm"
									aria-label={t("modelAccess.editConnection", { name: provider.name })}
									onClick={() => {
										setEditor(editor === provider.id ? null : provider.id);
										setAdding(false);
									}}
								>
									<EditIcon />
								</Button>
								{(provider.custom || (provider.configured && provider.authSource === "stored")) && (
									<Button
										size="sm"
										aria-label={
											provider.custom
												? t("modelAccess.removeConnection", { name: provider.name })
												: t("settings.providers.removeCredential")
										}
										onClick={() => setDeleting(provider)}
									>
										<TrashIcon />
									</Button>
								)}
							</div>
						</div>
						{result && (
							<p
								role="status"
								className={`mb-2 text-ui-11 ${typeof result === "object" && !result.ok ? "text-err" : "text-ink-faint"}`}
							>
								{result === "testing"
									? t("modelAccess.testing")
									: result.ok
										? t("settings.providers.testOk", { modelId: result.modelId ?? "" })
										: t("settings.providers.testFailed", { error: result.error ?? "" })}
							</p>
						)}
						{editor === provider.id ? (
							fullEdit ? (
								<CustomProviderEditForm
									provider={provider}
									onDone={() => setEditor((current) => (current === provider.id ? null : current))}
									embedded
								/>
							) : (
								<BuiltinProviderEditForm
									provider={provider}
									onDone={() => setEditor((current) => (current === provider.id ? null : current))}
								/>
							)
						) : isExpanded && models.length ? (
							<div>
								<ul>
									{models.map((model) => (
										<li
											key={model.id}
											className="flex min-w-0 items-center justify-between gap-3 rounded-lg px-2 py-2.5 hover:bg-hover"
											data-configured-model={model.id}
										>
											<div className="min-w-0">
												<p className="truncate text-ui-12 text-ink-dim">{model.id}</p>
											</div>
											<Button
												size="sm"
												aria-label={t("modelAccess.editModel", { name: model.id })}
												onClick={() => setEditor(provider.id)}
											>
												<EditIcon />
											</Button>
											<Switch
												checked={isModelVisible(prefs, provider.id, model.id)}
												aria-label={t("modelAccess.visible", { name: model.id })}
												onCheckedChange={(visible) => void setModelHidden(provider.id, model.id, !visible)}
											/>
										</li>
									))}
								</ul>
								<Button
									size="sm"
									className="mt-2 flex items-center gap-1.5"
									onClick={() => setEditor(provider.id)}
								>
									<PlusIcon />
									{t("modelAccess.add")}
								</Button>
							</div>
						) : isExpanded ? (
							<p className="py-3 text-ui-12 text-ink-faint">{t("modelAccess.noModels")}</p>
						) : null}
					</section>
				);
			})}
			{deleting && (
				<ConfirmDialog
					title={t(
						deleting.custom ? "modelAccess.removeConnectionTitle" : "settings.providers.removeCredential",
					)}
					description={t(
						deleting.custom ? "modelAccess.removeConnectionHint" : "modelAccess.removeCredentialHint",
						{ name: deleting.name },
					)}
					confirmLabel={t("common.delete")}
					cancelLabel={t("common.cancel")}
					danger
					onCancel={() => setDeleting(null)}
					onConfirm={() => {
						if (deleting.custom) void removeCustom(deleting.id);
						else void removeCredential(deleting.id);
						setDeleting(null);
					}}
				/>
			)}
		</div>
	);
}
