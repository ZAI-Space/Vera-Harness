/* The pairing secret stays in this tab's session storage; no external scripts or assets load. */
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get("token") || sessionStorage.getItem("vera-lan-token") || "";
if (token) sessionStorage.setItem("vera-lan-token", token);
history.replaceState(null, "", location.pathname);
const elements = Object.fromEntries(
	[
		"status",
		"sessions",
		"error",
		"messages",
		"permissions",
		"composer",
		"message",
		"readonly",
		"send",
		"stop",
	].map((id) => [id, document.getElementById(id)]),
);
let selected = "";
let writing = false;
let timer;
let previousMessages = "";
let previousPermissions = "";
let generation = 0;

async function request(path, body) {
	const response = await fetch(path, {
		method: body ? "POST" : "GET",
		headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
		...(body ? { body: JSON.stringify(body) } : {}),
	});
	const value = await response.json();
	if (!response.ok) throw new Error(value.error || "连接失败，请重新从电脑获取访问链接。");
	return value;
}

async function action(method, extra = {}) {
	if (writing) return;
	writing = true;
	elements.send.disabled = true;
	elements.stop.disabled = true;
	try {
		await request("/api/action", { method, sessionId: selected, ...extra });
		if (method === "prompt") elements.message.value = "";
		elements.error.textContent = "";
	} catch (failure) {
		elements.error.textContent = failure.message;
	} finally {
		writing = false;
		elements.send.disabled = false;
		elements.stop.disabled = false;
	}
}

/** Reconcile by content so polling does not reset reading position or keyboard focus. */
function render(value) {
	const selection = elements.sessions.value;
	const names = value.sessions
		.map((session) => `${session.sessionId}:${session.name}:${session.active}`)
		.join("|");
	if (elements.sessions.dataset.names !== names) {
		elements.sessions.replaceChildren(
			...value.sessions.map((session) => {
				const option = document.createElement("option");
				option.value = session.sessionId;
				option.textContent = `${session.active ? "运行中 · " : ""}${session.name}`;
				return option;
			}),
		);
		elements.sessions.dataset.names = names;
		elements.sessions.value = selection || value.sessionId || "";
	}
	selected = value.sessionId || "";
	elements.sessions.value = selected;
	elements.status.textContent = value.remoteControl ? "已连接 · 可远程控制" : "已连接 · 只读";
	elements.composer.hidden = !value.remoteControl || !selected;
	elements.readonly.hidden = value.remoteControl;
	const content = JSON.stringify(value.messages);
	if (content !== previousMessages) {
		previousMessages = content;
		elements.messages.replaceChildren(
			...value.messages.map((message) => {
				const article = document.createElement("article");
				article.className = message.kind;
				const label = document.createElement("strong");
				label.textContent = message.kind === "user" ? "你" : message.kind === "system" ? "系统" : "VERA";
				const text = document.createElement("p");
				text.textContent = message.text;
				article.append(label, text);
				for (const tool of message.tools) {
					const details = document.createElement("details");
					const summary = document.createElement("summary");
					summary.textContent = tool.name;
					const output = document.createElement("pre");
					output.textContent = tool.output;
					details.append(summary, output);
					article.append(details);
				}
				return article;
			}),
		);
	}
	const permissionState = JSON.stringify([value.remoteControl, value.permissions]);
	if (permissionState !== previousPermissions) {
		previousPermissions = permissionState;
		elements.permissions.replaceChildren();
		for (const permission of value.permissions) {
			const card = document.createElement("article");
			const title = document.createElement("strong");
			title.textContent = permission.title;
			const description = document.createElement("pre");
			description.textContent = permission.message;
			card.append(title, description);
			if (value.remoteControl)
				for (const [answer, label] of [
					["allow", "允许一次"],
					["deny", "拒绝"],
				]) {
					const button = document.createElement("button");
					button.textContent = label;
					button.onclick = () => void action("respondPermission", { requestId: permission.id, answer });
					card.append(button);
				}
			elements.permissions.append(card);
		}
	}
	if (!selected) elements.messages.textContent = "电脑端尚无会话，请先在电脑上打开会话。";
}

async function refresh() {
	clearTimeout(timer);
	const requestId = ++generation;
	try {
		const value = await request(
			`/api/snapshot${selected ? `?sessionId=${encodeURIComponent(selected)}` : ""}`,
		);
		if (requestId === generation) render(value);
	} catch (failure) {
		if (requestId === generation) {
			elements.status.textContent = "连接中断";
			elements.error.textContent = failure.message;
			elements.composer.hidden = true;
		}
	} finally {
		if (requestId === generation) timer = setTimeout(refresh, 2000);
	}
}
elements.sessions.onchange = () => {
	selected = elements.sessions.value;
	void refresh();
};
elements.composer.onsubmit = (event) => {
	event.preventDefault();
	if (elements.message.value.trim()) void action("prompt", { text: elements.message.value });
};
elements.stop.onclick = () => void action("abort");
void refresh();
