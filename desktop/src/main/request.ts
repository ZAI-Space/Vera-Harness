import { CHANNEL_TABLE } from "@vera/contracts";

export interface DesktopRequest {
	method: keyof typeof CHANNEL_TABLE;
	args: unknown;
}

/** 校验桥接方法与载荷；业务参数复用契约，桌面请求接受单对象或无参。 */
export function validateDesktopRequest(value: unknown): DesktopRequest {
	if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid desktop request");
	const request = value as Record<string, unknown>;
	if (typeof request.method !== "string" || !Object.hasOwn(CHANNEL_TABLE, request.method))
		throw new Error("Unknown desktop method");
	const method = request.method as DesktopRequest["method"];
	const definition = CHANNEL_TABLE[method];
	if (definition.scope === "environment") definition.validate(request.args);
	else if (
		request.args !== undefined &&
		(!request.args || typeof request.args !== "object" || Array.isArray(request.args))
	)
		throw new Error("Invalid desktop arguments");
	return { method, args: request.args };
}
