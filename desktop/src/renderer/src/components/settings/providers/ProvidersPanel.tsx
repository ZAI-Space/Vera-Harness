import { useEffect } from "react";
import { useT } from "../../../i18n";
import { useSettingsStore } from "../../../stores/settings";
import { ApiKeyModelsPanel } from "./ApiKeyModelsPanel";

/** 模型设置仅提供 API 配置；每次进入时刷新服务商目录。 */
export function ProvidersPanel() {
	const t = useT();
	const providers = useSettingsStore((s) => s.providers);
	const loading = useSettingsStore((s) => s.loading);
	const refreshFromNetwork = useSettingsStore((s) => s.refreshProvidersFromNetwork);
	const error = useSettingsStore((s) => s.error);
	useEffect(() => {
		void refreshFromNetwork();
	}, [refreshFromNetwork]);
	return (
		<div>
			{error && (
				<p role="alert" className="mb-3 text-ui-12 text-err">
					{error}
				</p>
			)}
			{loading && providers.length === 0 ? (
				<p className="py-8 text-center text-ui-13 text-ink-faint">{t("settings.loading")}</p>
			) : (
				<ApiKeyModelsPanel providers={providers} />
			)}
		</div>
	);
}
