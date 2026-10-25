"""Current Bedrock Converse models, shared with the UI through /api/models/list.

Official model cards and the verification date are recorded in docs/bedrock-models.md.
The catalog deliberately excludes legacy models and non-text inference APIs.
"""
from copy import deepcopy
import os
from typing import Any

DEFAULT_MODEL_ID = "global.anthropic.claude-opus-5-5"


def _model(
    name: str, label: str, category: str, max_tokens: int, *,
    sampling: bool = True, reasoning: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0 if sampling else 1,
                "max": 1,
                "default": 0.5 if sampling else 1,
                "current": 0.5 if sampling else 1,
            },
            "maxTokens": {
                "min": 1, "max": max_tokens, "default": 4096, "current": 4096
            },
        },
        "isNew": True,
        "category": category,
        "supportsReasoning": reasoning,
    }


BEDROCK_MODELS = [
    _model("global.anthropic.claude-opus-5-5", "Claude Opus 5.5", "Anthropic", 128000, sampling=False, reasoning=True),
    _model("global.anthropic.claude-sonnet-5-5", "Claude Sonnet 5.5", "Anthropic", 128000, sampling=False, reasoning=True),
    _model("global.anthropic.claude-haiku-5-5", "Claude Haiku 5.5", "Anthropic", 128000, sampling=False, reasoning=True),
    _model("global.anthropic.claude-fable-5-1", "Claude Fable 5.1", "Anthropic", 128000, sampling=False, reasoning=True),
    _model("global.openai.gpt-6.1-sol", "GPT-6.1 Sol", "OpenAI", 131072, sampling=False, reasoning=True),
    _model("global.openai.gpt-6-astra", "GPT-6 Astra", "OpenAI", 128000, sampling=False, reasoning=True),
    _model("global.openai.gpt-6-luna", "GPT-6 Luna", "OpenAI", 128000, sampling=False, reasoning=True),
    # Conservative application limits; these are not the providers' context windows.
    _model("global.xai.grok-4.7", "Grok 4.7", "xAI", 32768, sampling=False, reasoning=True),
    _model("global.moonshotai.kimi-k3", "Kimi K3", "Moonshot AI", 32768, sampling=False, reasoning=True),
]

# Only documented geographic inference profiles are accepted. Region selection remains
# an independent server setting; a profile must be available from the chosen region.
_PROFILE_PREFIXES = {
    "global.anthropic.claude-sonnet-5-5": ("global", "us", "eu", "au"),
    "global.anthropic.claude-opus-5-5": ("global", "us", "eu", "au", "jp"),
    "global.anthropic.claude-haiku-5-5": ("global", "us", "eu", "au", "jp"),
    "global.anthropic.claude-fable-5-1": ("global", "us"),
    "global.openai.gpt-6.1-sol": ("global", "us"),
    "global.openai.gpt-6-astra": ("global", "us"),
    "global.openai.gpt-6-luna": ("global", "us"),
    "global.xai.grok-4.7": ("global", "us"),
    "global.moonshotai.kimi-k3": ("global", "us", "in"),
}
MODEL_ALIASES: dict[str, dict[str, Any]] = {}
for _entry in BEDROCK_MODELS:
    _name = _entry["name"]
    MODEL_ALIASES[_name] = _entry
    for _prefix in _PROFILE_PREFIXES.get(_name, ()):
        MODEL_ALIASES[f"{_prefix}.{_name.split('.', 1)[1]}"] = _entry
# Opus 5.5 also has documented in-region inference in eu-west-2.
MODEL_ALIASES["anthropic.claude-opus-5-5"] = MODEL_ALIASES[DEFAULT_MODEL_ID]


def normalize_model_name(name: str) -> str:
    normalized = name.removeprefix("bedrock/")
    if normalized not in MODEL_ALIASES:
        raise ValueError("Unsupported model. Choose a model from the current model catalog.")
    return normalized


def get_default_model_name() -> str:
    return normalize_model_name(
        os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID
    )


def get_model_definition(name: str) -> dict[str, Any]:
    name = normalize_model_name(name)
    definition = deepcopy(MODEL_ALIASES[name])
    definition["name"] = name
    return definition


def get_base_model_name(name: str) -> str:
    """Resolve aliases from the catalog, including profiles newer than the SDK."""
    canonical = MODEL_ALIASES[normalize_model_name(name)]["name"]
    return canonical.removeprefix("global.")


def get_model_catalog() -> dict[str, Any]:
    """Keep the existing API shape, including configured geographic defaults."""
    default_name = get_default_model_name()
    models = deepcopy(BEDROCK_MODELS)
    if default_name not in {model["name"] for model in models}:
        models.insert(0, get_model_definition(default_name))
    return {
        "models": models,
        "defaultModelName": default_name,
        "defaultModelConfig": get_model_definition(default_name)["config"],
    }


ALL_MODELS = BEDROCK_MODELS
DEFAULT_MODEL_NAME = get_default_model_name()
DEFAULT_MODEL_CONFIG = get_model_definition(DEFAULT_MODEL_NAME)["config"]
TEMPERATURE_EXCLUDED_MODELS = [
    name for name, model in MODEL_ALIASES.items()
    if model["config"]["temperatureRange"]["min"] == model["config"]["temperatureRange"]["max"]
]
NON_STREAMING_TOOL_CALLING_MODELS: list[str] = []
NON_STREAMING_TEXT_MODELS: list[str] = []
THINKING_MODELS = [
    name for name, model in MODEL_ALIASES.items() if model["supportsReasoning"]
]
REASONING_HISTORY_EXCLUDED_MODELS = [
    name for name in MODEL_ALIASES if name.endswith(".moonshotai.kimi-k3")
]
