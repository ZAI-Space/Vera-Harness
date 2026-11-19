/** 权限策略图标：手动、确认、自动执行，沿用界面 currentColor 与线框样式。 */
interface PolicyIconProps {
	size?: number;
	className?: string;
}

export function HumanPolicyIcon({ size = 14, className }: PolicyIconProps) {
	return (
		<svg
			width={size}
			height={size}
			className={className}
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth={1.6}
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
		>
			<path d="M8 12V5a1.5 1.5 0 0 1 3 0v6M11 6V3.5a1.5 1.5 0 0 1 3 0V11M14 6a1.5 1.5 0 0 1 3 0v6M17 9a1.5 1.5 0 0 1 3 0v5c0 4-2.5 7-6.5 7-2.4 0-4-1-5.5-3l-4-5a1.5 1.5 0 0 1 2.3-1.9L8 13" />
		</svg>
	);
}

export function ConfirmPolicyIcon({ size = 14, className }: PolicyIconProps) {
	return (
		<svg
			width={size}
			height={size}
			className={className}
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth={1.6}
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
		>
			<circle cx="12" cy="12" r="9" />
			<path d="m7.5 8.5 3 3-3 3M13 14.5h3.5" />
		</svg>
	);
}

export function YoloPolicyIcon({ size = 14, className }: PolicyIconProps) {
	return (
		<svg
			width={size}
			height={size}
			className={className}
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth={1.6}
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
		>
			<path d="m12 3 8 3v6c0 4-3 7-8 9-5-2-8-5-8-9V6l8-3Z" />
			<path d="m13 7-3 5h4l-3 5" />
		</svg>
	);
}
