import { isModelVisible, type ModelPrefs, type ProviderInfo } from "@vera/contracts";
import { useState } from "react";
import { useT } from "../../../i18n";
import { useSettingsStore } from "../../../stores/settings";
import { ChevronRightIcon, EditIcon, PlusIcon, TestIcon, TrashIcon } from "../../icons";
import { Button } from "../../ui/Button";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { Switch } from "../../ui/Switch";
import { BuiltinProviderEditForm } from "./BuiltinProviderEditForm";
import { CustomProviderEditForm, CustomProviderForm } from "./CustomProviderForm";

const EMPTY_PREFS: ModelPrefs = { hiddenModels: {}, subagentModels: {} };

/** API 配置页只展示已有连接中的模型，完整服务商目录留给账号订阅页。 */
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
	const [deleting, setDeleting] = useState<ProviderInfo | null>(null);
	const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
	const connections = providers.filter(
		(provider) =>
			provider.authType !== "oauth" &&
			(provider.custom || (provider.configured && (provider.authType === "api_key" || !provider.oauth))),
	);
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
						setEditor(null);
					}}
				>
					<PlusIcon />
					{t("modelAccess.addConnection")}
				</Button>
			</header>
			{adding && (
				<div>
					<p className="text-ui-12 text-ink-dim">{t("modelAccess.connectionHint")}</p>
					<CustomProviderForm initiallyOpen onDone={() => setAdding(false)} />
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
									{provider.baseUrl ?? provider.authLabel ?? provider.id}
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
								<CustomProviderEditForm provider={provider} onDone={() => setEditor(null)} embedded />
							) : (
								<BuiltinProviderEditForm provider={provider} onDone={() => setEditor(null)} />
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
												<p className="truncate text-ui-12 text-ink-dim">{model.name ?? model.id}</p>
												{model.name && model.name !== model.id && (
													<p className="mt-0.5 truncate text-ui-11 text-ink-faint">{model.id}</p>
												)}
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
