import { useState } from "react";
import { FileTextIcon, ImageIcon, PuzzleIcon, ServerIcon, TerminalIcon } from "../../components/icons";

/** Prefer publisher artwork; use a functional symbol when the publisher supplies no image. */
export function PluginIcon({ name, icon, size = 40 }: { name: string; icon?: string; size?: number }) {
	const [failed, setFailed] = useState<string | undefined>();
	const Fallback = /design|figma|adobe|image|canvas/.test(name.toLowerCase())
		? ImageIcon
		: /terminal|code|git|dev/.test(name.toLowerCase())
			? TerminalIcon
			: /document|pdf|docx|xlsx|pptx|writing/.test(name.toLowerCase())
				? FileTextIcon
				: /mcp|server|database/.test(name.toLowerCase())
					? ServerIcon
					: PuzzleIcon;
	const isImage =
		icon?.startsWith("data:image/") ||
		/^https:\/\/(avatars\.githubusercontent\.com|raw\.githubusercontent\.com)\//.test(icon ?? "");
	return (
		<span
			className="flex shrink-0 items-center justify-center overflow-hidden rounded-xl bg-hover text-ui-16 font-semibold text-ink"
			style={{ width: size, height: size }}
		>
			{isImage && failed !== icon ? (
				<img
					src={icon}
					alt={`${name} icon`}
					className="h-full w-full object-contain p-1"
					loading="lazy"
					referrerPolicy="no-referrer"
					onError={() => setFailed(icon)}
				/>
			) : (
				<span role="img" aria-label={`${name} icon`}>
					<Fallback size={Math.round(size * 0.55)} />
				</span>
			)}
		</span>
	);
}
