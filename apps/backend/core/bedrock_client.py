"""
AWS Bedrock client wrapper for LangChain.
"""
from typing import Optional, Dict, Any, List
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
import os
import boto3


def get_bedrock_model(
    config: RunnableConfig,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    is_tool_calling: bool = False
) -> ChatBedrockConverse:
    """Get AWS Bedrock model instance using the Converse API."""
    from core.utils import get_model_config
    
    model_config = get_model_config(config, is_tool_calling=is_tool_calling)
    model_name = model_config["modelName"]
    config_dict = model_config.get("modelConfig", {})
    region = model_config.get("region", "us-east-1")
    credentials = model_config.get("credentials", {})
    
    # Get temperature and max_tokens from config or defaults
    temp = temperature
    if temp is None:
        temp_range = config_dict.get("temperatureRange", {})
        temp = temp_range.get("current", temp_range.get("default", 0.5))
    
    max_toks = max_tokens
    if max_toks is None:
        max_toks_config = config_dict.get("maxTokens", {})
        max_toks = max_toks_config.get("current", max_toks_config.get("default", 4096))
    
    # Create boto3 session with credentials if provided
    session_kwargs = {"region_name": region}
    if credentials.get("aws_access_key_id") and credentials.get("aws_secret_access_key"):
        session_kwargs.update({
            "aws_access_key_id": credentials["aws_access_key_id"],
            "aws_secret_access_key": credentials["aws_secret_access_key"],
        })
    
    # Create boto3 session
    boto_session = boto3.Session(**session_kwargs)
    
    # Create ChatBedrockConverse instance
    # Note: ChatBedrockConverse uses temperature and max_tokens as direct parameters, not in model_kwargs
    model = ChatBedrockConverse(
        model_id=model_name,
        temperature=temp,
        max_tokens=max_toks,
        credentials_profile_name=None,  # Use boto3 session instead
    )
    
    # Set the boto3 session
    model.client = boto_session.client("bedrock-runtime", region_name=region)
    
    return model

