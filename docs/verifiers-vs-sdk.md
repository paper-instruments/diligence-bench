# Verifiers And The SDK

This repo uses both `verifiers.v1` and the OpenAI Agents SDK, but they have
different jobs.

`verifiers.v1.Harness` owns benchmark orchestration:

- task and state shape
- rollout lifecycle
- reward function execution
- compatibility with verifiers tooling

The OpenAI Agents SDK owns agent execution:

- `SandboxAgent`
- capabilities
- MCP servers and function tools
- `Runner.run`
- Modal sandbox sessions

The split keeps one eval runner path while still using the SDK-native agent
surface. There is no `StatefulToolEnv`, no DeepAgents runner, and no custom
harness protocol in this repo.
