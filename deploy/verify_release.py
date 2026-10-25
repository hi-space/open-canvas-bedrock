"""One-shot ECS verification using the deployed backend image and task role.

Run through an ECS command override; the script prints no credentials or source
article contents. It creates and removes only its own deployment probe item.
"""
import json
import os
import uuid

from fastapi.testclient import TestClient
from main import app
from store.factory import create_storage

expected = "global.anthropic.claude-opus-5-5"
assert os.environ["STORAGE_TYPE"] == "dynamodb"
storage = create_storage()
namespace = ["deployment-verification"]
key = str(uuid.uuid4())
try:
    storage.put_item(namespace, key, {"probe": key})
    assert storage.get_item(namespace, key)["value"] == {"probe": key}
finally:
    storage.delete_item(namespace, key)
print(json.dumps({"check": "persistent-storage", "status": "passed"}), flush=True)

with TestClient(app) as client:
    catalog = client.get("/api/models/list")
    assert catalog.status_code == 200, catalog.status_code
    assert catalog.json()["defaultModelName"] == expected
    response = client.post("/api/writing/propose", json={
        "document": "테스트 문장 입니다.",
        "selectedText": "테스트 문장 입니다.",
        "instruction": "띄어쓰기만 바로잡아 주세요. 설명은 짧은 한 문장으로 작성해 주세요.",
        "sources": [],
    })
    if response.status_code != 200:
        print(json.dumps({"check": "live-model", "status": response.status_code,
                          "detail": response.json().get("detail")}, ensure_ascii=False), flush=True)
        raise RuntimeError("Live model verification failed")
    result = response.json()
    assert result["replacement"].strip() and result["explanation"].strip()
    print(json.dumps({"check": "live-model", "status": "passed", "model": expected,
                      "replacementCharacters": len(result["replacement"])}, ensure_ascii=False), flush=True)

    if os.environ.get("FIRECRAWL_API_KEY"):
        scraped = client.post("/api/firecrawl/scrape", json={
            "urls": ["https://www.markdownguide.org/basic-syntax/"],
        })
        documents = scraped.json().get("documents", [])
        assert scraped.status_code == 200 and documents and documents[0]["data"].strip(), "Reference extraction failed"
        print(json.dumps({"check": "live-reference-extraction", "status": "passed",
                          "characters": len(documents[0]["data"])}, ensure_ascii=False), flush=True)

print(json.dumps({"deploymentVerification": "passed"}), flush=True)
