import { readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";

/** 桌面 UI 偏好存储；串行原子替换，不读取旧后端配置或认证目录。 */
export class Preferences {
	private work: Promise<unknown> = Promise.resolve();
	constructor(private readonly directory: string) {}

	async read(name: string): Promise<unknown> {
		try {
			return JSON.parse(await readFile(join(this.directory, `${name}.json`), "utf8"));
		} catch (error) {
			if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
			throw error;
		}
	}

	write(name: string, value: unknown): Promise<void> {
		const operation = this.work.then(async () => {
			const file = join(this.directory, `${name}.json`);
			await writeFile(`${file}.tmp`, JSON.stringify(value), { mode: 0o600 });
			await rename(`${file}.tmp`, file);
		});
		this.work = operation.catch(() => {});
		return operation;
	}

	update(name: string, patch: Record<string, unknown>): Promise<void> {
		const operation = this.work.then(async () => {
			const current = await this.read(name);
			const value = { ...(current && typeof current === "object" ? current : {}), ...patch };
			const file = join(this.directory, `${name}.json`);
			await writeFile(`${file}.tmp`, JSON.stringify(value), { mode: 0o600 });
			await rename(`${file}.tmp`, file);
		});
		this.work = operation.catch(() => {});
		return operation;
	}
}
