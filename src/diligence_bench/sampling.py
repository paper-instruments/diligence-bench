"""Sampling-policy registry for agent rollouts.

Closed-lab models (OpenAI, Anthropic, Google) share one default policy so
cross-model numbers are comparable. Open-weight models follow their system-card
recommendation via ``MODEL_OVERRIDES`` keyed by the model id prefix. CLI flags
can still override anything per run.

The resolved policy is logged at run start and stamped into ``ablations.csv``
so every result row carries the config that produced it.

``max_tokens`` is intentionally not part of the policy: reasoning models count
thinking tokens against it, so a single cap either starves visible output at
high effort or removes the cost ceiling we wanted. We rely on provider
defaults instead.

``top_p`` is also not pinned at the policy level. Closed-lab providers
effectively run at 1.0 (no nucleus filter) when omitted; Gemini applies its
own server-side default (~0.95). Pinning would override Google's tuning.
Per-model overrides may still set it (open-weight families do).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Literal

logger = logging.getLogger(__name__)

ReasoningEffort = Literal["minimal", "low", "medium", "high"]
Verbosity = Literal["low", "medium", "high"]

DEFAULT_TEMPERATURE: float = 1.0
DEFAULT_REASONING_EFFORT: ReasoningEffort = "medium"
DEFAULT_VERBOSITY: Verbosity = "medium"

_OVERRIDABLE_FIELDS = (
    "temperature",
    "reasoning_effort",
    "verbosity",
    "top_p",
    "top_k",
    "min_p",
    "presence_penalty",
    "repetition_penalty",
)


@dataclass(frozen=True)
class SamplingPolicy:
    """Resolved sampling settings for a single model rollout.

    Fields default to ``None`` mean "do not send to the provider" — the
    provider's own default applies. ``temperature`` and ``reasoning_effort``
    are pinned to a shared closed-lab value for cross-model comparability.
    """

    temperature: float = DEFAULT_TEMPERATURE
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT
    verbosity: Verbosity = DEFAULT_VERBOSITY
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    repetition_penalty: float | None = None

    def describe(self) -> str:
        parts = [
            f"temperature={self.temperature}",
            f"reasoning_effort={self.reasoning_effort}",
            f"verbosity={self.verbosity}",
        ]
        for name in ("top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty"):
            value = getattr(self, name)
            if value is not None:
                parts.append(f"{name}={value}")
        return " ".join(parts)


# Per-model overrides keyed by case-insensitive prefix of the model id.
# Each entry mirrors the model's published system-card recommendation.
MODEL_OVERRIDES: dict[str, dict[str, Any]] = {
    # Qwen3.5-397B-A17B thinking mode (Qwen team recommendation).
    "qwen/qwen3.5-397b-a17b": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
    },
    # MiniMax M3 (vendor card: temp 1.0, top_p 0.95).
    "minimax/minimax-m3": {
        "temperature": 1.0,
        "top_p": 0.95,
    },
    # Kimi K2.6 thinking mode (Moonshot model card: temp 1.0, top_p 0.95).
    "moonshotai/kimi-k2.6": {
        "temperature": 1.0,
        "top_p": 0.95,
    },
    # GLM-5.1 (Z.AI default: temp 1.0, top_p 0.95).
    "z-ai/glm-5.1": {
        "temperature": 1.0,
        "top_p": 0.95,
    },
    # GLM-5.2 (Z.AI default: temp 1.0, top_p 0.95).
    "z-ai/glm-5.2": {
        "temperature": 1.0,
        "top_p": 0.95,
    },
}


def resolve_sampling(
    model: str,
    *,
    cli_overrides: dict[str, Any] | None = None,
) -> SamplingPolicy:
    """Resolve the policy for ``model``: defaults < model overrides < CLI overrides."""

    policy = SamplingPolicy()
    for prefix, override in MODEL_OVERRIDES.items():
        if model.lower().startswith(prefix.lower()):
            policy = replace(policy, **_filter_known_fields(override))
            break
    if cli_overrides:
        policy = replace(policy, **_filter_known_fields(cli_overrides))
    return policy


def build_model_settings(
    model: str,
    policy: SamplingPolicy,
    model_settings_cls: Any,
) -> Any:
    """Translate a ``SamplingPolicy`` into a ``ModelSettings`` instance.

    Wire-level encoding:

    - ``temperature`` and ``top_p`` go on ``ModelSettings`` directly when set.
      OpenRouter forwards each only to providers whose ``supported_parameters``
      includes them (closed-lab reasoning models drop both; Sonnet/Haiku/Gemini
      accept; open-weight families accept all sampling fields).
    - Reasoning effort goes through ``ModelSettings.reasoning.effort``, which
      the Agents SDK extracts and sends as Chat Completions' top-level
      ``reasoning_effort``. OpenRouter accepts that and translates per provider
      (OpenAI: ``reasoning_effort``; Anthropic 4.6 and Haiku 4.5: budget mode;
      Google: ``thinking_config.thinking_budget``). On Claude Opus 4.7/4.8 the
      ``reasoning_effort`` route is accepted but ignored — those models run
      adaptive thinking and want ``output_config.effort`` instead, which
      OpenRouter exposes via the ``verbosity`` field (below).
      We do *not* duplicate the effort into ``extra_body.reasoning`` because
      OpenRouter rejects conflicting values across the two forms (400) and
      having one source of truth removes that fragility.
    - ``verbosity`` goes on ``ModelSettings`` directly. OpenRouter forwards it
      to OpenAI's native ``verbosity`` field and translates to Anthropic's
      ``output_config.effort`` for Claude routes — the only way to pin
      effort on Opus 4.7/4.8. Models that don't accept it (Gemini, Haiku 4.5,
      open-weight) silently drop it.
    - ``top_k``, ``min_p``, ``presence_penalty``, ``repetition_penalty`` are
      open-weight knobs not in ``ModelSettings``; they ride along through
      ``extra_body`` when set by a model override.
    - OpenRouter routes pin the provider preference to Bedrock for stable
      pricing across runs.
    """

    extra_body: dict[str, Any] = {}
    if "/" in model:
        extra_body["provider"] = {
            "order": ["Bedrock"],
            "allow_fallbacks": True,
        }
    for name in ("top_k", "min_p", "presence_penalty", "repetition_penalty"):
        value = getattr(policy, name)
        if value is not None:
            extra_body[name] = value

    return model_settings_cls(
        temperature=policy.temperature,
        top_p=policy.top_p,
        reasoning={"effort": policy.reasoning_effort},
        verbosity=policy.verbosity,
        extra_body=extra_body or None,
    )


def _filter_known_fields(override: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in override.items() if key in _OVERRIDABLE_FIELDS}


__all__ = [
    "DEFAULT_REASONING_EFFORT",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_VERBOSITY",
    "MODEL_OVERRIDES",
    "ReasoningEffort",
    "SamplingPolicy",
    "Verbosity",
    "build_model_settings",
    "resolve_sampling",
]
