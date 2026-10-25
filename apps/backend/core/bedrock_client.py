"""AWS Bedrock Converse model construction with the server credential chain."""
from typing import Optional
import math

import boto3
from botocore.config import Config
from langchain_aws import ChatBedrockConverse
from langchain_core.runnables import RunnableConfig

from core.bedrock_messages import prepare_converse_messages
from core.models import TEMPERATURE_EXCLUDED_MODELS, get_base_model_name, get_model_definition


def _prepare_converse_history(params, **kwargs):
    """Apply compatibility rules after LangChain produces native Converse blocks."""
    if "messages" in params:
        params["messages"] = prepare_converse_messages(params["modelId"], params["messages"])


def get_bedrock_model(
    config: RunnableConfig,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    is_tool_calling: bool = False,
) -> ChatBedrockConverse:
    """Construct both AWS clients before LangChain performs initialization.

    boto3 resolves environment credentials (including session tokens), profiles,
    workload roles, and the remaining default providers. Never take credentials
    from a browser-supplied graph config.
    """
    from core.utils import get_model_config

    resolved = get_model_config(config, is_tool_calling=is_tool_calling)
    model_name = resolved["modelName"]
    base_model_name = get_base_model_name(model_name)
    settings = resolved["modelConfig"]
    token_settings = settings["maxTokens"]
    tokens = max_tokens if max_tokens is not None else token_settings["current"]
    ceiling = get_model_definition(model_name)["config"]["maxTokens"]["max"]
    if isinstance(tokens, bool) or not isinstance(tokens, int) or not 1 <= tokens <= ceiling:
        raise ValueError(f"max_tokens must be an integer between 1 and {ceiling}.")

    sampling = None
    if model_name not in TEMPERATURE_EXCLUDED_MODELS:
        sampling = temperature if temperature is not None else settings["temperatureRange"]["current"]
        if (
            isinstance(sampling, bool)
            or not isinstance(sampling, (int, float))
            or not math.isfinite(sampling)
            or not 0 <= sampling <= 1
        ):
            raise ValueError("temperature must be between 0 and 1.")

    session = boto3.Session(region_name=resolved["region"])
    client_config = Config(
        connect_timeout=10, read_timeout=180, retries={"mode": "standard", "max_attempts": 2}
    )
    runtime_client = session.client("bedrock-runtime", config=client_config)
    for operation in ("Converse", "ConverseStream"):
        runtime_client.meta.events.register(
            f"provide-client-params.bedrock-runtime.{operation}",
            _prepare_converse_history,
        )
    return ChatBedrockConverse(
        model_id=model_name,
        base_model_id=base_model_name,
        provider=base_model_name.partition(".")[0],
        region_name=resolved["region"],
        temperature=sampling,
        max_tokens=tokens,
        client=runtime_client,
        bedrock_client=session.client("bedrock", config=client_config),
    )
