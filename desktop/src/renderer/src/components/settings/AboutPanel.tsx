import { useState } from "react";
import { getDesktopApi } from "../../api";
import veraLogo from "../../assets/splash/vera-logo.png";
import { useT } from "../../i18n";
import { errText } from "../../lib/error-text";
import { Button } from "../ui/Button";

const REPOSITORY_URL = "https://github.com/zml-mis/Vera-Harness";

/** Project identity and explicit external links; issue content is composed by the user on GitHub. */
export function AboutPanel() {
	const t = useT();
	const [error, setError] = useState<string | null>(null);
	const open = async (url: string) => {
		setError(null);
		try {
			await getDesktopApi().openExternal({ url });
		} catch (failure) {
			setError(errText(failure) ?? String(failure));
		}
	};
	return (
		<section
			aria-label={t("settings.category.about")}
			className="flex min-h-[380px] flex-col items-center justify-center px-5 py-12 text-center"
		>
			<img src={veraLogo} alt="VERA Harness" className="mb-7 h-20 w-44 object-contain" />
			<h3 className="text-ui-26 font-semibold tracking-tight text-ink">VERA Harness</h3>
			<div className="mt-8 flex flex-wrap justify-center gap-3">
				<Button variant="primary" onClick={() => void open(REPOSITORY_URL)} className="min-w-28">
					GitHub{" "}
					<span aria-hidden="true" className="ml-2 opacity-60">
						↗
					</span>
				</Button>
				<Button
					onClick={() => void open(`${REPOSITORY_URL}/issues`)}
					className="min-w-28 border border-border"
				>
					{t("settings.about.feedback")}{" "}
					<span aria-hidden="true" className="ml-2 opacity-60">
						↗
					</span>
				</Button>
			</div>
			{error && (
				<p role="alert" className="mt-5 text-ui-12 text-err">
					{error}
				</p>
			)}
		</section>
	);
}
