"""Structured trace capture for OpenAI Agents SDK runs.

Registers a TracingProcessor that converts SDK spans into clean JSON-serializable
dicts. Replaces the previous approach of repr()-ing RunItem objects.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class SpanCollector:
    """TracingProcessor that collects structured span data in memory.

    Usage::

        collector = SpanCollector()
        collector.install()
        try:
            result = await Runner.run(agent, ...)
        finally:
            collector.uninstall()
        trajectory = collector.spans
    """

    def __init__(self) -> None:
        self._spans: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._active = False

    @property
    def spans(self) -> list[dict[str, Any]]:
        return list(self._spans)

    def install(self) -> None:
        from agents import add_trace_processor

        self._active = True
        add_trace_processor(self)

    def uninstall(self) -> None:
        self._active = False

    def on_trace_start(self, trace: Any) -> None:
        pass

    def on_trace_end(self, trace: Any) -> None:
        pass

    def on_span_start(self, span: Any) -> None:
        pass

    def on_span_end(self, span: Any) -> None:
        if not self._active:
            return
        exported = span.export()
        if not exported:
            return
        record = _span_to_record(exported)
        if record:
            with self._lock:
                self._spans.append(record)

    def force_flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def _span_to_record(exported: dict[str, Any]) -> dict[str, Any] | None:
    span_data = exported.get("span_data", {})
    span_type = span_data.get("type", "")

    if span_type == "function":
        return _function_record(exported, span_data)
    if span_type in ("response", "generation"):
        return _llm_record(exported, span_data)
    if span_type == "agent":
        return _agent_record(exported, span_data)
    return None


def _function_record(exported: dict[str, Any], span_data: dict[str, Any]) -> dict[str, Any]:
    output_raw = span_data.get("output")
    if isinstance(output_raw, list):
        output = _extract_mcp_text(output_raw)
    elif output_raw is not None:
        output = str(output_raw)
    else:
        output = ""

    return {
        "type": "tool_call",
        "name": span_data.get("name", ""),
        "input": span_data.get("input", ""),
        "output": output,
        "call_id": _extract_call_id(exported),
        "started_at": exported.get("started_at"),
        "ended_at": exported.get("ended_at"),
        "error": _extract_error(exported),
        "mcp_data": span_data.get("mcp_data"),
    }


def _llm_record(exported: dict[str, Any], span_data: dict[str, Any]) -> dict[str, Any]:
    usage = span_data.get("usage") or {}
    output_messages = span_data.get("output")

    content = ""
    if isinstance(output_messages, list):
        for msg in output_messages:
            if isinstance(msg, dict):
                c = msg.get("content", "")
                if isinstance(c, str) and c:
                    content = c
                    break
                if isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and part.get("type") == "output_text":
                            content = part.get("text", "")
                            break
                    if content:
                        break

    return {
        "type": "message",
        "content": content,
        "model": span_data.get("model", ""),
        "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
        "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens"),
        "started_at": exported.get("started_at"),
        "ended_at": exported.get("ended_at"),
        "error": _extract_error(exported),
    }


def _agent_record(exported: dict[str, Any], span_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "agent",
        "name": span_data.get("name", ""),
        "tools": span_data.get("tools"),
        "handoffs": span_data.get("handoffs"),
        "started_at": exported.get("started_at"),
        "ended_at": exported.get("ended_at"),
    }


def _extract_mcp_text(output_list: list[Any]) -> str:
    parts = []
    for item in output_list:
        if isinstance(item, dict):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif "text" in item:
                parts.append(str(item["text"]))
    return "\n".join(parts) if parts else str(output_list)


def _extract_call_id(exported: dict[str, Any]) -> str:
    span_id = exported.get("id", "")
    if isinstance(span_id, str) and span_id.startswith("span_"):
        return span_id
    return span_id or ""


def _extract_error(exported: dict[str, Any]) -> str | None:
    error = exported.get("error")
    if not error:
        return None
    if isinstance(error, dict):
        return error.get("message") or str(error)
    return str(error)
