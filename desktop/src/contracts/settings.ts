/** 设置页相关类型（IPC 往返用，独立于 pi 内部类型） */

/** pi-ai 的 KnownApi 协议可选值（自定义 provider 时用） */
export const KNOWN_APIS = [
	"openai-completions",
	"openai-responses",
	"anthropic-messages",
	"google-generative-ai",
] as const;

export type KnownApiId = (typeof KNOWN_APIS)[number];

export interface ListProvidersOptions {
	/** true 时强制从 pi.dev 联网拉取最新模型目录（绕过 4h 新鲜度窗口）；默认 false 只用内置目录 + 本地缓存 */
	forceNetwork?: boolean;
}

/** 用户级模型偏好（<agentDir>/model-prefs.json）。 */
export interface ModelPrefs {
	/** 隐藏的模型 id（provider → modelId 列表）；隐藏不影响已经选中的会话运行 */
	hiddenModels: Record<string, string[]>;
	/** 全源模型默认隐藏（不影响凭证或当前会话执行）；缺省为空 */
	hiddenProviders?: string[];
	/** 默认隐藏源中的单模型显示例外；非隐藏源不保留条目 */
	visibleModels?: Record<string, string[]>;
	subagentModels: Record<string, string>;
	/** 逐代理思考深度覆盖（agent name → level）；无键 = 跟随 agent 定义 */
	subagentThinking?: Record<string, string>;
	/** 内置 subagent 执行器优先（默认 true）；新会话/恢复会话生效 */
	subagentPreferBuiltin?: boolean;
}

/** 设置页可配置的子代理（仅内置与用户级定义，不含项目级）。 */
export interface SubagentInfo {
	name: string;
	description: string;
	source: "builtin" | "user";
	/** agent 定义中的合法 thinking 档位（无定义/非法时 undefined） */
	thinking?: string;
	/** agent 定义中 thinking 非法时的原文（设置页警示用） */
	thinkingWarning?: string;
	denyWarnings?: string[];
}

export interface ProviderModelInfo {
	id: string;
	name: string;
	/** 是否支持思考/推理（自定义 provider 从 models.json 原文回填，编辑预填用） */
	reasoning?: boolean;
	/** 上下文窗口 tokens（同上，未设置则为 undefined，SDK 缺省 128000） */
	contextWindow?: number;
	/** 最大输出 tokens（同上，SDK 缺省 16384） */
	maxTokens?: number;
	/** 支持图片输入（同上，SDK 缺省仅文本） */
	imageInput?: boolean;
}

export interface ProviderInfo {
	/** 创建连接时选用的服务商预设。 */
	template?: string;
	/** 用户输入的地址是否包含协议请求路径。 */
	fullUrl?: boolean;
	/** 用户原始请求地址；baseUrl 是供 SDK 使用的规范化地址。 */
	requestUrl?: string;
	id: string;
	/** 显示名 */
	name: string;
	/** 是否来自 models.json 的自定义 provider */
	custom: boolean;
	/** 覆写内置 provider（models.json 有配置且 id 为内置，如 openai——pi 官方「覆写 baseUrl 共享官方模型列表」语义）；区别于真·自定义全新 id */
	overridesBuiltin?: boolean;
	/** 是否有可用凭证 */
	configured: boolean;
	/** 凭证来源：stored / runtime / environment / models_json_key / models_json_command */
	authSource?: string;
	/** 当前有效凭证类型；仅返回 API 凭证的非敏感元数据。 */
	authType?: "api_key";
	/** 自定义 provider 的 baseUrl（来自 models.json，编辑表单预填用；内置 provider 不填） */
	baseUrl?: string;
	/** 自定义 provider 的 api 协议（编辑表单预填用；内置 provider 不填） */
	api?: string;
	/** 已在 models.json 落盘的自定义模型定义（原文回填，编辑表单预填用；区别于 runtime 全量 models） */
	customModels?: CustomProviderModelInput[];
	/** 全量模型（内置 + models.json 自定义 + 远程目录 overlay，展示用） */
	models: ProviderModelInfo[];
}

/** 思考档位（与 SDK ModelThinkingLevel 一致） */
export type ModelThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";
/**
 * 档位 → 上游 reasoning_effort 取值；`null` = 该档不支持（SDK thinkingLevelMap 语义）。
 * 缺省的档位（undefined）对 off~high 视为支持、对 xhigh/max 视为不支持。
 */
export type ModelThinkingLevelMap = Partial<Record<ModelThinkingLevel, string | null>>;

export interface CustomProviderModelInput {
	advanced?: ModelRequestOptions;
	id: string;
	name?: string;
	/** 支持思考/推理；缺省 SDK 按 false 处理（思考深度会被钳到 off） */
	reasoning?: boolean;
	/** 逐档思考力度映射；从 SDK 内置目录带出，缺省 = 只用 off~high */
	thinkingLevelMap?: ModelThinkingLevelMap;
	/** 上下文窗口 tokens；缺省 SDK 按 128000 */
	contextWindow?: number;
	/** 最大输出 tokens；缺省 SDK 按 16384 */
	maxTokens?: number;
	/** 支持图片输入；缺省仅文本 */
	imageInput?: boolean;
}

/** Validated request parameters persisted by the backend and used on every task. */
export interface ModelRequestOptions {
	toolCallLimit: number;
	reasoningParameter: string;
	reasoningValues: string[];
	temperature?: number;
	topP?: number;
	topK?: number;
}

export interface CustomProviderInput {
	template?: string;
	fullUrl?: boolean;
	id: string;
	name?: string;
	baseUrl: string;
	/** KnownApiId 之一 */
	api: string;
	models: CustomProviderModelInput[];
	/** 可选；保存进 auth.json（0600），不写进 models.json */
	apiKey?: string;
}

/** 更新自定义 provider：ID 为主键不可改；apiKey 留空 = 保持不变（删除凭证走行上的「移除凭证」/「删除」） */
export type CustomProviderUpdateInput = CustomProviderInput;

/** 上游 `/models` 返回的一条模型；能力字段由 SDK 内置目录补全，缺省 = 未知，跟随 SDK 默认 */
export interface UpstreamModelInfo {
	reasoningValues?: string[];
	id: string;
	name?: string;
	reasoning?: boolean;
	/** 从 SDK 内置目录带出的逐档思考力度映射（/models 本身不返回） */
	thinkingLevelMap?: ModelThinkingLevelMap;
	contextWindow?: number;
	maxTokens?: number;
	imageInput?: boolean;
}

/** 拉取上游模型清单的入参（providerId 只用于兜底已落盘的 baseUrl/api 与已存 key） */
export interface UpstreamModelsInput {
	template?: string;
	fullUrl?: boolean;
	providerId?: string;
	baseUrl: string;
	api: string;
	/** 表单里临时输入的 key；留空则由所属后端通过 SDK 解析该 provider 的已有凭证 */
	apiKey?: string;
}

/** 拉取结果：`baseUrl` 是实际可用的基址（站点根会被探测补成 `/v1`），表单据此回填 */
export interface UpstreamModelsResult {
	models: UpstreamModelInfo[];
	baseUrl: string;
}

export interface ProviderTestResult {
	ok: boolean;
	/** 失败原因（网络/鉴权等错误信息） */
	error?: string;
	/** 测试时实际使用的模型 */
	modelId?: string;
}
