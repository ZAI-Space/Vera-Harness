// @vitest-environment happy-dom
import { act, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useI18nStore } from "../../i18n";
import { AtMenu } from "./AtMenu";
import type { ComposerEditorHandle } from "./ComposerEditor";
import { useAtCompletion } from "./use-at-completion";

const fixture = vi.hoisted(() => ({ list: vi.fn(), insert: vi.fn(), focus: vi.fn() }));
vi.mock("../../environment-api", () => ({
	getExecutionApi: () => ({ listProjectFiles: fixture.list }),
}));

let host: HTMLDivElement;
let root: Root;
let completion: ReturnType<typeof useAtCompletion>;

/** 挂载真实补全 hook 与菜单，编辑器仅模拟引用与替换接口，验证搜索不改正文。 */
function Harness({ draftKey = "test" }: { draftKey?: string }) {
	const [text, setText] = useState("看 @");
	const editorRef = useRef<ComposerEditorHandle>({
		focus: fixture.focus,
		insertReference: fixture.insert,
		replaceText: () => {},
		selectionRange: () => ({ start: 3, end: 3 }),
		insertReferences: () => {},
	});
	editorRef.current.replaceText = (start, end, value) => {
		setText((previous) => previous.slice(0, start) + value + previous.slice(end));
	};
	completion = useAtCompletion({ cwd: "/project", text, draftKey, slashOpen: false, editorRef });
	return (
		<>
			<p data-draft="">{text}</p>
			{completion.atOpen && (
				<AtMenu
					files={completion.atFiltered}
					query={completion.atQuery}
					onQueryChange={completion.updateSearchQuery}
					onKeyDown={completion.handleKeyDown}
					selectedIndex={completion.atSelected}
					onSelectedIndexChange={completion.setAtSelected}
					onPick={completion.handleAtPick}
				/>
			)}
		</>
	);
}

beforeEach(async () => {
	vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
	useI18nStore.setState({ language: "zh" });
	fixture.list.mockResolvedValue([
		...Array.from({ length: 55 }, (_, index) => `file-${index}.ts`),
		"src/",
		"src/Composer.tsx",
		"src/file with spaces.ts",
	]);
	host = document.createElement("div");
	document.body.append(host);
	root = createRoot(host);
	await act(() => root.render(<Harness />));
	await act(async () => completion.updateToken("看 @", 3));
});

afterEach(async () => {
	await act(() => root.unmount());
	host.remove();
	vi.clearAllMocks();
	vi.unstubAllGlobals();
});

function searchInput() {
	const input = host.querySelector<HTMLInputElement>('input[type="search"]');
	if (!input) throw new Error("缺少文件搜索框");
	return input;
}

async function search(query: string) {
	const input = searchInput();
	await act(() => {
		Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, query);
		input.dispatchEvent(new Event("input", { bubbles: true }));
	});
}

async function key(value: string, isComposing = false) {
	await act(() => {
		searchInput().dispatchEvent(new KeyboardEvent("keydown", { key: value, isComposing, bubbles: true }));
	});
}

describe("@ 菜单顶部文件搜索", () => {
	it("搜索完整列表而非前 50 项，不改正文且不重复请求，回车插入正确引用", async () => {
		expect(completion.atFiltered).not.toContain("src/Composer.tsx");
		await search("Composer");
		expect(completion.atFiltered).toEqual(["src/Composer.tsx"]);
		expect(host.querySelector("[data-draft]")?.textContent).toBe("看 @");
		expect(fixture.list).toHaveBeenCalledOnce();
		await key("Enter", true);
		expect(fixture.insert).not.toHaveBeenCalled();
		await key("Enter");
		expect(fixture.insert).toHaveBeenCalledWith(2, 3, {
			type: "file",
			path: "/project/src/Composer.tsx",
			label: "src/Composer.tsx",
		});
	});

	it("无匹配时仍可编辑搜索，清空后恢复列表，支持含空格的文件名", async () => {
		await search("missing-file");
		expect(host.textContent).toContain("没有匹配的文件");
		expect(searchInput().value).toBe("missing-file");
		await search("");
		expect(completion.atFiltered).toHaveLength(50);
		await search("file with spaces");
		expect(completion.atFiltered).toEqual(["src/file with spaces.ts"]);
	});

	it("搜索目录后可继续进入目录，并从搜索框用键盘选择文件", async () => {
		await search("src");
		await key("Enter");
		expect(host.querySelector("[data-draft]")?.textContent).toBe("看 @src/");
		expect(searchInput().value).toBe("src/");
		expect(completion.atFiltered).not.toContain("src/");
		await key("ArrowUp");
		expect(completion.atSelected).toBe(0);
		await key("ArrowDown");
		expect(completion.atSelected).toBe(1);
		await key("Tab");
		expect(fixture.insert).toHaveBeenCalledWith(2, 7, expect.objectContaining({ type: "file" }));
	});

	it("Escape 返回正文且保留内容，切换草稿不会沿用旧搜索", async () => {
		await search("Composer");
		await key("Escape");
		expect(host.querySelector("input")).toBeNull();
		expect(fixture.focus).toHaveBeenCalledWith(3);
		expect(host.querySelector("[data-draft]")?.textContent).toBe("看 @");
		await act(() => root.render(<Harness draftKey="another" />));
		await act(async () => completion.updateToken("看 @", 3));
		expect(searchInput().value).toBe("");
		expect(completion.atFiltered).toHaveLength(50);
	});
});
