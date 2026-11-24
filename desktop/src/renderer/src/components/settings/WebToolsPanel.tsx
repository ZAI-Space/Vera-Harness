import { useCallback, useEffect, useState } from "react";
import { getDesktopApi } from "../../api";
import { harness } from "../../harness-api";
import { useT } from "../../i18n";
import { errText } from "../../lib/error-text";
import { Button } from "../ui/Button";
import { Select } from "../ui/Select";
import { Switch } from "../ui/Switch";

interface WebSettings {
	provider: string;
	enabled: boolean;
	readPages: boolean;
	searxngUrl: string;
	credentials: Record<string, boolean>;
}

const PROVIDERS = [
	{ value: "tavily", label: "Tavily" },
	{ value: "firecrawl", label: "Firecrawl" },
	{ value: "searxng", label: "SearXNG" },
];
const WEBSITES: Record<string, string> = {
	tavily: "https://app.tavily.com",
	firecrawl: "https://www.firecrawl.dev/app",
	searxng: "https://docs.searxng.org/dev/search_api.html",
};

/** Configure the shared search tools. Unsaved secrets stay in component memory and are never read back. */
export function WebToolsPanel() {
	const t = useT();
	const [settings, setSettings] = useState<WebSettings | null>(null);
	const [key, setKey] = useState("");
	const [removeKey, setRemoveKey] = useState(false);
	const [dirty, setDirty] = useState(false);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [message, setMessage] = useState<string | null>(null);
	const load = useCallback(async () => {
		setBusy(true);
		try {
			setSettings(await harness<WebSettings>("getWebSettings"));
			setError(null);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	}, []);
	useEffect(() => {
		void load();
	}, [load]);
	const update = (patch: Partial<WebSettings>) => {
		setSettings((previous) => previous && { ...previous, ...patch });
		setDirty(true);
		setMessage(null);
	};
	const save = async () => {
		if (!settings) return;
		setBusy(true);
		setError(null);
		setMessage(null);
		try {
			setSettings(
				await harness<WebSettings>("saveWebSettings", {
					provider: settings.provider,
					enabled: settings.enabled,
					readPages: settings.readPages,
					searxngUrl: settings.searxngUrl,
					apiKey: key,
					removeKey,
				}),
			);
			setKey("");
			setRemoveKey(false);
			setDirty(false);
			setMessage(t("webTools.saved"));
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	const test = async () => {
		setBusy(true);
		setError(null);
		setMessage(null);
		try {
			const result = await harness<{ tools: string[]; durationMs: number }>("testWebTools");
			setMessage(
				t("webTools.testPassed", {
					tools: result.tools.join(", "),
					seconds: (result.durationMs / 1000).toFixed(1),
				}),
			);
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		} finally {
			setBusy(false);
		}
	};
	const website = async () => {
		if (!settings) return;
		const url = WEBSITES[settings.provider];
		if (!url) return;
		try {
			await getDesktopApi().openExternal({ url });
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		}
	};
	return (
		<section aria-label={t("webTools.title")} className="flex flex-col gap-5">
			<p className="text-ui-12 leading-relaxed text-ink-dim">{t("webTools.hint")}</p>
			{error && (
				<p role="alert" className="text-ui-12 text-err">
					{error}
				</p>
			)}
			{!settings ? (
				<Button disabled={busy} onClick={() => void load()}>
					{t(busy ? "webTools.loading" : "webTools.reload")}
				</Button>
			) : (
				<>
					<div className="rounded-xl border border-border p-4">
						<div className="flex items-center justify-between gap-4">
							<div>
								<h3 className="text-ui-13 font-medium text-ink">{t("webTools.enable")}</h3>
								<p className="mt-1 text-ui-11 text-ink-faint">{t("webTools.nextTask")}</p>
							</div>
							<Switch
								aria-label={t("webTools.enable")}
								checked={settings.enabled}
								disabled={busy}
								onCheckedChange={(enabled) => update({ enabled })}
							/>
						</div>
						<p className="mt-5 text-ui-12 text-ink-dim">{t("webTools.provider")}</p>
						<div className="mt-2">
							<Select
								ariaLabel={t("webTools.provider")}
								disabled={busy}
								value={settings.provider}
								options={PROVIDERS}
								onChange={(provider) => {
									update({ provider, readPages: provider !== "searxng" });
									setKey("");
									setRemoveKey(false);
								}}
							/>
						</div>
						<div className="mt-4 flex items-center justify-between gap-4">
							<label htmlFor="web-credential" className="text-ui-12 text-ink-dim">
								{settings.provider === "searxng" ? t("webTools.instance") : "API Key"}
							</label>
							<Button disabled={busy} onClick={() => void website()}>
								{t(settings.provider === "searxng" ? "webTools.docs" : "webTools.getKey")} ↗
							</Button>
						</div>
						<input
							id="web-credential"
							autoComplete="off"
							type={settings.provider === "searxng" ? "url" : "password"}
							disabled={busy}
							className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-ui-12 text-ink outline-none focus:border-border-strong"
							value={settings.provider === "searxng" ? settings.searxngUrl : key}
							placeholder={
								settings.provider === "searxng"
									? "http://localhost:8080"
									: t(
											settings.credentials[settings.provider] && !removeKey
												? "webTools.keepKey"
												: "webTools.enterKey",
										)
							}
							onChange={(event) => {
								if (settings.provider === "searxng") update({ searxngUrl: event.target.value });
								else {
									setKey(event.target.value);
									setRemoveKey(false);
									update({});
								}
							}}
						/>
						<p className="mt-2 text-ui-11 leading-relaxed text-ink-faint">
							{t(settings.provider === "searxng" ? "webTools.searxngHint" : "webTools.privateKey")}
						</p>
						{settings.provider !== "searxng" && settings.credentials[settings.provider] && (
							<Button
								disabled={busy || removeKey}
								onClick={() => {
									setRemoveKey(true);
									setKey("");
									update({ enabled: false });
								}}
							>
								{t(removeKey ? "webTools.keyPendingRemoval" : "webTools.removeKey")}
							</Button>
						)}
					</div>
					<div className="rounded-xl border border-border p-4">
						<div className="flex items-center justify-between gap-4">
							<div>
								<h3 className="text-ui-13 font-medium text-ink">{t("webTools.readPages")}</h3>
								<p className="mt-1 text-ui-11 text-ink-faint">{t("webTools.readHint")}</p>
							</div>
							<Switch
								aria-label={t("webTools.readPages")}
								disabled={busy || settings.provider === "searxng"}
								checked={settings.readPages}
								onCheckedChange={(readPages) => update({ readPages })}
							/>
						</div>
					</div>
					<div className="flex items-center justify-end gap-2">
						<Button disabled={busy || dirty || !settings.enabled} onClick={() => void test()}>
							{t(busy ? "webTools.working" : "webTools.test")}
						</Button>
						<Button variant="primary" disabled={busy || !dirty} onClick={() => void save()}>
							{t("webTools.save")}
						</Button>
					</div>
					{message && (
						<p role="status" className="text-ui-12 text-ink-dim">
							{message}
						</p>
					)}
					<p className="text-ui-11 leading-relaxed text-ink-faint">{t("webTools.testHint")}</p>
				</>
			)}
		</section>
	);
}
