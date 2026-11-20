import type { UpstreamModelInfo } from "@vera/contracts";
import { useState } from "react";
import { useT } from "../../../i18n";
import { SearchIcon } from "../../icons";
import { Button } from "../../ui/Button";

/** 上游结果只作候选：搜索和勾选不修改配置，确认时仅返回尚未添加的模型。 */
export function UpstreamModelPicker({
	models,
	addedIds,
	onAdd,
}: {
	models: readonly UpstreamModelInfo[];
	addedIds: readonly string[];
	onAdd: (models: UpstreamModelInfo[]) => void;
}) {
	const t = useT();
	const [search, setSearch] = useState("");
	const [selected, setSelected] = useState<Set<string>>(() => new Set());
	const added = new Set(addedIds.map((id) => id.trim()));
	const query = search.trim().toLocaleLowerCase();
	const visible = models.filter((model) =>
		`${model.id} ${model.name ?? ""}`.toLocaleLowerCase().includes(query),
	);
	const picked = models.filter((model) => selected.has(model.id) && !added.has(model.id));
	return (
		<section className="mt-3 rounded-xl bg-hover/50 p-3" aria-label={t("modelAccess.chooseModels")}>
			<h4 className="text-ui-12 font-medium text-ink-2">{t("modelAccess.chooseModels")}</h4>
			<label className="my-3 flex items-center gap-2 rounded-lg bg-surface px-2.5 py-2 text-ink-faint">
				<SearchIcon />
				<input
					type="search"
					aria-label={t("modelAccess.searchModels")}
					placeholder={t("modelAccess.searchModels")}
					className="min-w-0 flex-1 bg-transparent text-ui-12 text-ink outline-none"
					value={search}
					onChange={(event) => setSearch(event.target.value)}
				/>
			</label>
			<div className="mb-2 flex flex-wrap items-center gap-1.5">
				<Button
					size="sm"
					onClick={() =>
						setSelected(
							(previous) =>
								new Set([
									...previous,
									...visible.filter((model) => !added.has(model.id)).map((model) => model.id),
								]),
						)
					}
					disabled={!visible.some((model) => !added.has(model.id))}
				>
					{t("modelAccess.selectVisible")}
				</Button>
				<Button size="sm" onClick={() => setSelected(new Set())} disabled={!selected.size}>
					{t("modelAccess.clearSelection")}
				</Button>
			</div>
			<div className="max-h-48 overflow-y-auto">
				{visible.length ? (
					visible.map((model) => (
						<label
							key={model.id}
							className={`flex min-w-0 items-center gap-3 rounded-lg px-2 py-2 text-ui-12 hover:bg-hover ${added.has(model.id) ? "text-ink-faint" : "text-ink-dim"}`}
						>
							<input
								type="checkbox"
								className="shrink-0 accent-[var(--color-ink)]"
								checked={added.has(model.id) || selected.has(model.id)}
								disabled={added.has(model.id)}
								aria-label={model.id}
								onChange={(event) => {
									const checked = event.target.checked;
									setSelected((previous) => {
										const next = new Set(previous);
										if (checked) next.add(model.id);
										else next.delete(model.id);
										return next;
									});
								}}
							/>
							<span className="min-w-0 flex-1">
								<span className="block truncate">{model.name ?? model.id}</span>
								{model.name && model.name !== model.id && (
									<span className="block truncate text-ui-11 text-ink-faint">{model.id}</span>
								)}
							</span>
							{added.has(model.id) && (
								<span className="shrink-0 text-ui-11">{t("modelAccess.alreadyAdded")}</span>
							)}
						</label>
					))
				) : (
					<p className="py-4 text-center text-ui-12 text-ink-faint">{t("modelAccess.noMatches")}</p>
				)}
			</div>
			<div className="mt-3 flex flex-wrap items-center justify-between gap-2">
				<span role="status" className="text-ui-11 text-ink-faint">
					{t("modelAccess.selectedCount", { count: picked.length })}
				</span>
				<Button
					size="sm"
					disabled={!picked.length}
					onClick={() => {
						onAdd(picked);
						setSelected(new Set());
					}}
				>
					{t("modelAccess.addSelected", { count: picked.length })}
				</Button>
			</div>
			<p className="mt-2 text-ui-11 leading-relaxed text-ink-faint">{t("modelAccess.selectionHint")}</p>
		</section>
	);
}
