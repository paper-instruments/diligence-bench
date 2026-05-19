# Adding A Tool

MCP tools live under `src/diligence_bench/tools/<tool-name>/`.

1. Create `server.py` with a module-level `FastMCP` instance.
2. Register typed async tool functions with `@mcp.tool()`.
3. Add a `main()` that runs stdio transport.
4. Export `mcp_stdio_spec()` from the package `__init__.py`.
5. Register the spec in `src/diligence_bench/tools/__init__.py`.

Tool servers must be public and reproducible. Do not depend on private
services, private packages, or a separate sandbox pool. The agent already runs
inside Modal through the OpenAI Agents SDK.

Include any needed env vars in `.env.example`, the tool spec allowlist, and the
Harbor task template.
