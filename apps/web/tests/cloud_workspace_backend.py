"""Local browser-test fixture: real workspace API/storage, deterministic agent.

Run from apps/backend with PYTHONPATH=. and explicit WORKSPACE_AUTH_MODE=local.
This fixture binds only localhost and is never used by the production app.
"""
import threading
import uvicorn

from main import app
from api.workspaces import service
from api.workspaces.files import ProjectFiles

invocations = []
release = threading.Event()


def fixture_agent(payload):
    invocations.append(payload)
    if "기다림" in payload["message"]:
        release.wait(45)
        release.clear()
    if "실패 테스트" in payload["message"]:
        raise RuntimeError("Controlled browser-test failure")
    files = ProjectFiles(payload["ownerKey"], payload["workspaceId"])
    path = payload.get("activePath") or files.list()[0]["path"]
    document = files.read(path)
    before = document["content"]
    selection = payload.get("selection")
    if selection:
        replacement = selection["text"].replace("문장 입니다", "문장입니다")
        after = before[:selection["start"]] + replacement + before[selection["end"]:]
    else:
        after = before.replace("문장 입니다", "문장입니다")
        if after == before:
            after = before + "\r\n\r\n검토를 기다리는 새 문장.\r\n"
    proposals = [{
        "path": path, "baseVersion": document["version"], "baseContent": before,
        "proposedContent": after, "explanation": "띄어쓰기와 글의 흐름을 다듬었습니다.",
    }]
    if "여러 파일" in payload["message"]:
        proposals.append({
            "path": "notes/agent-note.md", "baseVersion": None, "baseContent": "",
            "proposedContent": "# 함께 만든 메모\n\n승인 후 저장되는 문서입니다.\n",
            "explanation": "두 번째 파일의 초안을 제안합니다.",
        })
    return {"message": "검토할 수정안을 준비했습니다. 파일별로 내용을 확인해 주세요.",
            "proposals": proposals, "events": []}


service.invoke_agent = fixture_agent


@app.post("/__test/release")
def release_agent():
    release.set()
    return {"ok": True}


@app.get("/__test/invocations")
def recorded_invocations():
    return invocations


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9011, log_level="warning")
