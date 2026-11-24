// Page structure adapted from PI-Desktop PluginDetailSheet, LGPL-3.0-only.

import { CloseIcon } from "../../components/icons";
import { WorkspaceButton } from "../../components/workspace/WorkspacePage";
import { useT } from "../../i18n";
import { pluginDescription, type WorkspacePlugin } from "./model";
import { PluginIcon } from "./PluginIcon";

/** 插件详情的单层卡片内容，由页面的全屏浮层承载并统一处理安装确认。 */
export function PluginDetail({
	plugin,
	added,
	onClose,
	onAdd,
}: {
	plugin: WorkspacePlugin;
	added: boolean;
	onClose: () => void;
	onAdd: () => void;
}) {
	const t = useT();
	return (
		<section aria-label={t("plugins.details")} className="w-full bg-surface p-6">
			<header className="flex items-start justify-between gap-3">
				<div>
					<PluginIcon name={plugin.name} icon={plugin.icon} size={48} />
					<h2 className="mt-4 text-ui-19 font-semibold text-ink">{plugin.name}</h2>
					<p className="mt-1 text-ui-12 text-ink-faint">
						{plugin.author} · {plugin.version}
					</p>
				</div>
				<WorkspaceButton onClick={onClose} aria-label={t("common.close")}>
					<CloseIcon />
				</WorkspaceButton>
			</header>
			<p className="my-5 text-ui-13 leading-relaxed text-ink-dim">{pluginDescription(plugin, t)}</p>
			{plugin.longDescription && (
				<p className="mb-5 text-ui-13 leading-relaxed text-ink-dim">{plugin.longDescription}</p>
			)}
			<h3 className="text-ui-13 font-medium text-ink">{t("plugins.capabilities")}</h3>
			<ul className="mt-3 space-y-2 text-ui-13 text-ink-dim">
				{plugin.capabilities.map((capability) => (
					<li key={capability}>{capability}</li>
				))}
			</ul>
			{plugin.compatibility && (
				<p role="status" className="mt-5 rounded-lg bg-hover p-3 text-ui-12 text-ink-dim">
					{plugin.compatibility}
				</p>
			)}
			{plugin.source && <p className="mt-5 break-all text-ui-12 text-ink-faint">{plugin.source}</p>}
			<p className="mt-6 text-ui-12 leading-relaxed text-ink-faint">
				{t("plugins.addHint", { name: plugin.name })}
			</p>
			<WorkspaceButton
				className="mt-4 bg-hover"
				disabled={added || plugin.status === "error"}
				onClick={onAdd}
			>
				{t(added ? "plugins.added" : "plugins.addPreview")}
			</WorkspaceButton>
		</section>
	);
}
