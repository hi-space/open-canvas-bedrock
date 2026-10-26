"""Exercise lazy sources through real job preparation, tools and proposal validation."""
import json
from unittest.mock import patch

import pytest

from test_source_library import OWNER, WORKSPACE, project, source
from test_workspace_agent import BedrockFixture, response


def prepare(files, **options):
    from api.workspaces.models import ChatRequest
    from api.workspaces.service import prepare_job

    with files.lock():
        return prepare_job(files, ChatRequest(message="Revise using the relevant reference.", requestId="one", **options))


def test_large_library_never_enters_job_payload_or_initial_model_message(project, monkeypatch):
    from api.workspaces.service import run_job
    from api.workspaces.sources import SourceLibrary
    from workspace_agent.agent import run_agent

    with project.lock():
        library = SourceLibrary(project)
        for index in range(60):
            library.put(source(index, "DO_NOT_PRELOAD " * 250))
        original = project.save("draft.md", "Before.\n", None)
    job, payload = prepare(project, activePath="draft.md", activeVersion=original["version"])
    assert "DO_NOT_PRELOAD" not in json.dumps(payload)
    assert payload.get("sourceSnapshot")
    bedrock = BedrockFixture([
        response(None, tools=[("read", "read_source", {"id": "source-59", "limit": 100})]),
        response(None, tools=[("file", "read_file", {"path": "draft.md"})]),
        response(None, tools=[("edit", "propose_edit", {
            "path": "draft.md", "replacement": "After [1](https://example.com/reference/59).\n",
            "explanation": "Cited the source actually read.",
        })]),
        response("Prepared for review."),
    ])
    monkeypatch.setattr("workspace_agent.agent.boto3.client", lambda *args, **kwargs: bedrock)
    with patch("api.workspaces.service.invoke_agent", side_effect=run_agent), \
            patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
        run_job(OWNER, WORKSPACE, job["id"], payload)
    saved = project.metadata.get(project.namespace, "job:" + job["id"])
    assert saved["status"] == "completed", saved
    assert "DO_NOT_PRELOAD" not in json.dumps(bedrock.calls[0])
    proposal = project.proposal(saved["proposalIds"][0])
    assert len(proposal["sources"]) == 1
    assert len(proposal["sources"][0]["excerpt"]) == 100
    assert proposal["sourceReads"][0]["ranges"] == [[0, 100]]
    assert project.read("draft.md")["content"] == "Before.\n"


def test_deleting_a_source_during_the_job_keeps_read_snapshot_without_resurrection(project):
    from api.workspaces.service import run_job
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog

    with project.lock():
        library = SourceLibrary(project)
        library.put(source(1, "Old evidence."))
    job, payload = prepare(project)
    catalog = SourceCatalog(project.root, OWNER, WORKSPACE, payload["sourceSnapshot"])
    with project.lock():
        library.remove("source-1")
    with patch("api.workspaces.service.invoke_agent", return_value={
        "message": "Prepared", "sourceReads": [{
            "id": "source-1", "version": catalog.entries["source-1"]["version"], "ranges": [[0, 13]],
        }], "sources": [source(1, "Old evidence.")],
        "proposals": [{"path": "new.md", "baseVersion": None, "baseContent": "",
                       "proposedContent": "Fact [1](https://example.com/reference/1).",
                       "explanation": "Read old snapshot"}],
    }), patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
        run_job(OWNER, WORKSPACE, job["id"], payload)
    saved = project.metadata.get(project.namespace, "job:" + job["id"])
    assert saved["status"] == "completed", saved
    assert project.metadata.get(project.namespace, "source:source-1") is None
    assert project.proposal(saved["proposalIds"][0])["sources"][0]["excerpt"] == "Old evidence."


def test_job_rejects_forged_source_versions_before_publishing_a_proposal(project):
    from api.workspaces.service import run_job
    from api.workspaces.sources import SourceLibrary

    with project.lock():
        SourceLibrary(project).put(source(1))
    job, payload = prepare(project)
    with patch("api.workspaces.service.invoke_agent", return_value={
        "message": "Prepared", "sourceReads": [
            {"id": "source-1", "version": "b" * 64, "ranges": [[0, 5]]},
        ], "proposals": [],
    }), patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
        run_job(OWNER, WORKSPACE, job["id"], payload)
    saved = project.metadata.get(project.namespace, "job:" + job["id"])
    assert saved["status"] == "failed"
    assert saved["proposalIds"] == []


def test_new_fetched_version_is_preserved_without_overwriting_the_users_source(project):
    from api.workspaces.service import run_job
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog, entry_for

    with project.lock():
        library = SourceLibrary(project)
        library.put(source(1, "User's original excerpt."))
    job, payload = prepare(project)
    fresh = source(1, "Newly fetched evidence.")
    entry, _ = entry_for(fresh)
    with patch("api.workspaces.service.invoke_agent", return_value={
        "message": "Prepared", "sources": [fresh], "sourceReads": [{
            "id": "source-1", "version": entry["version"], "ranges": [[0, len(fresh["excerpt"])]],
        }], "proposals": [{
            "path": "new.md", "baseVersion": None, "baseContent": "",
            "proposedContent": "New finding [1](https://example.com/reference/1).",
            "explanation": "Read fresh evidence.",
        }],
    }), patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
        run_job(OWNER, WORKSPACE, job["id"], payload)
    saved = project.metadata.get(project.namespace, "job:" + job["id"])
    assert saved["status"] == "completed", saved
    proposal = project.proposal(saved["proposalIds"][0])
    assert proposal["sources"] == [fresh]
    assert library.read("source-1")["excerpt"] == "User's original excerpt."
    frozen = SourceCatalog(project.root, OWNER, WORKSPACE, proposal["sourceSnapshot"])
    assert frozen.read("source-1")["source"]["excerpt"] == fresh["excerpt"]
