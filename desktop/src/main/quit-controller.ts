/** 将关窗确认交给现有前端弹窗；界面无应答时回退退出，避免锁死窗口。 */
export class QuitController {
	private enabled = false;
	private timer: ReturnType<typeof setTimeout> | undefined;
	constructor(
		private readonly request: () => void,
		private readonly exit: () => void,
	) {}
	setEnabled(enabled: boolean): void {
		this.enabled = enabled;
	}
	canClose(): boolean {
		if (!this.enabled) return true;
		if (!this.timer) this.timer = setTimeout(() => this.confirm(), 1500);
		this.request();
		return false;
	}
	acknowledge(): void {
		if (this.timer) clearTimeout(this.timer);
		this.timer = undefined;
	}
	confirm(): void {
		this.acknowledge();
		this.enabled = false;
		this.exit();
	}
}
