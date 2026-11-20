// Page structure adapted from PI-Desktop PluginDetailSheet, LGPL-3.0-only.

import { CloseIcon, PuzzleIcon } from "../../components/icons";
import { WorkspaceButton } from "../../components/workspace/WorkspacePage";
import { useT } from "../../i18n";
import { pluginDescription, type WorkspacePlugin } from "./model";

/** 插件详情作为当前页面的一列展示，所有提交交回页面进行确认。 */
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
		<section aria-label={t("plugins.details")} className="min-w-0 rounded-xl bg-surface p-5 shadow-soft">
			<header className="flex items-start justify-between gap-3">
				<div>
					<PuzzleIcon size={24} />
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
			<h3 className="text-ui-13 font-medium text-ink">{t("plugins.capabilities")}</h3>
			<ul className="mt-3 space-y-2 text-ui-13 text-ink-dim">
				{plugin.capabilities.map((capability) => (
					<li key={capability}>{capability}</li>
				))}
			</ul>
			{plugin.source && <p className="mt-5 break-all text-ui-12 text-ink-faint">{plugin.source}</p>}
			<p className="mt-6 text-ui-12 leading-relaxed text-ink-faint">{t("plugins.addHint")}</p>
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
