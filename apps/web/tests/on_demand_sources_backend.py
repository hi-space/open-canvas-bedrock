"""Local deterministic model boundary; real source store, agent tools and graph."""
import json
import os
from unittest.mock import patch

import uvicorn

import research_html_backend as research_fixture
from api.workspaces import service
from workspace_agent.agent import run_agent


app = research_fixture.app
research_fixture.BRIEF["questions"][0].update(
    question="프로젝트 자료의 예시 정확도와 versioned document snapshot",
    queries=["document evaluation accuracy 예시 정확도"],
)
observations = []


def reply(*, tool=None, text="검토할 수정안을 준비했습니다."):
    content = [{"toolUse": {
        "toolUseId": tool[0], "name": tool[1], "input": tool[2],
    }}] if tool else [{"text": text}]
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": "tool_use" if tool else "end_turn",
        "usage": {"inputTokens": 100, "outputTokens": 30, "totalTokens": 130},
    }


class LocalModel:
    def __init__(self):
        self.round = 0
        self.context = {}
        self.url = ""
        self.observation = {}

    def converse(self, **request):
        self.round += 1
        if self.round == 1:
            initial = request["messages"][0]["content"][0]["text"]
            self.context = json.loads(initial)
            self.observation = {
                "sourceCount": self.context["sourceCount"],
                "initialCharacters": len(initial),
                "preloadedBody": "IRRELEVANT_STORED_BODY" in initial or "READ_ONLY_TARGET" in initial,
                "loadedSources": [],
            }
            observations.append(self.observation)
            return reply(tool=("find", "search_sources", {"query": "versioned document snapshot"}))
        result = request["messages"][-1]["content"][0]["toolResult"]
        if result["status"] != "success":
            raise AssertionError(result)
        data = result["content"][0]["json"]
        if self.round == 2:
            target = data["sources"][0]
            return reply(tool=("source", "read_source", {
                "id": target["id"], "offset": target["readOffset"],
            }))
        if self.round == 3:
            self.observation["loadedSources"].append(data["source"]["id"])
            self.observation["readCharacters"] = len(data["source"]["excerpt"])
            self.url = data["source"]["url"]
            return reply(tool=("file", "read_file", {"path": self.context["activePath"]}))
        if self.round == 4:
            return reply(tool=("edit", "propose_edit", {
                "path": self.context["activePath"],
                "replacement": data["content"] + f"\n\n필요한 근거만 읽어 추가한 설명입니다 [1]({self.url}).\n",
                "explanation": "읽은 근거를 연결했습니다.",
            }))
        return reply()


def fixture_agent(payload):
    model = LocalModel()
    with patch("workspace_agent.agent.model_client", return_value=model):
        return run_agent(payload)


service.invoke_agent = fixture_agent


@app.get("/__test/source-observations")
def source_observations():
    return observations


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SOURCE_TEST_PORT", "9019")),
                log_level="warning")
