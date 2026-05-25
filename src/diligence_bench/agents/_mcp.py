"""Shared MCPServerStdio construction for agent builders."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, cast

from agents.mcp import MCPServerStdioParams

from diligence_bench.tools import TOOLS


def tool_spec(tool_id: str) -> Mapping[str, Any]:
    spec_factory = TOOLS[tool_id]
    spec = spec_factory() if callable(spec_factory) else spec_factory
    if not isinstance(spec, Mapping):
        raise TypeError(f"MCP tool registry entry {tool_id!r} must return a mapping")
    return spec


def mcp_stdio_params(tool_id: str, spec: Mapping[str, Any]) -> MCPServerStdioParams:
    raw_params = spec.get("params")
    if raw_params is not None:
        if not isinstance(raw_params, Mapping):
            raise TypeError(f"MCP tool {tool_id!r} spec.params must be a mapping")
        return cast(MCPServerStdioParams, dict(raw_params))

    command = spec.get("command", spec.get("launch_cmd"))
    if not isinstance(command, str) or not command:
        raise ValueError(f"MCP tool {tool_id!r} requires command or launch_cmd")

    args = spec.get("args", spec.get("launch_args", []))
    if args is None:
        args = []
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ValueError(f"MCP tool {tool_id!r} args must be a list[str]")

    params: dict[str, Any] = {"command": command, "args": args}
    env = spec.get("env")
    if env is not None:
        if not isinstance(env, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in env.items()
        ):
            raise ValueError(f"MCP tool {tool_id!r} env must be a dict[str, str]")
        params["env"] = dict(env)
    elif spec.get("env_allowlist") is not None:
        params["env"] = _allowlisted_env(tool_id, spec["env_allowlist"])

    return cast(MCPServerStdioParams, params)


def _allowlisted_env(tool_id: str, raw_allowlist: object) -> dict[str, str]:
    if not isinstance(raw_allowlist, list) or not all(
        isinstance(key, str) for key in raw_allowlist
    ):
        raise ValueError(f"MCP tool {tool_id!r} env_allowlist must be a list[str]")
    keys = [key for key in raw_allowlist if isinstance(key, str)]
    return {key: os.environ[key] for key in keys if key in os.environ}


__all__ = ["tool_spec", "mcp_stdio_params"]
