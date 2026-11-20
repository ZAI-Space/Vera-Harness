/** UI stream protocol. Backend adapters translate their own events into these display DTOs. */
export interface CompactionPause {
	reason: "failed" | "still-over-threshold" | "nothing-to-compact" | "context-changed";
	errorMessage?: string;
	tokens?: number;
	contextWindow?: number;
	thresholdTokens?: number;
}
export interface Usage {
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	totalTokens: number;
	cost: { input: number; output: number; cacheRead: number; cacheWrite: number; total: number };
}
export type ContentPart =
	| { type: "text"; text: string }
	| { type: "thinking"; thinking: string; thinkingSignature?: string; redacted?: boolean }
	| { type: "image"; data: string; mimeType: string }
	| { type: "toolCall"; id: string; name: string; arguments: Record<string, unknown> };
export interface AssistantMessage {
	role: "assistant";
	content: ContentPart[];
	timestamp: number;
	api: string;
	provider: string;
	model: string;
	usage: Usage;
	stopReason: "stop" | "length" | "toolUse" | "error" | "aborted";
	errorMessage?: string;
	responseModel?: string;
	responseId?: string;
	durationMs?: number;
	diagnostics?: unknown[];
	providerThinkingLevel?: string;
}
export type StreamMessage =
	| AssistantMessage
	| { role: "user"; content: string | ContentPart[]; timestamp: number }
	| {
			role: "toolResult";
			content: ContentPart[];
			timestamp: number;
			toolCallId: string;
			toolName: string;
			isError: boolean;
			details?: unknown;
	  }
	| {
			role: "custom" | "bashExecution" | "compactionSummary" | "branchSummary";
			content: string | ContentPart[];
			timestamp: number;
			customType?: string;
			details?: unknown;
	  };
export type AssistantStreamUpdate =
	| { type: "start"; partial: AssistantMessage }
	| {
			type: "text_start" | "thinking_start" | "toolcall_start";
			contentIndex: number;
			partial: AssistantMessage;
	  }
	| {
			type: "text_delta" | "thinking_delta" | "toolcall_delta";
			contentIndex: number;
			delta: string;
			partial: AssistantMessage;
	  }
	| { type: "text_end" | "thinking_end"; contentIndex: number; content: string; partial: AssistantMessage }
	| {
			type: "toolcall_end";
			contentIndex: number;
			toolCall: Extract<ContentPart, { type: "toolCall" }>;
			partial: AssistantMessage;
	  }
	| { type: "done"; reason: "stop" | "length" | "toolUse"; message: AssistantMessage }
	| { type: "error"; reason: "error" | "aborted"; error: AssistantMessage };
export type AgentSessionEvent =
	| { type: "agent_start" | "turn_start" | "summarization_retry_finished" }
	| { type: "agent_end"; messages: StreamMessage[]; willRetry: boolean }
	| { type: "agent_settled"; aborted: boolean }
	| { type: "turn_end"; message: StreamMessage; toolResults: StreamMessage[] }
	| { type: "message_start" | "message_end"; message: StreamMessage }
	| { type: "message_update"; message: StreamMessage; assistantMessageEvent: AssistantStreamUpdate }
	| {
			type: "tool_execution_start";
			toolCallId: string;
			toolName: string;
			args: Record<string, unknown>;
			parentToolCallId?: string;
	  }
	| {
			type: "tool_execution_update";
			toolCallId: string;
			toolName: string;
			args: Record<string, unknown>;
			partialResult: unknown;
			parentToolCallId?: string;
	  }
	| {
			type: "tool_execution_end";
			toolCallId: string;
			toolName: string;
			result: unknown;
			isError: boolean;
			durationMs?: number;
			parentToolCallId?: string;
	  }
	| { type: "compaction_pause"; pause: CompactionPause | null }
	| { type: "queue_update"; steering: readonly string[]; followUp: readonly string[] }
	| { type: "compaction_start"; reason: "manual" | "threshold" | "overflow" }
	| {
			type: "compaction_end";
			reason: "manual" | "threshold" | "overflow";
			result:
				| { summary: string; firstKeptEntryId: string; tokensBefore: number; estimatedTokensAfter?: number }
				| undefined;
			aborted: boolean;
			willRetry: boolean;
			errorMessage?: string;
	  }
	| { type: "entry_appended"; entry: Record<string, unknown> }
	| { type: "session_info_changed"; name: string | undefined }
	| { type: "thinking_level_changed"; level: string }
	| {
			type: "auto_retry_start" | "summarization_retry_scheduled";
			attempt: number;
			maxAttempts: number;
			delayMs: number;
			errorMessage: string;
	  }
	| { type: "auto_retry_end"; success: boolean; attempt: number; finalError?: string }
	| {
			type: "summarization_retry_attempt_start";
			source: "branchSummary" | "compaction";
			reason?: "manual" | "threshold" | "overflow";
	  }
	| { type: "bash_execution_update"; id?: string; delta: string };
