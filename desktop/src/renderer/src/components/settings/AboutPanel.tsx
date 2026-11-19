import { useEffect, useState } from "react";
import { getDesktopApi } from "../../api";
import veraLogo from "../../assets/splash/vera-logo.png";
import { useT } from "../../i18n";

/** 独立桌面前端信息，不调用旧项目的更新或诊断服务。 */
export function AboutPanel() {
	const t = useT();
	const [version, setVersion] = useState("");
	useEffect(() => {
		let active = true;
		void getDesktopApi()
			.getAppInfo()
			.then((info) => {
				if (active) setVersion(info.version);
			})
			.catch(() => {});
		return () => {
			active = false;
		};
	}, []);
	return (
		<div className="flex flex-col items-center gap-3 py-10 text-center">
			<img src={veraLogo} alt="VERA" className="h-14 w-24 object-contain" />
			<p className="mt-2 text-ui-14 font-semibold text-ink">VERA</p>
			<p className="text-ui-12 text-ink-dim">
				{t("settings.about.version")} {version || "…"}
			</p>
			<p className="mt-2 text-ui-12 text-ink-faint">{t("settings.about.frontendOnly")}</p>
		</div>
	);
}
