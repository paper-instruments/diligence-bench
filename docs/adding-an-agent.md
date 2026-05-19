# Adding An Agent

v1 ships only `finance` in the public SandboxAgent registry, but the registry is
folder-based.

1. Create `src/diligence_bench/agents/<name>/`.
2. Add `system_prompt.md`.
3. Add optional `AGENTS.md` and `skills/<skill-name>/SKILL.md` files.
4. Implement `build_agent(workdir: Path) -> SandboxAgent` in the folder's
   `__init__.py`.
5. Register it in `src/diligence_bench/agents/__init__.py`.

Keep the builder model-agnostic. The runner attaches the requested model at
rollout time so the same agent folder can run across all benchmark variants.

Use the existing `finance` builder as the template for capabilities, MCP server
construction, and final-answer wiring.

Experimental CLI-agent runners live in `src/diligence_bench/cli_agents/`. They
still execute through `verifiers.v1.Harness`, but they are a separate comparison
surface from the v1 `SandboxAgent` contract.
