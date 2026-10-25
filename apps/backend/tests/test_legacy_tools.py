"""Updated Claude models must still work with canvas title/reflection tools."""
import importlib
import os
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from core.bedrock_client import get_bedrock_model


class LegacyToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_DEFAULT_REGION": "us-east-1",
            "STORAGE_TYPE": "memory",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.model = get_bedrock_model(
            {"configurable": {"customModelName": "global.anthropic.claude-sonnet-5-5"}}
        )

    async def test_title_generation_uses_supported_tool_choice(self):
        graph = importlib.import_module("agents.thread_title.graph")
        result = ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="",
            tool_calls=[{"name": "generate_title", "args": {"title": "글쓰기"}, "id": "test-title", "type": "tool_call"}],
            response_metadata={"stopReason": "tool_use"},
        ))])
        with patch.object(graph, "get_bedrock_model", return_value=self.model):
            with patch("langchain_aws.ChatBedrockConverse._agenerate", new=AsyncMock(return_value=result)):
                generated = await graph.generate_title_node(
                    {"messages": [HumanMessage(content="글을 써 주세요.")]},
                    {"configurable": {"open_canvas_thread_id": "test-thread"}},
                )
        self.assertEqual(generated, {"title": "글쓰기", "thread_id": "test-thread"})

    async def test_reflection_uses_supported_tool_choice(self):
        graph = importlib.import_module("agents.reflection.graph")
        result = ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="",
            tool_calls=[{
                "name": "generate_reflections",
                "args": {"styleRules": ["간결하게 씁니다."], "content": []},
                "id": "test-reflection", "type": "tool_call",
            }],
            response_metadata={"stopReason": "tool_use"},
        ))])
        with patch.object(graph, "get_bedrock_model", return_value=self.model):
            with patch("langchain_aws.ChatBedrockConverse._agenerate", new=AsyncMock(return_value=result)):
                generated = await graph.reflect_node(
                    {"messages": [HumanMessage(content="간결하게 써 주세요.")]},
                    {"configurable": {"open_canvas_assistant_id": "test-assistant"}},
                )
        self.assertEqual(generated, {"reflections": {"styleRules": ["간결하게 씁니다."], "content": []}})

    async def test_kimi_legacy_tools_can_use_implicit_automatic_choice(self):
        model = get_bedrock_model(
            {"configurable": {"customModelName": "global.moonshotai.kimi-k3"}}
        )
        cases = [
            (
                "agents.thread_title.graph", "generate_title_node", "generate_title",
                {"title": "Kimi title"}, {"open_canvas_thread_id": "kimi-thread"},
                {"title": "Kimi title", "thread_id": "kimi-thread"},
            ),
            (
                "agents.reflection.graph", "reflect_node", "generate_reflections",
                {"styleRules": ["Concise."], "content": []},
                {"open_canvas_assistant_id": "kimi-assistant"},
                {"reflections": {"styleRules": ["Concise."], "content": []}},
            ),
        ]
        for module_name, node, tool, arguments, config, expected in cases:
            with self.subTest(node=node):
                graph = importlib.import_module(module_name)
                result = ChatResult(generations=[ChatGeneration(message=AIMessage(
                    content="",
                    tool_calls=[{"name": tool, "args": arguments, "id": "kimi-tool", "type": "tool_call"}],
                    response_metadata={"stopReason": "tool_use"},
                ))])
                with patch.object(graph, "get_bedrock_model", return_value=model):
                    with patch("langchain_aws.ChatBedrockConverse._agenerate", new=AsyncMock(return_value=result)):
                        generated = await getattr(graph, node)(
                            {"messages": [HumanMessage(content="Summarize this conversation.")]},
                            {"configurable": config},
                        )
                self.assertEqual(generated, expected)


if __name__ == "__main__":
    unittest.main()
