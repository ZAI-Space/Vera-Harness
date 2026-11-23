"""Stream provider output while retaining the base model's parsing and receipts.

Only the desktop worker chooses these adapters. The shared Agent Loop is unchanged.
Provider text, visible reasoning and argument fragments are forwarded on arrival;
the completed response uses the configured accounting and completion policy.
"""

import json
import time
from uuid import uuid4

import litellm

from vera.desktop.protocol import send
from vera.models.litellm_model import LitellmModel
from vera.models.litellm_response_model import LitellmResponseModel


class StreamBlocks:
    """Assign content indices in arrival order, keeping interleaved tools distinct."""

    def __init__(self):
        self.blocks = {}
        self.calls = {}
        send("stream_start")

    def delta(self, key, kind, text, *, call_id="", name=""):
        if key not in self.blocks:
            self.blocks[key] = len(self.blocks)
            if kind == "toolcall_delta":
                self.calls[key] = {"id": call_id, "name": name, "arguments": ""}
                send(
                    "stream_delta",
                    update={"type": "toolcall_start", "contentIndex": self.blocks[key]},
                    call=self.calls[key],
                )
        if kind == "toolcall_delta":
            call = self.calls[key]
            call["id"] = call_id or call["id"]
            call["name"] += name if name and name != call["name"] else ""
            call["arguments"] += text or ""
        if text:
            send("stream_delta", update={"type": kind, "contentIndex": self.blocks[key], "delta": text})

    def finish(self):
        """Only complete, validated action arguments can later be executed."""
        for key, call in self.calls.items():
            try:
                arguments = json.loads(call["arguments"])
            except json.JSONDecodeError:
                arguments = {}
            send(
                "stream_delta",
                update={
                    "type": "toolcall_end",
                    "contentIndex": self.blocks[key],
                    "toolCall": {"type": "toolCall", **call, "arguments": arguments},
                },
            )


class DesktopUsage:
    """Report every consumed response once, even when later format validation rejects it."""

    def query(self, messages, **kwargs):
        """Reset attempt observation per model turn without changing its retry policy."""
        self._desktop_attempts = 0
        return super().query(messages, **kwargs)

    def _stream_blocks(self):
        self._desktop_attempts = getattr(self, "_desktop_attempts", 0) + 1
        if self._desktop_attempts > 1:
            send("retry", reason="model")
        self._desktop_request_id = uuid4().hex
        send("model_request", id=self._desktop_request_id)
        return StreamBlocks()

    def _calculate_cost(self, response):
        counters = super()._calculate_cost(response)
        if counters.get("usage_reported"):
            identifier = uuid4().hex
            counters["usage_id"] = identifier
            provider, _, model = self.config.model_name.partition("/")
            identity = self.config.usage_identity or {"provider": provider, "modelId": model}
            send(
                "usage",
                id=identifier,
                message={
                    "timestamp": int(time.time() * 1000),
                    "usageReported": True,
                    "usage": counters["usage"],
                    "provider": identity["provider"],
                    "model": identity["modelId"],
                    "requestId": self._desktop_request_id,
                },
            )
        return counters


class StreamingChatModel(DesktopUsage, LitellmModel):
    """Use LiteLLM's normalized Chat stream for OpenAI, Anthropic and Gemini."""

    def _query(self, messages, **kwargs):
        blocks = self._stream_blocks()
        chunks = []
        stream = None
        try:
            stream = super()._query(messages, **(kwargs | {"stream": True, "stream_options": {"include_usage": True}}))
            for chunk in stream:
                chunks.append(chunk)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    blocks.delta("thinking", "thinking_delta", reasoning)
                if delta.content:
                    blocks.delta("text", "text_delta", delta.content)
                for call in delta.tool_calls or []:
                    function = call.function
                    blocks.delta(
                        ("tool", call.index),
                        "toolcall_delta",
                        function.arguments or "",
                        call_id=call.id or "",
                        name=function.name or "",
                    )
            if not chunks:
                raise ValueError("Provider returned an empty stream.")
            response = litellm.stream_chunk_builder(chunks, messages=messages)
            blocks.finish()
            return response
        except Exception as error:
            send("model_failure", category=type(error).__name__)
            raise
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()


class StreamingResponsesModel(DesktopUsage, LitellmResponseModel):
    """Preserve Responses reasoning items/signatures in the final provider object."""

    def _query(self, messages, **kwargs):
        blocks = self._stream_blocks()
        response = None
        stream = None
        try:
            stream = super()._query(messages, **(kwargs | {"stream": True}))
            for event in stream:
                value = event.model_dump() if hasattr(event, "model_dump") else dict(event)
                kind = value.get("type")
                if kind == "response.output_text.delta":
                    blocks.delta(("text", value.get("output_index", 0)), "text_delta", value.get("delta", ""))
                elif kind in {"response.reasoning_summary_text.delta", "response.reasoning_text.delta"}:
                    blocks.delta(("thinking", value.get("output_index", 0)), "thinking_delta", value.get("delta", ""))
                elif kind == "response.output_item.added" and value.get("item", {}).get("type") == "function_call":
                    item = value["item"]
                    blocks.delta(
                        ("tool", value["output_index"]),
                        "toolcall_delta",
                        item.get("arguments", ""),
                        call_id=item["call_id"],
                        name=item["name"],
                    )
                elif kind == "response.function_call_arguments.delta":
                    blocks.delta(("tool", value["output_index"]), "toolcall_delta", value.get("delta", ""))
                elif kind in {"response.completed", "response.incomplete"}:
                    from litellm.types.llms.openai import ResponsesAPIResponse

                    response = ResponsesAPIResponse(**value["response"])
                elif kind in {"response.failed", "error"}:
                    raise ValueError("Provider reported a failed response stream.")
            if response is None:
                raise ValueError("Provider stream ended without a final response.")
            blocks.finish()
            return response
        except Exception as error:
            send("model_failure", category=type(error).__name__)
            raise
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
