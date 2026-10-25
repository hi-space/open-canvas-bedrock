"""The runtime reads real files and creates reviewable proposals, never writes."""
import hashlib

import pytest


OWNER = "a" * 64
WORKSPACE = "workspace-1"


@pytest.fixture
def project(tmp_path):
    directory = tmp_path / OWNER / WORKSPACE / "files"
    directory.mkdir(parents=True)
    return tmp_path, directory


def tools_for(root, **fields):
    from workspace_agent.models import Invocation
    from workspace_agent.tools import WorkspaceTools

    request = Invocation.model_validate({
        "ownerKey": OWNER,
        "workspaceId": WORKSPACE,
        "message": "문장을 다듬어 주세요.",
        "model": "global.anthropic.claude-opus-5-5",
        "history": [],
        "sources": [],
        **fields,
    })
    return WorkspaceTools(root, request)


def test_reads_exact_bom_and_line_endings_and_hashes_the_original_bytes(project):
    root, directory = project
    original = b"\xef\xbb\xbf# Title\r\nText \xf0\x9f\x98\x80\r\n"
    (directory / "article.md").write_bytes(original)
    with tools_for(root) as tools:
        result = tools.execute("read_file", {"path": "article.md"})
    assert result == {
        "path": "article.md",
        "content": "\ufeff# Title\r\nText 😀\r\n",
        "version": hashlib.sha256(original).hexdigest(),
    }


def test_proposal_uses_the_read_snapshot_after_a_concurrent_manual_save(project):
    root, directory = project
    article = directory / "article.md"
    article.write_text("Original.\n", encoding="utf-8")
    with tools_for(root) as tools:
        tools.execute("read_file", {"path": "article.md"})
        article.write_text("Manual save.\n", encoding="utf-8")
        tools.execute("propose_edit", {
            "path": "article.md", "replacement": "Revised.\n", "explanation": "Clearer phrasing.",
        })
        assert tools.proposals == [{
            "path": "article.md",
            "baseVersion": hashlib.sha256(b"Original.\n").hexdigest(),
            "baseContent": "Original.\n",
            "proposedContent": "Revised.\n",
            "explanation": "Clearer phrasing.",
        }]
        assert tools.execute("read_file", {"path": "article.md"})["content"] == "Original.\n"
    assert article.read_text() == "Manual save.\n"


def test_selection_replaces_only_the_exact_occurrence_using_python_offsets(project):
    root, directory = project
    original = "\ufeff앞 😀\r\n같은 문장\r\n같은 문장\r\n끝\r\n"
    article = directory / "article.md"
    article.write_bytes(original.encode("utf-8"))
    start = original.rindex("같은 문장")
    with tools_for(
        root,
        activePath="article.md",
        selection={"path": "article.md", "start": start, "end": start + 5, "text": "같은 문장"},
    ) as tools:
        tools.execute("propose_edit", {
            "path": "article.md", "replacement": "고친 문장", "explanation": "선택 문장만 교정합니다.",
        })
        assert tools.proposals[0]["baseContent"] == original
        assert tools.proposals[0]["proposedContent"] == "\ufeff앞 😀\r\n같은 문장\r\n고친 문장\r\n끝\r\n"
    assert article.read_bytes() == original.encode("utf-8")


def test_stale_selection_fails_before_any_proposal_is_created(project):
    root, directory = project
    (directory / "article.md").write_text("Changed", encoding="utf-8")
    with pytest.raises(ValueError, match="selection|선택"):
        with tools_for(
            root, activePath="article.md",
            selection={"path": "article.md", "start": 0, "end": 3, "text": "Old"},
        ):
            pass


def test_new_nested_file_is_a_proposal_and_no_directory_or_file_is_created(project):
    root, directory = project
    with tools_for(root) as tools:
        tools.execute("propose_edit", {
            "path": "new/chapter.md", "replacement": "# New chapter\n", "explanation": "Added chapter.",
        })
        assert tools.proposals[0]["baseVersion"] is None
        assert tools.proposals[0]["baseContent"] == ""
        assert tools.proposals[0]["proposedContent"] == "# New chapter\n"
    assert list(directory.iterdir()) == []


def test_existing_file_must_be_read_before_a_whole_document_proposal(project):
    root, directory = project
    (directory / "article.md").write_text("Do not blindly replace this.", encoding="utf-8")
    with tools_for(root) as tools:
        with pytest.raises(ValueError, match="read_file"):
            tools.execute("propose_edit", {
                "path": "article.md", "replacement": "A guess.", "explanation": "Rewritten.",
            })
        assert tools.proposals == []


@pytest.mark.parametrize("path", [
    "../other.md", "/tmp/outside.md", "folder/../../other.md", ".canvas/secrets.md",
    "folder/.hidden.md", "folder//article.md", "folder\\article.md",
    "a/b/c/d/e/f/g/h/article.md", "script.py", "nul\x00.md",
    "C:/article.md", "/".join(["a" * 170] * 3) + "/article.md", "é" * 121 + ".md",
])
def test_model_paths_cannot_escape_or_reach_private_or_unsupported_files(project, path):
    root, _ = project
    with tools_for(root) as tools:
        with pytest.raises(ValueError):
            tools.execute("read_file", {"path": path})
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {"path": path, "replacement": "bad", "explanation": "bad"})
        assert tools.proposals == []


def test_symlink_files_and_directories_cannot_be_read_or_proposed(project):
    root, directory = project
    other = root / ("b" * 64) / "other" / "files"
    other.mkdir(parents=True)
    (other / "secret.md").write_text("Other owner's secret.", encoding="utf-8")
    (directory / "alias.md").symlink_to(other / "secret.md")
    (directory / "alias").symlink_to(other, target_is_directory=True)
    with tools_for(root) as tools:
        assert tools.execute("list_files", {})["files"] == []
        for path in ("alias.md", "alias/secret.md", "alias/new.md"):
            with pytest.raises(ValueError):
                tools.execute("read_file", {"path": path})
            with pytest.raises(ValueError):
                tools.execute("propose_edit", {
                    "path": path, "replacement": "overwrite", "explanation": "unsafe",
                })
        assert tools.proposals == []
    assert (other / "secret.md").read_text() == "Other owner's secret."


def test_owner_directory_symlinks_are_rejected(tmp_path):
    actual = tmp_path / "actual"
    (actual / WORKSPACE / "files").mkdir(parents=True)
    (tmp_path / OWNER).symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError):
        with tools_for(tmp_path):
            pass


def test_opened_directory_cannot_be_redirected_by_replacing_it_with_a_symlink(project):
    root, directory = project
    (directory / "chapter").mkdir()
    (directory / "chapter" / "article.md").write_text("Workspace content.", encoding="utf-8")
    other = root / "external"
    other.mkdir()
    (other / "article.md").write_text("Other owner's content.", encoding="utf-8")
    with tools_for(root) as tools:
        (directory / "chapter").rename(directory / "original")
        (directory / "chapter").symlink_to(other, target_is_directory=True)
        with pytest.raises(ValueError):
            tools.execute("read_file", {"path": "chapter/article.md"})


def test_list_and_literal_search_stay_in_the_current_project(project):
    root, directory = project
    (directory / "notes").mkdir()
    (directory / "notes" / "article.md").write_text("alpha.*beta\nalphaXYZbeta\n", encoding="utf-8")
    (directory / ".hidden.md").write_text("alpha.*beta", encoding="utf-8")
    (directory / "unsupported.json").write_text("alpha.*beta", encoding="utf-8")
    private = directory.parent / ".canvas"
    private.mkdir()
    (private / "history.md").write_text("alpha.*beta", encoding="utf-8")
    with tools_for(root) as tools:
        assert [item["path"] for item in tools.execute("list_files", {})["files"]] == ["notes/article.md"]
        result = tools.execute("search_files", {"query": "alpha.*beta"})
        assert result["matches"] == [{
            "path": "notes/article.md", "line": 1, "text": "alpha.*beta",
        }]


def test_list_stops_at_two_hundred_files(project):
    root, directory = project
    for index in range(205):
        (directory / f"{index:03}.md").write_text("A", encoding="utf-8")
    with tools_for(root) as tools:
        result = tools.execute("list_files", {})
    assert len(result["files"]) == 200
    assert result["truncated"] is True


def test_new_file_proposals_respect_existing_and_pending_project_file_count(project):
    root, directory = project
    for index in range(199):
        (directory / f"{index:03}.md").write_text("A", encoding="utf-8")
    with tools_for(root) as tools:
        tools.execute("propose_edit", {
            "path": "first.md", "replacement": "First.", "explanation": "New file.",
        })
        with pytest.raises(ValueError, match="200|file limit"):
            tools.execute("propose_edit", {
                "path": "second.md", "replacement": "Second.", "explanation": "New file.",
            })
        assert len(tools.proposals) == 1
    assert len(list(directory.iterdir())) == 199


def test_nul_content_cannot_be_read_or_proposed(project):
    root, directory = project
    (directory / "article.md").write_bytes(b"Not\x00plain text")
    with tools_for(root) as tools:
        with pytest.raises(ValueError):
            tools.execute("read_file", {"path": "article.md"})
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": "new.md", "replacement": "Not\x00plain text", "explanation": "Invalid content.",
            })
        assert tools.proposals == []


def test_selection_job_can_read_other_files_but_only_proposes_its_selected_file(project):
    root, directory = project
    (directory / "selected.md").write_text("First passage.", encoding="utf-8")
    (directory / "context.md").write_text("Context only.", encoding="utf-8")
    with tools_for(
        root, activePath="selected.md",
        selection={"path": "selected.md", "start": 0, "end": 5, "text": "First"},
    ) as tools:
        assert tools.execute("read_file", {"path": "context.md"})["content"] == "Context only."
        with pytest.raises(ValueError, match="select|선택"):
            tools.execute("propose_edit", {
                "path": "context.md", "replacement": "Unrequested edit.", "explanation": "Invalid scope.",
            })
        assert tools.proposals == []


@pytest.mark.parametrize(
    "content", [b"x" * 200001, b"\xff", b"x" * (2 * 1024 * 1024 + 1)],
    ids=["too-many-characters", "invalid-utf8", "too-many-bytes"],
)
def test_oversized_or_non_utf8_files_are_never_given_to_the_model(project, content):
    root, directory = project
    (directory / "article.md").write_bytes(content)
    with tools_for(root) as tools:
        with pytest.raises(ValueError):
            tools.execute("read_file", {"path": "article.md"})


def test_total_read_context_is_bounded_across_distinct_files(project):
    root, directory = project
    for index in range(3):
        (directory / f"{index}.md").write_text("x" * 150000, encoding="utf-8")
    with tools_for(root) as tools:
        tools.execute("read_file", {"path": "0.md"})
        tools.execute("read_file", {"path": "1.md"})
        with pytest.raises(ValueError, match="context|문맥"):
            tools.execute("read_file", {"path": "2.md"})


@pytest.mark.parametrize("name,arguments", [
    ("read_file", {"path": "article.md", "ownerKey": "b" * 64}),
    ("list_files", {"root": "/"}),
    ("search_files", {"query": "", "workspaceId": "another"}),
    ("propose_edit", {"path": "article.md", "replacement": "", "explanation": "x", "baseContent": "fake"}),
    ("shell", {"command": "cat /etc/passwd"}),
    ("read_file", {"path": ["article.md"]}),
])
def test_tools_reject_extra_fields_wrong_types_and_shell_commands(project, name, arguments):
    root, directory = project
    (directory / "article.md").write_text("Original", encoding="utf-8")
    with tools_for(root) as tools:
        with pytest.raises(ValueError):
            tools.execute(name, arguments)
        assert tools.proposals == []


def test_proposals_cannot_drop_citations_or_invent_sources(project):
    root, directory = project
    original = "Claim [1](https://example.com/source)."
    (directory / "article.md").write_text(original, encoding="utf-8")
    with tools_for(root) as tools:
        tools.execute("read_file", {"path": "article.md"})
        for replacement in (
            "Missing citation.",
            original + "\nInvented [2](https://invented.example/source).",
        ):
            with pytest.raises(ValueError):
                tools.execute("propose_edit", {
                    "path": "article.md", "replacement": replacement, "explanation": "Revised.",
                })
        assert tools.proposals == []
    assert (directory / "article.md").read_text() == original


def test_selection_citations_resolve_reference_definitions_outside_the_selection(project):
    root, directory = project
    original = "Claim [1][report].\n\n[report]: https://example.com/report\n"
    selected = "Claim [1][report]."
    (directory / "article.md").write_text(original, encoding="utf-8")
    with tools_for(
        root, activePath="article.md",
        selection={"path": "article.md", "start": 0, "end": len(selected), "text": selected},
    ) as tools:
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": "article.md", "replacement": "Revised claim.", "explanation": "Revised.",
            })
        tools.execute("propose_edit", {
            "path": "article.md", "replacement": "Revised claim [1][report].", "explanation": "Revised.",
        })
        assert tools.proposals[0]["proposedContent"] == (
            "Revised claim [1][report].\n\n[report]: https://example.com/report\n"
        )


def test_supplied_evidence_can_be_fetched_without_network_credentials_and_cited(project, monkeypatch):
    root, _ = project
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    source = {
        "id": "report", "title": "Report", "url": "https://example.com/report",
        "excerpt": "The documented result.",
    }
    with tools_for(root, sources=[source]) as tools:
        assert tools.execute("fetch_reference", {"url": source["url"]}) == {"source": source}
        tools.execute("propose_edit", {
            "path": "new.md",
            "replacement": "The result [1](https://example.com/report).",
            "explanation": "Cited supplied evidence.",
        })
        assert len(tools.proposals) == 1


def test_unconfigured_fetch_is_a_readable_tool_error(project, monkeypatch):
    root, _ = project
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with tools_for(root) as tools:
        with pytest.raises(ValueError, match="source|참고자료"):
            tools.execute("fetch_reference", {"url": "https://example.com/new"})


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://127.0.0.1", "http://169.254.169.254/latest/meta-data",
    "http://[::1]", "http://10.1.2.3", "http://localhost", "http://service.internal",
    "https://user:password@example.com", "http://example.com:9000",
])
def test_reference_fetch_refuses_internal_networks_and_non_web_urls(project, url):
    root, _ = project
    with tools_for(root) as tools:
        with pytest.raises(ValueError):
            tools.execute("fetch_reference", {"url": url})
