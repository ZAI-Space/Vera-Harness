/** 表单原文与旧版偏好的兼容格式；保存时转为后端数值配置。 */
export interface ModelAdvancedOptions {
	toolCallLimit: string;
	reasoningParameter: string;
	reasoningValues: string[];
	temperature: string;
	topP: string;
	topK: string;
}

export const MODEL_ADVANCED_STORAGE_KEY = "vera.model-advanced.v1";
export const DEFAULT_MODEL_ADVANCED: ModelAdvancedOptions = {
	toolCallLimit: "500",
	reasoningParameter: "reasoning_effort",
	reasoningValues: ["default", "off", "low", "medium", "high"],
	temperature: "",
	topP: "",
	topK: "",
};
export type ModelAdvancedError =
	| "toolCallLimit"
	| "reasoningParameter"
	| "reasoningValues"
	| "temperature"
	| "topP"
	| "topK";

/** 留空表示使用默认值；非空时按界面声明的数值范围和参数路径校验。 */
export function validateModelAdvanced(value: ModelAdvancedOptions): ModelAdvancedError | null {
	const number = (raw: string) => (raw.trim() === "" ? null : Number(raw));
	const rounds = number(value.toolCallLimit);
	if (rounds !== null && (!Number.isSafeInteger(rounds) || rounds < 1 || rounds > 10000))
		return "toolCallLimit";
	if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(value.reasoningParameter.trim()))
		return "reasoningParameter";
	if (
		value.reasoningValues.some((item) => !item.trim() || item.length > 64) ||
		value.reasoningValues.length > 32
	)
		return "reasoningValues";
	for (const [field, max] of [
		["temperature", 2],
		["topP", 1],
	] as const) {
		const parsed = number(value[field]);
		if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0 || parsed > max)) return field;
	}
	const topK = number(value.topK);
	if (topK !== null && (!Number.isInteger(topK) || topK < 1 || topK > 100)) return "topK";
	return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return !!value && typeof value === "object" && !Array.isArray(value);
}
/** 只取允许的配置字段，防止任意附加属性进入前端存储。 */
function normalizeOptions(item: unknown): ModelAdvancedOptions | null {
	if (
		!isRecord(item) ||
		!["toolCallLimit", "reasoningParameter", "temperature", "topP", "topK"].every(
			(field) => typeof item[field] === "string",
		) ||
		!Array.isArray(item.reasoningValues) ||
		!item.reasoningValues.every((value) => typeof value === "string")
	)
		return null;
	const value = item as unknown as ModelAdvancedOptions;
	if (validateModelAdvanced(value)) return null;
	return {
		toolCallLimit: value.toolCallLimit,
		reasoningParameter: value.reasoningParameter,
		reasoningValues: [...value.reasoningValues],
		temperature: value.temperature,
		topP: value.topP,
		topK: value.topK,
	};
}

function normalizeModels(models: unknown): Record<string, ModelAdvancedOptions> {
	if (!isRecord(models)) return {};
	return Object.fromEntries(
		Object.entries(models).flatMap(([id, item]) => {
			const value = normalizeOptions(item);
			return value ? [[id, value]] : [];
		}),
	);
}

function readPreferences(): Record<string, Record<string, ModelAdvancedOptions>> {
	try {
		const saved: unknown = JSON.parse(localStorage.getItem(MODEL_ADVANCED_STORAGE_KEY) ?? "{}");
		if (!isRecord(saved)) return {};
		return Object.fromEntries(
			Object.entries(saved).map(([connection, models]) => [connection, normalizeModels(models)]),
		);
	} catch {
		return {};
	}
}
/** 返回指定连接各模型的高级偏好；缺失、损坏或非法记录被忽略。 */
export function readModelAdvanced(connectionId: string): Record<string, ModelAdvancedOptions> {
	const preferences = readPreferences();
	return Object.hasOwn(preferences, connectionId) ? (preferences[connectionId] ?? {}) : {};
}

/** 基础连接保存成功后才写前端偏好。失败返回 false，调用方提示，不伪造已保存。 */
export function saveModelAdvanced(
	connectionId: string,
	models: { id: string; advanced?: ModelAdvancedOptions }[],
): boolean {
	try {
		const entries = models.filter((model) => model.id.trim() && model.advanced);
		if (entries.some((model) => model.advanced && validateModelAdvanced(model.advanced))) return false;
		localStorage.setItem(
			MODEL_ADVANCED_STORAGE_KEY,
			JSON.stringify({
				...readPreferences(),
				[connectionId]: normalizeModels(
					Object.fromEntries(entries.map((model) => [model.id.trim(), model.advanced])),
				),
			}),
		);
		return true;
	} catch {
		return false;
	}
}
