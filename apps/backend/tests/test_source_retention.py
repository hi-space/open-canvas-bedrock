"""Storage quotas do not become context quotas; unused copies are reclaimed."""
from unittest.mock import patch

import pytest

from test_source_library import OWNER, WORKSPACE, project, source
from test_source_jobs import prepare


def test_storage_count_limit_does_not_prevent_existing_source_reads(project, monkeypatch):
    from api.workspaces import sources
    from core.source_catalog import SourceCatalog

    monkeypatch.setattr(sources, "MAX_STORED_SOURCES", 2, raising=False)
    with project.lock():
        library = sources.SourceLibrary(project)
        library.put(source(1))
        library.put(source(2))
        with pytest.raises(sources.SourceCapacityError, match="보관"):
            library.put(source(3))
        snapshot = library.snapshot()
    assert SourceCatalog(project.root, OWNER, WORKSPACE, snapshot).read("source-2")["source"]["excerpt"]


def test_unused_versions_are_removed_but_active_job_versions_survive(project):
    from api.workspaces.sources import SourceLibrary

    with project.lock():
        library = SourceLibrary(project)
        old = library.put(source(1, "old"))
    job, _ = prepare(project)
    with project.lock():
        new = library.put(source(1, "new"))
        old_path = library.directory / "blobs" / f"{old['version']}.json"
        assert old_path.exists()
        job["status"] = "failed"
        project.metadata.put(project.namespace, "job:" + job["id"], job)
        library.collect_garbage()
        assert not old_path.exists()
        new_path = library.directory / "blobs" / f"{new['version']}.json"
        assert new_path.exists()
        library.remove("source-1")
        assert not new_path.exists()


def test_proposal_pins_used_sources_only_and_releases_unused_copies(project):
    from api.workspaces.service import run_job
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog

    with project.lock():
        library = SourceLibrary(project)
        first = library.put(source(1, "used"))
        second = library.put(source(2, "unused"))
    job, payload = prepare(project)
    with patch("api.workspaces.service.invoke_agent", return_value={
        "message": "Ready", "sourceReads": [
            {"id": "source-1", "version": first["version"], "ranges": [[0, 4]]},
        ], "proposals": [{
            "path": "new.md", "baseVersion": None, "baseContent": "",
            "proposedContent": "Fact [1](https://example.com/reference/1).", "explanation": "Evidence.",
        }],
    }), patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
        run_job(OWNER, WORKSPACE, job["id"], payload)
    saved = project.metadata.get(project.namespace, "job:" + job["id"])
    assert saved["status"] == "completed", saved
    proposal = project.proposal(saved["proposalIds"][0])
    catalog = SourceCatalog(project.root, OWNER, WORKSPACE, proposal["sourceSnapshot"])
    assert set(catalog.entries) == {"source-1"}
    with project.lock():
        library.remove("source-1")
        library.remove("source-2")
    assert (library.directory / "blobs" / f"{first['version']}.json").exists()
    assert not (library.directory / "blobs" / f"{second['version']}.json").exists()
    assert catalog.read("source-1")["source"]["excerpt"] == "used"


def test_full_storage_still_finishes_job_and_keeps_new_evidence_in_proposal(project, monkeypatch):
    from api.workspaces import sources
    from api.workspaces.service import run_job
    from core.source_catalog import entry_for

    with project.lock():
        sources.SourceLibrary(project).put(source(1))
    monkeypatch.setattr(sources, "MAX_STORED_SOURCES", 1, raising=False)
    job, payload = prepare(project)
    new = source(2, "newly read")
    entry, _ = entry_for(new)
    with patch("api.workspaces.service.invoke_agent", return_value={
        "message": "Ready", "sources": [new], "sourceReads": [
            {"id": new["id"], "version": entry["version"], "ranges": [[0, 10]]},
        ], "proposals": [{
            "path": "new.md", "baseVersion": None, "baseContent": "",
            "proposedContent": "Fact [1](https://example.com/reference/2).", "explanation": "Evidence.",
        }],
    }), patch("api.workspaces.service.fetch_requested_sources", return_value=[]):
        run_job(OWNER, WORKSPACE, job["id"], payload)
    saved = project.metadata.get(project.namespace, "job:" + job["id"])
    assert saved["status"] == "completed", saved
    proposal = project.proposal(saved["proposalIds"][0])
    assert proposal["sources"] == [new]
    assert project.metadata.get(project.namespace, "source:source-2") is None


def test_source_byte_quota_allows_shrinking_an_existing_record(project, monkeypatch):
    from api.workspaces import sources

    monkeypatch.setattr(sources, "MAX_STORED_BYTES", 400)
    with project.lock():
        library = sources.SourceLibrary(project)
        library.put(source(1, "x" * 200))
        with pytest.raises(sources.SourceCapacityError):
            library.put(source(2, "y" * 200))
        library.put(source(1, "shorter"))
        library.put(source(2, "y" * 100))
        assert len(library.summaries()) == 2
