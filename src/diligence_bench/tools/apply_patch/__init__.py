"""Function-tool wrapper for the SDK's ``apply_patch`` editor.

The SDK ships ``SandboxApplyPatchTool`` as a freeform/custom-grammar tool, which
only works with the OpenAI Responses API; the Chat Completions API rejects it
("Hosted tools are not supported"). Providers that only speak Chat Completions
(OpenRouter, Anthropic via OpenAI shim, etc.) therefore can't use the SDK's
default Filesystem capability as-is.

This module exposes the same parser + editor as a plain function tool. The
underlying ``SandboxApplyPatchEditor`` is reused verbatim, so behavior is 1:1
with the hosted version. Session lookup happens via the run context, since the
sandbox is created after the agent is built.
"""

from __future__ import annotations

import logging
from typing import Any

from agents import RunContextWrapper, function_tool
from agents.sandbox.capabilities.tools.apply_patch_tool import (
    _APPLY_PATCH_CUSTOM_TOOL_DESCRIPTION,
    SandboxApplyPatchEditor,
    _parse_custom_tool_input,
)

APPLY_PATCH_TOOL_NAME = "apply_patch"

logger = logging.getLogger(__name__)


@function_tool(
    name_override=APPLY_PATCH_TOOL_NAME,
    description_override=_APPLY_PATCH_CUSTOM_TOOL_DESCRIPTION,
)
async def apply_patch(ctx: RunContextWrapper[Any], input: str) -> str:
    sandbox = getattr(ctx.context, "sandbox", None)
    if sandbox is None:
        logger.warning("apply_patch called without a sandbox in context")
        return "Error: sandbox unavailable"

    editor = SandboxApplyPatchEditor(sandbox)
    outputs: list[str] = []
    for op in _parse_custom_tool_input(input):
        if op.type == "create_file":
            result = await editor.create_file(op)
        elif op.type == "update_file":
            result = await editor.update_file(op)
        elif op.type == "delete_file":
            result = await editor.delete_file(op)
        else:
            raise ValueError(f"Unsupported apply_patch operation: {op.type}")
        if result.output:
            outputs.append(result.output)
    return "\n".join(outputs)


__all__ = ["APPLY_PATCH_TOOL_NAME", "apply_patch"]
