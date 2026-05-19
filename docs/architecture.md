# Architecture

`diligence-bench` is intentionally small: task generation, one reference
agent, one runner, and file-based results.

## Adapter

`diligence_bench.dataset` loads `tldc/diligence-bench` and normalizes each row
to:

```python
{
    "prompt": [{"role": "user", "content": "..."}],
    "info": {"datasetId": "...", "rubric": [...]},
}
```

`diligence_bench.harbor.DiligenceBenchAdapter` writes those rows as Harbor task
directories. `instruction.md` contains the prompt plus the final-answer
contract: write the memo to `/workspace/answer.md`. `tests/rubric.json`
contains the flattened criteria.

## Agent

The v1 reference agent is `finance`. It is an OpenAI Agents SDK
`SandboxAgent` with:

- finance system prompt
- five static `SKILL.md` files
- filesystem, shell, compaction, and skills capabilities
- SEC EDGAR and web search MCP stdio servers
- an SDK-native `final_answer` function tool

## Runner

The only eval path is `verifiers.v1.Harness`. The harness program builds the
finance `SandboxAgent`, creates a Modal sandbox session, runs `Runner.run`, and
then reads `/workspace/answer.md`. If the file is empty and the run called the
SDK `final_answer` tool, the runner writes that payload into
`/workspace/answer.md` before reading. A run with no file-backed answer is
recorded as an error rather than scored from model `final_output`.

The reward function calls the in-process rubric grader and stores:

- `state["reward"]`
- `state["judge_verdicts"]`
- `state["section_scores"]`

## Results

Per-example results are JSON files under:

```text
results/<run-id>/<agent-model-variant>/scores/<dataset-id>.json
```

Compact trajectories live beside them under `trajectories/`. Aggregate rows
are appended to `results/ablations.csv` with a stable column order.
