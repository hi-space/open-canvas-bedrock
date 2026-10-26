"""Stored evidence is independent of the amount a single model job reads."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient


OWNER = hashlib.sha256(b"source-library-test").hexdigest()
WORKSPACE = "00000000-0000-0000-0000-000000000011"


@pytest.fixture
def project(tmp_path, monkeypatch):
    from api.workspaces.files import ProjectFiles

    for key, value in {
        "WORKSPACE_ROOT": str(tmp_path), "WORKSPACE_METADATA": "file",
        "WORKSPACE_AUTH_MODE": "local", "WORKSPACE_LOCAL_SUB": "source-library-test",
        "STORAGE_TYPE": "memory", "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }.items():
        monkeypatch.setenv(key, value)
    files = ProjectFiles(OWNER, WORKSPACE)
    files.files.mkdir(parents=True)
    with files.lock():
        files.metadata.put(files.owner_namespace, WORKSPACE, {
            "id": WORKSPACE, "name": "Sources", "createdAt": 0, "updatedAt": 0,
        })
    return files


def source(index, excerpt="Verified source text."):
    return {
        "id": f"source-{index}", "title": f"Reference {index}",
        "url": f"https://example.com/reference/{index}", "excerpt": excerpt,
    }


def test_source_api_stores_more_than_one_jobs_budget_and_returns_only_summaries(project):
    from main import app

    with TestClient(app) as client:
        for index in range(60):
            response = client.post(
                f"/api/workspaces/{WORKSPACE}/sources", json=source(index, "기밀 원문 " * 500),
            )
            assert response.status_code == 200, response.text
        snapshot = client.get(f"/api/workspaces/{WORKSPACE}").json()
        assert len(snapshot["sources"]) == 60
        assert "기밀 원문" not in json.dumps(snapshot, ensure_ascii=False)
        assert snapshot["sources"][0]["excerptCharacters"] == 3000
        response = client.get(f"/api/workspaces/{WORKSPACE}/sources/source-59")
        assert response.status_code == 200, response.text
        assert response.json()["excerpt"] == "기밀 원문 " * 500


def test_migrated_source_keeps_identity_and_snapshot_survives_edit_and_removal(project):
    from api.workspaces.sources import SourceLibrary
    from api.workspaces.files import now
    from core.source_catalog import SourceCatalog

    old = source(1, "Originally verified text.")
    with project.lock():
        project.metadata.put(project.namespace, "source:source-1", old)
        library = SourceLibrary(project)
        snapshot = library.snapshot()
        project.metadata.put(project.namespace, "job:snapshot-user", {
            "id": "snapshot-user", "status": "running", "createdAt": now(), "updatedAt": now(),
            "sourceSnapshots": [snapshot],
        })
        record = project.metadata.get(project.namespace, "source:source-1")
        # A compatibility mirror lets the previous API image read the record
        # during a rolling deployment/rollback.
        assert record["excerpt"] == old["excerpt"]
        assert record["id"] == old["id"] and record["url"] == old["url"]
        library.put(source(1, "New material."))
        project.metadata.delete(project.namespace, "source:source-1")
    catalog = SourceCatalog(project.root, OWNER, WORKSPACE, snapshot)
    read = catalog.read("source-1", 0, 8000)
    assert read["source"] == old
    assert read["version"] == record["version"]
    assert SourceLibrary(project).summaries() == []


def test_search_finds_late_korean_english_evidence_without_returning_its_body(project):
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog

    with project.lock():
        library = SourceLibrary(project)
        for index in range(80):
            library.put(source(index, "Unrelated cooking ingredients."))
        library.put(source(80, "도입 " * 2000 + "Kubernetes 오토스케일링 측정 결과."))
        snapshot = library.snapshot()
    catalog = SourceCatalog(project.root, OWNER, WORKSPACE, snapshot)
    for query in ("Kubernetes", "오토스케일링", "오토스케일"):
        hits = catalog.search(query, 0, 10)
        assert hits["sources"][0]["id"] == "source-80"
        assert "excerpt" not in hits["sources"][0]
        assert len(hits["sources"]) == 1
        assert hits["sources"][0]["readOffset"] > 0
    page = catalog.list(80, 20)
    assert page["total"] == 81
    assert len(page["sources"]) == 1
    read = catalog.read("source-80", 6000, 8000)
    assert read["source"]["excerpt"] == "Kubernetes 오토스케일링 측정 결과."
    assert read["offset"] == 6000
    assert read["nextOffset"] is None


def test_source_snapshot_and_body_cannot_cross_project_boundaries(project):
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog

    with project.lock():
        library = SourceLibrary(project)
        summary = library.put(source(1))
        snapshot = library.snapshot()
    with pytest.raises(ValueError):
        SourceCatalog(project.root, "b" * 64, WORKSPACE, snapshot)
    with pytest.raises(ValueError):
        SourceCatalog(project.root, OWNER, "other-project", snapshot)
    with pytest.raises(ValueError):
        SourceCatalog(project.root, OWNER, WORKSPACE, "../secrets")
    catalog = SourceCatalog(project.root, OWNER, WORKSPACE, snapshot)
    blob = project.internal / "source-library" / "blobs" / f"{summary['version']}.json"
    blob.unlink()
    blob.symlink_to("/etc/passwd")
    with pytest.raises(ValueError):
        catalog.read("source-1", 0, 8000)


def test_changed_source_bytes_cannot_masquerade_as_the_snapshotted_version(project):
    from api.workspaces.sources import SourceLibrary
    from core.source_catalog import SourceCatalog

    with project.lock():
        library = SourceLibrary(project)
        summary = library.put(source(1))
        snapshot = library.snapshot()
    blob = project.internal / "source-library" / "blobs" / f"{summary['version']}.json"
    blob.write_text(json.dumps(source(1, "Tampered evidence.")))
    catalog = SourceCatalog(project.root, OWNER, WORKSPACE, snapshot)
    with pytest.raises(ValueError, match="version|integrity"):
        catalog.read("source-1", 0, 8000)


def test_source_detail_remains_owner_authenticated(project, monkeypatch):
    from main import app

    with TestClient(app) as client:
        assert client.post(f"/api/workspaces/{WORKSPACE}/sources", json=source(1)).status_code == 200
        monkeypatch.setenv("WORKSPACE_LOCAL_SUB", "someone-else")
        assert client.get(f"/api/workspaces/{WORKSPACE}/sources/source-1").status_code == 404


def test_evidence_uses_only_read_ranges_and_overlaps_do_not_spend_budget_twice():
    from core.source_catalog import SourceCatalog, SourceEvidence

    catalog = SourceCatalog("", OWNER, WORKSPACE, sources=[source(1, "0123456789")])
    evidence = SourceEvidence(catalog, max_chars=10)
    evidence.read("source-1", 0, 6)
    evidence.read("source-1", 4, 6)
    assert evidence.sources == [source(1, "0123456789")]
    assert evidence.reads[0]["ranges"] == [[0, 10]]
    assert evidence.characters == 10
    fresh = SourceEvidence(catalog, max_chars=5)
    fresh.read("source-1", 5, 5)
    assert fresh.sources == [source(1, "56789")]
    with pytest.raises(ValueError, match="request|요청"):
        fresh.read("source-1", 0, 1)
    assert fresh.sources == [source(1, "56789")]


def test_evidence_manifest_rejects_unread_version_and_invalid_ranges():
    from core.source_catalog import SourceCatalog, evidence_from_reads

    catalog = SourceCatalog("", OWNER, WORKSPACE, sources=[source(1, "0123456789")])
    good = {"id": "source-1", "version": catalog.entries["source-1"]["version"], "ranges": [[2, 5]]}
    assert evidence_from_reads(catalog, [good]).sources == [source(1, "234")]
    for bad in (
        {**good, "version": "b" * 64},
        {**good, "id": "another-source"},
        {**good, "ranges": [[0, 11]]},
        {**good, "ranges": [[4, 2]]},
        {**good, "ranges": [[False, 2]]},
    ):
        with pytest.raises(ValueError):
            evidence_from_reads(catalog, [bad])
