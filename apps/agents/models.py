"""
Model configuration for AWS Bedrock.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class TemperatureRange(BaseModel):
    min: float
    max: float
    default: float
    current: float


class MaxTokens(BaseModel):
    min: int
    max: int
    default: int
    current: int


class ModelConfig(BaseModel):
    provider: str
    temperatureRange: TemperatureRange
    maxTokens: MaxTokens


class ModelConfigurationParams(BaseModel):
    name: str
    label: str
    config: ModelConfig
    isNew: bool = False


# AWS Bedrock models - matching models.ts (without bedrock/ prefix)
BEDROCK_MODELS: List[ModelConfigurationParams] = [
    {
        "name": "global.anthropic.claude-opus-4-5-20251101-v1:0",
        "label": "Claude Opus 4.5",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 64000,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": True,
    },
    {
        "name": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "label": "Claude Sonnet 4.5",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 64000,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "label": "Claude Haiku 4.5",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 64000,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "global.anthropic.claude-sonnet-4-20250514-v1:0",
        "label": "Claude Sonnet 4",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.anthropic.claude-opus-4-1-20250805-v1:0",
        "label": "Claude Opus 4.1",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.amazon.nova-premier-v1:0",
        "label": "Nova Premier",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.amazon.nova-pro-v1:0",
        "label": "Nova Pro",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.amazon.nova-micro-v1:0",
        "label": "Nova Micro",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.amazon.nova-lite-v1:0",
        "label": "Nova Lite",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.meta.llama3-3-70b-instruct-v1:0",
        "label": "Llama 3.3 70B Instruct",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "us.deepseek.r1-v1:0",
        "label": "DeepSeek R1",
        "config": {
            "provider": "bedrock",
            "temperatureRange": {
                "min": 0,
                "max": 1,
                "default": 0.5,
                "current": 0.5,
            },
            "maxTokens": {
                "min": 1,
                "max": 8192,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    }
]

ALL_MODELS: List[ModelConfigurationParams] = BEDROCK_MODELS

DEFAULT_MODEL_NAME = BEDROCK_MODELS[0]["name"]
DEFAULT_MODEL_CONFIG = BEDROCK_MODELS[0]["config"]

# Models which do NOT support the temperature parameter
TEMPERATURE_EXCLUDED_MODELS: List[str] = []

# Models which do NOT stream back tool calls
NON_STREAMING_TOOL_CALLING_MODELS: List[str] = []

# Models which do NOT stream back text
NON_STREAMING_TEXT_MODELS: List[str] = []

# Models which perform CoT before generating a final response
THINKING_MODELS: List[str] = []

