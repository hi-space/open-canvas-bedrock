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


# AWS Bedrock models
BEDROCK_MODELS: List[ModelConfigurationParams] = [
    {
        "name": "bedrock/claude-3-5-sonnet-20240620",
        "label": "Claude 3.5 Sonnet (Bedrock)",
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
        "name": "bedrock/claude-3-5-haiku-20241022",
        "label": "Claude 3.5 Haiku (Bedrock)",
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
        "name": "bedrock/claude-3-opus-20240229",
        "label": "Claude 3 Opus (Bedrock)",
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
                "max": 4096,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "bedrock/amazon.titan-text-lite-v1",
        "label": "Amazon Titan Text Lite (Bedrock)",
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
                "max": 4096,
                "default": 4096,
                "current": 4096,
            },
        },
        "isNew": False,
    },
    {
        "name": "bedrock/amazon.titan-text-express-v1",
        "label": "Amazon Titan Text Express (Bedrock)",
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
        "name": "bedrock/ai21.j2-ultra-v1",
        "label": "AI21 Jurassic-2 Ultra (Bedrock)",
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

