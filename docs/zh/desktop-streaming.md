[English](../desktop-streaming.md) · [简体中文](desktop-streaming.md)

# 桌面流式呈现

!!! abstract "区分模型增量与展示动画"

    桌面在收到模型增量时更新正文，平滑动画控制已收到文字的展示节奏。思考区域仅显示服务商返回的可展示内容。

## 设计参考

呈现设计参考 PI-Desktop 版本 `f589deec80b4be928146db0eca74e6f3f5e4e4b0`。组件来源与许可证见桌面的第三方声明。

| 上游实现 | 实际规则 | VERA 接入方式 |
| --- | --- | --- |
| [AssistantTurnParts](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/features/chat/transcript/AssistantTurnParts.tsx) | 正文片段与过程活动分开，保留先后顺序 | 复用 Markdown、MetaGroup 与工具卡 |
| [活动折叠](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/lib/activity-group-folding.ts) | 生成中的思考展开，结束后折叠，用户手动选择优先 | 自动展开默认值与明确的手动开合分开 |
| [思考可见性](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/lib/thinking-visibility.ts) | 思考可见性属于展示偏好，与整个过程的折叠分开 | 思考单独显示；等待响应不标成实际思考内容 |
| [平滑文字](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/hooks/useSmoothText.ts) | 自适应释放、限制视觉延迟、尊重减少动效设置 | 保留已有增量 Markdown 与平滑呈现 |
| [流式合流](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/packages/agent-runtime/src/stream-coalescer.ts) | 合并高频更新，语义边界先冲刷再发送 | 复用 renderer EventConflator，按帧更新且不打乱边界 |
| [阅读位置](https://github.com/vastsa/PI-Desktop/blob/f589deec80b4be928146db0eca74e6f3f5e4e4b0/apps/desktop/src/lib/transcript-scroll.ts) | 向上阅读后停止跟随底部，回到底部后恢复 | 保留现有消息列表阅读位置机制 |

## 事件链路

```text
服务商 SSE → 桌面流式模型适配器 → worker JSON 事件
→ 带认证的回环事件缓冲 → Electron main/preload
→ EventConflator → transcript reducer → 正文 / 思考 / 工具卡
```

桌面选择已有 LiteLLM 模型的流式子类。Chat Completions 经 LiteLLM 统一 OpenAI 兼容、Anthropic 和 Gemini；Responses 使用原生响应事件。增量汇总为完整服务商响应后，仍交给原有动作解析、费用统计、工具校验与运行存储。Agent Loop 不变。

每条模型回复开启一个轮次，正文与可展示思考分别追加；工具参数片段不执行。完整工具调用经校验后，在 confirm 模式下等待对应审批。工具结果先回传，再结束轮次。稳定的消息标识避免结束时重播整段回复。

后端保留用于重连的实时展示投影。停止后，已收到的文字保留在历史中，部分工具参数始终只用于展示。缺少完成记录时返回错误。不透明签名与加密推理内容保留用于服务商上下文回放，思考面板显示服务商提供的可读内容。

## 回归测试

- `tests/run/test_desktop_streaming.py`：本机 HTTP SSE 服务在发送完整回复前暂停，此时后端必须已暴露正文和思考，随后验证完整工具与用量；另一项测试验证完成前中止。
- `desktop/tests/contracts/transcript/harness.integration.test.ts`：实际 Python worker 执行 Bash，TypeScript 消费其事件，验证思考、正文、工具完成和空闲状态。

在 `desktop/` 执行 `npm run test:ui` 运行桌面交互测试。环境与命令见[测试文档](testing.md)。
