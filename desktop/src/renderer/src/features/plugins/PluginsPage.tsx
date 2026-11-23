// Adapted from PI-Desktop PluginsPage / InstalledPluginsPanel / MarketplacePanel.
// LGPL-3.0-only; see third_party/pi-desktop/NOTICE.md for source and modifications.
import { useEffect, useState } from "react";
import { PlusIcon, TrashIcon } from "../../components/icons";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Modal } from "../../components/ui/Modal";
import { Select } from "../../components/ui/Select";
import { Switch } from "../../components/ui/Switch";
import {
	WorkspaceButton,
	WorkspaceEmpty,
	WorkspacePage,
	WorkspaceSearch,
} from "../../components/workspace/WorkspacePage";
import { isHarnessConnected } from "../../harness-api";
import { useT } from "../../i18n";
import { GROUP_ORDER, groupOf, matchesQuery, pluginDescription, type WorkspacePlugin } from "./model";
import { PluginDetail } from "./PluginDetail";
import { PluginIcon } from "./PluginIcon";
import { PluginSourceForm } from "./PluginSourceForm";
import { usePluginPreviewStore } from "./plugin-preview-store";
import { PLUGIN_PREVIEW_CATALOG } from "./preview-catalog";

/** 插件工作区：复用原页面的分栏、筛选、详情、确认流程，以独立预览 store 承接变更。 */
export function PluginsPage() {
	useEffect(() => {
		void usePluginPreviewStore.getState().refresh().catch(console.error);
	}, []);
	const remoteMarket = usePluginPreviewStore((s) => s.market);
	const { marketSource, marketLoaded, marketLoading, marketError, error, busy } = usePluginPreviewStore();
	const market = isHarnessConnected() ? remoteMarket : PLUGIN_PREVIEW_CATALOG;
	const t = useT();
	const plugins = usePluginPreviewStore((s) => s.plugins);
	const add = usePluginPreviewStore((s) => s.add);
	const remove = usePluginPreviewStore((s) => s.remove);
	const setEnabled = usePluginPreviewStore((s) => s.setEnabled);
	const [tab, setTab] = useState<"installed" | "market">("installed");
	const [queries, setQueries] = useState({ installed: "", market: "" });
	const [category, setCategory] = useState("all");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [sourceOpen, setSourceOpen] = useState(false);
	const repositories = usePluginPreviewStore((state) => state.repositories);
	const [pending, setPending] = useState<{ kind: "add" | "remove"; plugin: WorkspacePlugin } | null>(null);
	useEffect(() => {
		if (tab === "market" && isHarnessConnected() && !marketLoaded && !marketLoading && !marketError)
			void usePluginPreviewStore.getState().loadMarket(marketSource);
	}, [tab, marketSource, marketLoaded, marketLoading, marketError]);
	const query = queries[tab];
	const selected =
		plugins.find((plugin) => plugin.id === selectedId) ?? market.find((plugin) => plugin.id === selectedId);
	const filtered = (tab === "installed" ? plugins : market).filter(
		(plugin) =>
			matchesQuery(query, plugin.name, plugin.author, pluginDescription(plugin, t), ...plugin.capabilities) &&
			(tab === "installed" || category === "all" || category === plugin.category),
	);
	const added = (id: string) => plugins.some((plugin) => plugin.id === id);
	const card = (plugin: WorkspacePlugin) => (
		<article key={plugin.id} className="min-w-0 rounded-xl bg-surface p-5 shadow-soft">
			<div className="flex items-start justify-between gap-3">
				<button
					type="button"
					className="flex min-w-0 items-center gap-3 rounded-lg text-left outline-none focus-visible:ring-2 focus-visible:ring-ink-faint"
					onClick={() => setSelectedId(plugin.id)}
				>
					<PluginIcon key={plugin.id} name={plugin.name} icon={plugin.icon} />
					<div className="min-w-0">
						<h3 className="truncate text-ui-14 font-medium text-ink">{plugin.name}</h3>
						<p className="mt-1 text-ui-11 text-ink-faint">
							{plugin.author} · {plugin.version}
						</p>
					</div>
				</button>
				{tab === "installed" && (
					<Switch
						checked={plugin.enabled}
						disabled={busy !== null}
						onCheckedChange={(enabled) => setEnabled(plugin.id, enabled)}
						aria-label={t("plugins.toggle", { name: plugin.name })}
					/>
				)}
			</div>
			<p className="mt-4 line-clamp-2 min-h-10 text-ui-13 leading-relaxed text-ink-dim">
				{pluginDescription(plugin, t)}
			</p>
			<div className="mt-3 flex flex-wrap gap-1.5">
				{plugin.capabilities.length ? (
					plugin.capabilities.map((capability) => (
						<span key={capability} className="rounded-md bg-hover px-2 py-1 text-ui-11 text-ink-dim">
							{capability}
						</span>
					))
				) : (
					<span className="text-ui-11 text-ink-faint">{t("plugins.sourceDraft")}</span>
				)}
			</div>
			<div className="mt-4 flex items-center justify-between gap-2">
				<WorkspaceButton onClick={() => setSelectedId(plugin.id)}>{t("plugins.details")}</WorkspaceButton>
				{tab === "market" ? (
					<WorkspaceButton
						className="bg-hover"
						disabled={added(plugin.id) || busy !== null || plugin.status === "error"}
						onClick={() => setPending({ kind: "add", plugin })}
					>
						{t(added(plugin.id) ? "plugins.added" : "plugins.addPreview")}
					</WorkspaceButton>
				) : (
					<WorkspaceButton
						onClick={() => setPending({ kind: "remove", plugin })}
						aria-label={t("plugins.remove", { name: plugin.name })}
					>
						<TrashIcon />
					</WorkspaceButton>
				)}
			</div>
		</article>
	);

	return (
		<WorkspacePage
			title={t("plugins.title")}
			description={t("plugins.description")}
			actions={
				<>
					<WorkspaceButton onClick={() => setSourceOpen((open) => !open)}>
						<PlusIcon />
						{t("plugins.addRepository")}
					</WorkspaceButton>
					{tab === "installed" && (
						<WorkspaceButton className="bg-hover" onClick={() => setTab("market")}>
							{t("plugins.browseMarket")}
						</WorkspaceButton>
					)}
				</>
			}
		>
			{sourceOpen && (
				<Modal title={t("plugins.addRepository")} onClose={() => setSourceOpen(false)}>
					<PluginSourceForm
						errorMessage={error}
						onCancel={() => setSourceOpen(false)}
						onSave={async (plugin) => {
							if (isHarnessConnected()) {
								if (!(await usePluginPreviewStore.getState().addRepository(plugin.source ?? ""))) return;
							} else if (!(await add(plugin))) return;
							setSourceOpen(false);
							setTab("market");
						}}
					/>
				</Modal>
			)}

			{error && (
				<p role="alert" className="text-ui-12 text-err">
					{error}
				</p>
			)}
			{tab === "market" && marketLoading && <p role="status">{t("plugins.loadingMarket")}</p>}
			{tab === "market" && marketError && (
				<div role="alert" className="text-ui-12 text-err">
					<p>{marketError}</p>
					<WorkspaceButton
						onClick={() => void usePluginPreviewStore.getState().loadMarket(marketSource, true)}
					>
						{t("plugins.retryMarket")}
					</WorkspaceButton>
				</div>
			)}
			<div className="flex flex-wrap items-center justify-between gap-4">
				<div
					role="tablist"
					aria-label={t("plugins.title")}
					className="flex gap-1 rounded-lg bg-hover p-1"
					onKeyDown={(event) => {
						if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
						event.preventDefault();
						const target =
							event.key === "Home"
								? "installed"
								: event.key === "End"
									? "market"
									: tab === "installed"
										? "market"
										: "installed";
						setTab(target);
						event.currentTarget.querySelector<HTMLButtonElement>(`#plugins-tab-${target}`)?.focus();
					}}
				>
					{(["installed", "market"] as const).map((id) => (
						<button
							key={id}
							type="button"
							role="tab"
							id={`plugins-tab-${id}`}
							aria-controls={`plugins-panel-${id}`}
							aria-selected={tab === id}
							tabIndex={tab === id ? 0 : -1}
							className={`rounded-md px-4 py-2 text-ui-13 outline-none focus-visible:ring-2 focus-visible:ring-ink-faint ${tab === id ? "bg-surface font-medium text-ink shadow-soft" : "text-ink-dim hover:text-ink"}`}
							onClick={() => setTab(id)}
						>
							{t(`plugins.tabs.${id}`)}
							{id === "installed" && plugins.length > 0 ? ` ${plugins.length}` : ""}
						</button>
					))}
				</div>
				<WorkspaceSearch
					value={query}
					onChange={(value) => setQueries((previous) => ({ ...previous, [tab]: value }))}
					label={t("plugins.search")}
				/>
			</div>
			{tab === "market" && (
				<div className="flex flex-wrap items-center justify-between gap-3">
					<p className="text-ui-12 text-ink-faint">{t("plugins.exampleCatalog")}</p>
					<div className="flex gap-2">
						<Select
							ariaLabel={t("plugins.category")}
							value={category}
							onChange={setCategory}
							variant="ghost"
							options={(["all", "development", "productivity", "design"] as const).map((id) => ({
								value: id,
								label: t(`plugins.categories.${id}`),
							}))}
						/>
						{isHarnessConnected() && (
							<>
								<Select
									ariaLabel={t("plugins.sourceFilter")}
									value={marketSource}
									onChange={(source) => void usePluginPreviewStore.getState().loadMarket(source)}
									variant="ghost"
									options={repositories.map((repository) => ({
										value: repository.id,
										label: repository.name,
									}))}
								/>
								<WorkspaceButton
									disabled={marketLoading}
									onClick={() => void usePluginPreviewStore.getState().loadMarket(marketSource, true)}
								>
									{t("plugins.refreshMarket")}
								</WorkspaceButton>
							</>
						)}
					</div>
				</div>
			)}
			<div className="min-w-0">
				<div role="tabpanel" id={`plugins-panel-${tab}`} aria-labelledby={`plugins-tab-${tab}`}>
					{tab === "market" && marketLoading && !filtered.length ? null : filtered.length === 0 ? (
						<WorkspaceEmpty
							title={t(
								query || category !== "all"
									? "plugins.noMatches"
									: tab === "market"
										? "plugins.emptyMarket"
										: "plugins.empty",
							)}
							description={t("plugins.emptyHint")}
						>
							<WorkspaceButton
								onClick={() => {
									setQueries({ installed: "", market: "" });
									setCategory("all");
									setTab("market");
								}}
							>
								{t("plugins.browseMarket")}
							</WorkspaceButton>
						</WorkspaceEmpty>
					) : tab === "market" ? (
						<div className="grid gap-4 min-[850px]:grid-cols-2">{filtered.map(card)}</div>
					) : (
						<div className="space-y-6">
							{GROUP_ORDER.map((group) => {
								const rows = filtered.filter((plugin) => groupOf(plugin) === group);
								return (
									rows.length > 0 && (
										<section key={group}>
											<h2 className="mb-3 text-ui-12 font-medium text-ink-dim">
												{t(`plugins.groups.${group}`)} · {rows.length}
											</h2>
											<div className="grid gap-4 min-[850px]:grid-cols-2">{rows.map(card)}</div>
										</section>
									)
								);
							})}
						</div>
					)}
				</div>
			</div>
			{selected && (
				<Modal title={t("plugins.details")} showHeader={false} onClose={() => setSelectedId(null)}>
					<PluginDetail
						plugin={selected}
						added={added(selected.id)}
						onClose={() => setSelectedId(null)}
						onAdd={() => setPending({ kind: "add", plugin: selected })}
					/>
				</Modal>
			)}
			{pending && (
				<ConfirmDialog
					title={t(pending.kind === "add" ? "plugins.addPreview" : "plugins.removeTitle")}
					description={t(pending.kind === "add" ? "plugins.addHint" : "plugins.removeHint", {
						name: pending.plugin.name,
					})}
					confirmLabel={t(pending.kind === "add" ? "plugins.addPreview" : "common.delete")}
					cancelLabel={t("common.cancel")}
					confirmDisabled={busy !== null}
					danger={pending.kind === "remove"}
					onCancel={() => setPending(null)}
					onConfirm={async () => {
						if (pending.kind === "add") {
							if ((await add(pending.plugin)) === false) return;
						} else {
							if ((await remove(pending.plugin.id)) === false) return;
							if (selectedId === pending.plugin.id) setSelectedId(null);
						}
						setPending(null);
					}}
				>
					{error && (
						<p role="alert" className="mt-3 text-ui-12 text-err">
							{error}
						</p>
					)}
				</ConfirmDialog>
			)}
		</WorkspacePage>
	);
}
