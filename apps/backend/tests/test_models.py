"""Regression checks at the Bedrock request boundary; no AWS calls are made."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from botocore.stub import Stubber
from langchain_core.messages import AIMessage, HumanMessage

from core.bedrock_client import get_bedrock_model
from core.models import get_model_catalog
from core.utils import get_model_config


class BedrockConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "AWS_SESSION_TOKEN": "temporary-session",
                "AWS_EC2_METADATA_DISABLED": "true",
                "AWS_REGION": "ap-northeast-2",
                "AWS_DEFAULT_REGION": "us-east-1",
                "BEDROCK_MODEL_ID": "global.anthropic.claude-haiku-5-5",
                "LANGSMITH_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_environment_model_and_region_are_used_without_mutating_config(self):
        config = {"configurable": {"open_canvas_thread_id": "existing-thread"}}
        resolved = get_model_config(config)
        self.assertEqual(resolved["modelName"], "global.anthropic.claude-haiku-5-5")
        self.assertEqual(resolved["region"], "ap-northeast-2")
        self.assertEqual(config, {"configurable": {"open_canvas_thread_id": "existing-thread"}})

    def test_explicit_model_wins_but_request_region_and_credentials_are_ignored(self):
        resolved = get_model_config(
            {
                "configurable": {
                    "customModelName": "bedrock/eu.anthropic.claude-sonnet-5-5",
                    "region": "eu-west-1",
                    "credentials": {"aws_access_key_id": "untrusted"},
                }
            }
        )
        self.assertEqual(resolved["modelName"], "eu.anthropic.claude-sonnet-5-5")
        self.assertEqual(resolved["region"], "ap-northeast-2")
        self.assertNotEqual(resolved.get("credentials", {}).get("aws_access_key_id"), "untrusted")

    def test_bedrock_region_override_wins_over_aws_region(self):
        with patch.dict(os.environ, {"BEDROCK_REGION": "eu-central-1"}):
            self.assertEqual(get_model_config({})["region"], "eu-central-1")

    def test_unknown_model_cannot_be_forwarded_to_bedrock(self):
        with self.assertRaisesRegex(ValueError, "model"):
            get_model_config({"configurable": {"customModelName": "unapproved.model"}})

    def test_model_settings_do_not_mutate_catalog_defaults(self):
        original = get_model_config({})["modelConfig"]
        custom = get_model_config(
            {"configurable": {"modelConfig": {"maxTokens": {"current": 2048}}}}
        )
        self.assertEqual(custom["modelConfig"]["maxTokens"]["current"], 2048)
        self.assertEqual(original, get_model_config({})["modelConfig"])

    def test_claude_request_uses_temporary_credentials_and_omits_sampling(self):
        model = get_bedrock_model(
            {"configurable": {"customModelName": "global.anthropic.claude-sonnet-5-5"}},
            temperature=0,
            max_tokens=1024,
        )
        self.assertEqual(model.client.meta.region_name, "ap-northeast-2")
        self.assertEqual(model.region_name, "ap-northeast-2")
        self.assertEqual(model.client._request_signer._credentials.token, "temporary-session")
        with Stubber(model.client) as stub:
            stub.add_response(
                "converse",
                {
                    "output": {"message": {"role": "assistant", "content": [{"text": "done"}]}},
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                    "metrics": {"latencyMs": 1},
                },
                {
                    "modelId": "global.anthropic.claude-sonnet-5-5",
                    "messages": [{"role": "user", "content": [{"text": "revise"}]}],
                    "system": [],
                    "inferenceConfig": {"maxTokens": 1024},
                },
            )
            response = model.invoke([HumanMessage(content="revise")])
            self.assertEqual(response.text, "done")

    def test_new_models_can_be_selected_and_invoked_with_provider_defaults(self):
        for model_name in (
            "global.anthropic.claude-fable-5-1",
            "global.openai.gpt-6.1-sol",
            "global.openai.gpt-6-astra",
            "global.openai.gpt-6-luna",
            "global.xai.grok-4.7",
            "global.moonshotai.kimi-k3",
        ):
            with self.subTest(model=model_name):
                model = get_bedrock_model(
                    {"configurable": {"customModelName": model_name}},
                    temperature=0,
                    max_tokens=1024,
                )
                with Stubber(model.client) as stub:
                    stub.add_response(
                        "converse",
                        {
                            "output": {"message": {"role": "assistant", "content": [{"text": "done"}]}},
                            "stopReason": "end_turn",
                            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                            "metrics": {"latencyMs": 1},
                        },
                        {
                            "modelId": model_name,
                            "messages": [{"role": "user", "content": [{"text": "revise"}]}],
                            "system": [],
                            "inferenceConfig": {"maxTokens": 1024},
                        },
                    )
                    self.assertEqual(model.invoke([HumanMessage(content="revise")]).text, "done")
                    stub.assert_no_pending_responses()

    def test_configured_geographic_defaults_remain_selectable(self):
        for model_name in (
            "us.anthropic.claude-fable-5-1",
            "us.openai.gpt-6.1-sol",
            "us.openai.gpt-6-astra",
            "us.openai.gpt-6-luna",
            "us.xai.grok-4.7",
            "in.moonshotai.kimi-k3",
        ):
            with self.subTest(model=model_name), patch.dict(os.environ, {"BEDROCK_MODEL_ID": model_name}):
                catalog = get_model_catalog()
                self.assertEqual(catalog["defaultModelName"], model_name)
                definition = next(item for item in catalog["models"] if item["name"] == model_name)
                self.assertEqual(definition["config"], catalog["defaultModelConfig"])
                self.assertEqual(get_model_config({})["modelName"], model_name)

    def test_retired_models_and_undocumented_profiles_cannot_reach_bedrock(self):
        for model_name in (
            "global.amazon.nova-2-lite-v1:0",
            "us.amazon.nova-2-lite-v1:0",
            "deepseek.v3.2",
            "bedrock/deepseek.v3.2",
            "eu.openai.gpt-6.1-sol",
            "eu.anthropic.claude-fable-5-1",
            "openai.gpt-6.1-sol",
            "xai.grok-4.7",
            "moonshotai.kimi-k3",
        ):
            with self.subTest(model=model_name), self.assertRaises(ValueError):
                get_bedrock_model({"configurable": {"customModelName": model_name}})

    def test_kimi_history_drops_reasoning_without_mutating_saved_messages(self):
        model = get_bedrock_model(
            {"configurable": {"customModelName": "global.moonshotai.kimi-k3"}},
            max_tokens=1024,
        )
        messages = [
            HumanMessage(content="Draft an introduction."),
            AIMessage(content=[
                {"type": "reasoning_content", "reasoning_content": {"text": "Private reasoning."}},
                {"type": "text", "text": "Original introduction."},
            ]),
            HumanMessage(content="Revise it."),
        ]
        original = deepcopy(messages)
        with Stubber(model.client) as stub:
            stub.add_response(
                "converse",
                {
                    "output": {"message": {"role": "assistant", "content": [{"text": "Revised."}]}},
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                    "metrics": {"latencyMs": 1},
                },
                {
                    "modelId": "global.moonshotai.kimi-k3",
                    "messages": [
                        {"role": "user", "content": [{"text": "Draft an introduction."}]},
                        {"role": "assistant", "content": [{"text": "Original introduction."}]},
                        {"role": "user", "content": [{"text": "Revise it."}]},
                    ],
                    "system": [],
                    "inferenceConfig": {"maxTokens": 1024},
                },
            )
            self.assertEqual(model.invoke(messages).text, "Revised.")
            stub.assert_no_pending_responses()
        self.assertEqual(messages, original)

    def test_kimi_india_profile_keeps_the_model_provider_and_streaming(self):
        model = get_bedrock_model(
            {"configurable": {"customModelName": "bedrock/in.moonshotai.kimi-k3"}}
        )
        self.assertEqual(model.model_id, "in.moonshotai.kimi-k3")
        self.assertEqual(model.provider, "moonshotai")
        self.assertFalse(model.disable_streaming)


if __name__ == "__main__":
    unittest.main()
