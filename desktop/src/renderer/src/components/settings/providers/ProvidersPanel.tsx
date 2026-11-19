import { useEffect, useState } from "react";
import { isHarnessConnected } from "../../../harness-api";
import { useT } from "../../../i18n";
import { useSettingsStore } from "../../../stores/settings";
import { RefreshIcon } from "../../icons";
import { ApiKeyModelsPanel } from "./ApiKeyModelsPanel";
import { LoginDialog } from "./LoginDialog";
import { IconAction, ProviderRow } from "./ProviderRow";

type ModelSettingsTab = "apiKey" | "subscription";

/** 按认证方式分开 API 模型配置与订阅账号登录；OAuth 能力不等同于登录状态。 */
export function ProvidersPanel() {
	const t = useT();
	const [tab, setTab] = useState<ModelSettingsTab>("apiKey");
	const providers = useSettingsStore((s) => s.providers);
	const loading = useSettingsStore((s) => s.loading);
	const refreshing = useSettingsStore((s) => s.refreshing);
	const refreshFromNetwork = useSettingsStore((s) => s.refreshProvidersFromNetwork);
	const error = useSettingsStore((s) => s.error);
	const subscriptions = providers.filter(
		(provider) => !provider.custom && provider.oauth && provider.oauth.isSubscription !== false,
	);

	// 每次进入模型分类刷新一次目录；两种接入方式间切换不重新发起请求。
	useEffect(() => {
		void refreshFromNetwork();
	}, [refreshFromNetwork]);

	return (
		<div>
			<div className="mb-4 flex w-fit gap-1" role="tablist" aria-label={t("modelAccess.tabs")}>
				{(["apiKey", "subscription"] as const).map((id) => (
					<button
						key={id}
						disabled={isHarnessConnected() && id === "subscription"}
						title={
							isHarnessConnected() && id === "subscription"
								? "VERA does not support subscription OAuth yet"
								: undefined
						}
						type="button"
						role="tab"
						aria-selected={tab === id}
						aria-controls={`model-access-${id}`}
						id={`model-access-tab-${id}`}
						className={`rounded-lg px-3 py-2 text-ui-12 transition-colors ${tab === id ? "bg-hover font-medium text-ink" : "text-ink-faint hover:bg-hover hover:text-ink"}`}
						onClick={() => setTab(id)}
					>
						{t(`modelAccess.${id}`)}
					</button>
				))}
			</div>
			{error && (
				<p role="alert" className="mb-3 text-ui-12 text-err">
					{error}
				</p>
			)}
			<div role="tabpanel" id={`model-access-${tab}`} aria-labelledby={`model-access-tab-${tab}`}>
				{loading && providers.length === 0 ? (
					<p className="py-8 text-center text-ui-13 text-ink-faint">{t("settings.loading")}</p>
				) : tab === "apiKey" ? (
					<ApiKeyModelsPanel providers={providers} />
				) : (
					<>
						<div className="mb-4 flex items-start justify-between gap-3">
							<p className="text-ui-12 leading-relaxed text-ink-faint">{t("modelAccess.subscriptionHint")}</p>
							<IconAction
								label={t("settings.providers.refresh")}
								align="end"
								disabled={loading || refreshing}
								onClick={() => void refreshFromNetwork()}
							>
								<RefreshIcon />
							</IconAction>
						</div>
						{subscriptions.length ? (
							<ul className="grid grid-cols-1 items-start gap-2.5 sm:grid-cols-2">
								{subscriptions.map((provider) => (
									<ProviderRow
										key={provider.id}
										subscriptionOnly
										provider={{
											...provider,
											configured: provider.authType === "oauth",
											authLabel: provider.authType === "oauth" ? provider.authLabel : undefined,
										}}
									/>
								))}
							</ul>
						) : (
							<p className="py-4 text-ui-12 text-ink-faint">{t("modelAccess.subscriptionEmpty")}</p>
						)}
					</>
				)}
			</div>
			<LoginDialog />
		</div>
	);
}
