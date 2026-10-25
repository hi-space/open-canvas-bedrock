"""AgentCore's HTTP contract, with only the external Converse call replaced."""
import json
import logging

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    from workspace_agent.app import app

    owner = "a" * 64
    (tmp_path / owner / "workspace-1" / "files").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def payload():
    return {
        "ownerKey": "a" * 64, "workspaceId": "workspace-1", "message": "List the project.",
        "model": "global.anthropic.claude-opus-5-5", "history": [], "sources": [],
    }


class ExternalModel:
    def converse(self, **_request):
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": "Ready for review."}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 100, "outputTokens": 10, "totalTokens": 110},
            "metrics": {"latencyMs": 1},
            "ResponseMetadata": {"RequestId": "offline-test", "HTTPStatusCode": 200},
        }


def test_ping_uses_the_agentcore_health_contract_without_a_changing_timestamp(client):
    first = client.get("/ping")
    second = client.get("/ping")
    assert first.status_code == 200
    assert first.json() == {"status": "Healthy"}
    assert second.json() == first.json()


def test_invocations_return_the_runtime_json_contract(client, monkeypatch):
    monkeypatch.setattr("workspace_agent.agent.boto3.client", lambda *args, **kwargs: ExternalModel())
    result = client.post("/invocations", json=payload())
    assert result.status_code == 200, result.text
    assert result.json() == {"message": "Ready for review.", "proposals": [], "events": []}


@pytest.mark.parametrize("changes", [
    {"ownerKey": "bad-owner"}, {"workspaceId": "../outside"}, {"message": ""},
    {"root": "/etc"}, {"history": [{"role": "system", "content": "PRIVATE"}]},
])
def test_invalid_runtime_input_returns_readable_detail_without_echoing_request_data(client, changes):
    result = client.post("/invocations", json={**payload(), **changes})
    assert result.status_code == 422
    assert isinstance(result.json()["detail"], str)
    assert "PRIVATE" not in result.text


def test_duplicate_json_keys_are_rejected_at_the_http_boundary(client):
    raw = json.dumps(payload()).removesuffix("}") + ',"ownerKey":"' + "b" * 64 + '"}'
    result = client.post("/invocations", content=raw, headers={"Content-Type": "application/json"})
    assert result.status_code == 422
    assert isinstance(result.json()["detail"], str)


def test_large_invocation_body_is_rejected_before_parsing(client):
    result = client.post(
        "/invocations", content=b"x" * (2 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert result.status_code == 413
    assert isinstance(result.json()["detail"], str)


def test_provider_failure_returns_a_retryable_error_without_private_provider_data(client, monkeypatch):
    class UnavailableModel:
        def converse(self, **_request):
            raise RuntimeError("PRIVATE request contents")
    monkeypatch.setattr("workspace_agent.agent.boto3.client", lambda *args, **kwargs: UnavailableModel())
    result = client.post("/invocations", json=payload())
    assert result.status_code == 502
    assert isinstance(result.json()["detail"], str)
    assert "PRIVATE" not in result.text


def test_model_rejections_log_only_safe_stage_and_exception_classes(client, monkeypatch, caplog):
    class InvalidModel:
        def converse(self, **_request):
            result = ExternalModel().converse()
            result["stopReason"] = "tool_use"
            result["output"]["message"]["content"] = [
                {"text": "PRIVATE_DOCUMENT_CONTENT"},
                {"toolUse": {
                    "toolUseId": "read", "name": "read_file", "type": "server_tool_use",
                    "input": {"path": "PRIVATE_FILENAME.md", "credential": "PRIVATE_CREDENTIAL"},
                }},
            ]
            return result
    monkeypatch.setattr("workspace_agent.agent.boto3.client", lambda *args, **kwargs: InvalidModel())
    with caplog.at_level(logging.WARNING):
        result = client.post("/invocations", json=payload())
    assert result.status_code == 502
    assert "stage=tool_type" in caplog.text
    assert "stage=run_agent" in caplog.text
    assert "error=AgentError" in caplog.text
    assert "cause=ValueError" in caplog.text
    assert "PRIVATE" not in caplog.text
    assert "PRIVATE" not in result.text


def test_mount_errors_log_the_failure_class_without_workspace_paths(client, monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "PRIVATE_MOUNT_PATH"))
    with caplog.at_level(logging.WARNING):
        result = client.post("/invocations", json=payload())
    assert result.status_code == 502
    assert "stage=run_agent" in caplog.text
    assert "error=ToolError" in caplog.text
    assert "cause=FileNotFoundError" in caplog.text
    assert "PRIVATE" not in caplog.text
    assert "PRIVATE" not in result.text
