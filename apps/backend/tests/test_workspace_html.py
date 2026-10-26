"""Static HTML is saved canonically and revised as exact, atomic elements."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import importlib
import json
import re

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest


SOURCE = {
    "id": "report", "title": "Report", "url": "https://example.com/report",
    "excerpt": "The report supports the result.",
}
DOCUMENT = (
    '\ufeff<!DOCTYPE html>\r\n<html lang="ko"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    "<style>@media(max-width: 40rem) { .grid {display: block} }</style>"
    '</head><body><main data-oc-id="main"><p data-oc-id="first">같음 😀</p>'
    '<section data-oc-id="second"><p data-oc-id="nested">같음 😀</p></section>'
    "</main></body></html>\r\n"
)
SELECTED = '<section data-oc-id="second"><p data-oc-id="nested">같음 😀</p></section>'
NAVIGATION_DOCUMENT = (
    '<html><body><nav><a href="#features">Features</a><a href="#">Top</a></nav>'
    '<main><section id="features"><h1>Features</h1>'
    '<p>Supported result <a href="https://example.com/report">[1]</a></p>'
    "</section></main></body></html>"
)
HISTORICAL_PROVENANCE = DOCUMENT.replace(
    '<p data-oc-id="first">같음 😀</p>',
    '<p data-oc-id="first" data-source-ids=\'["report"]\'>같음 😀 '
    '<a data-oc-id="citation" href="https://example.com/report">[1]</a></p>',
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for key, value in {
        "STORAGE_TYPE": "memory", "WORKSPACE_METADATA": "file", "WORKSPACE_ROOT": str(tmp_path),
        "WORKSPACE_AUTH_MODE": "local", "WORKSPACE_LOCAL_SUB": "html-author",
        "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
    }.items():
        monkeypatch.setenv(key, value)
    from main import app
    from api.workspaces.files import ProjectFiles

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post("/api/workspaces", json={"name": "HTML 문서"})
        assert created.status_code == 200, created.text
        workspace_id = created.json()["id"]
        files = ProjectFiles(hashlib.sha256(b"html-author").hexdigest(), workspace_id)
        yield client, files


def save(client, files, content, *, path="page.html", base_version=None):
    return client.put(f"/api/workspaces/{files.workspace}/files", json={
        "path": path, "content": content, "baseVersion": base_version,
    })


def html_module():
    return importlib.import_module("api.workspaces.html_documents")


def selected(content=DOCUMENT, text=SELECTED, *, node_id="second"):
    start = content.index(text)
    return {"path": "page.html", "start": start, "end": start + len(text), "text": text, "nodeId": node_id}


def edit(before=DOCUMENT, after=None):
    return {
        "path": "page.html", "baseContent": before, "baseVersion": hashlib.sha256(before.encode()).hexdigest(),
        "proposedContent": after if after is not None else before.replace("같음", "개정", 1),
        "explanation": "요청한 영역을 개정합니다.",
    }


@pytest.mark.parametrize("path", ["page.html", "nested/PAGE.HTM"])
def test_html_file_roundtrip_assigns_ids_without_changing_formatting(workspace, path):
    client, files = workspace
    raw = '\ufeff<!doctype html>\r\n<html><head><style>p { color: red }</style></head><body><p class=\'lead\'>😀</p><hr /></body></html>\r\n'
    response = save(client, files, raw, path=path)
    assert response.status_code == 200, response.text
    document = response.json()
    ids = re.findall(r' data-oc-id="([^"]+)"', document["content"])
    assert len(ids) == len(set(ids)) == 2
    assert re.sub(r' data-oc-id="[^"]+"', "", document["content"]) == raw
    assert document["bytes"] == len(document["content"].encode("utf-8"))
    assert document["version"] == hashlib.sha256(document["content"].encode("utf-8")).hexdigest()
    listed = client.get(f"/api/workspaces/{files.workspace}").json()["files"]
    assert [item["path"] for item in listed] == [path]
    repeated = save(client, files, document["content"], path=path, base_version=document["version"])
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == document
    assert files.history(path) == []


def test_existing_ids_and_void_element_source_offsets_are_stable():
    module = html_module()
    raw = '<body><section data-oc-id="stable">😀<br data-oc-id="break" /></section></body>'
    assert module.prepare_html(raw) == raw
    result = module.html_selection(raw, "break")
    start = raw.index("<br")
    assert result == {"start": start, "end": start + len('<br data-oc-id="break" />'), "text": '<br data-oc-id="break" />', "nodeId": "break"}


@pytest.mark.parametrize("raw,attribute,value", [
    ("<p class=foo/>hello</p>", "class", "foo/"),
    ("<img src=https://example.org/pic/>", "src", "https://example.org/pic/"),
    ("<img src=https://example.org/pic/ />", "src", "https://example.org/pic/"),
])
def test_id_insertion_preserves_unquoted_attribute_slashes_and_valid_html(workspace, raw, attribute, value):
    client, files = workspace
    saved = save(client, files, raw)
    assert saved.status_code == 200, saved.text
    content = saved.json()["content"]
    attributes = []

    class AttributeParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attributes.append(dict(attrs))

    parser = AttributeParser()
    parser.feed(content)
    assert attributes[0][attribute] == value
    assert "data-oc-id" in attributes[0]
    assert html_module().prepare_html(content) == content
    html_module().validate_html(content)
    assert files.read("page.html")["content"] == content


def test_generated_html_with_unquoted_trailing_slash_attribute_remains_valid():
    from api.workspaces.proposals import create_proposal

    proposal = create_proposal({
        "path": "new.html", "baseContent": "", "baseVersion": None,
        "proposedContent": "<p class=foo/>hello</p>", "explanation": "HTML 생성",
    }, "job", "생성", [])
    assert re.fullmatch(r'<p class=foo/ data-oc-id="[^"]+">hello</p>', proposal["proposedContent"])
    assert html_module().prepare_html(proposal["proposedContent"]) == proposal["proposedContent"]


def test_duplicate_and_invalid_ids_become_unique_without_losing_the_first_id():
    module = html_module()
    raw = '<body><p data-oc-id="same">One</p><p data-oc-id="same">Two</p><p data-oc-id="bad id">Three</p></body>'
    result = module.prepare_html(raw)
    ids = re.findall(r'data-oc-id="([^"]+)"', result)
    assert ids[0] == "same"
    assert len(ids) == len(set(ids)) == 3
    assert all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", item) for item in ids)
    assert module.prepare_html(result) == result
    assert module.prepare_html(raw) == result


def test_encoded_markup_remains_literal_text_and_keeps_exact_source_selection():
    module = html_module()
    raw = '<p data-oc-id="literal">&lt;script&gt;literal&lt;/script&gt; &amp; &#60;</p>'
    assert module.prepare_html(raw) == raw
    assert module.html_selection(raw, "literal")["text"] == raw


@pytest.mark.parametrize("content", [
    "<body><section><p>unclosed</section></body>",
    "<body><p>browser repairs <div>nesting</div></p></body>",
    "<body><table><p>fostered outside table</p></table></body>",
    '<body><script>alert(1)</script></body>',
    '<body><p ONCLICK="alert(1)">Event</p></body>',
    '<body><iframe srcdoc="<p>frame</p>"></iframe></body>',
    '<html><head><meta http-equiv="refresh" content="0;url=https://example.com"></head><body></body></html>',
    '<html><head><base href="https://example.com"></head><body></body></html>',
    '<html><head><link rel="stylesheet" href="https://example.com/a.css"></head><body></body></html>',
    '<body><a href="java&#x73;cript:alert(1)">Unsafe</a></body>',
    '<body><a href="java&#x0a;script:alert(1)">Unsafe</a></body>',
    '<body><svg><script>alert(1)</script></svg></body>',
    '<body><template><script>alert(1)</script></template></body>',
    '<body><p data-oc-id="one" data-oc-id="two">Duplicate attribute</p></body>',
    '<body><p data-source-ids=\'{"report": true}\'>Wrong metadata</p></body>',
    '<body><p data-source-ids=\'["report", 3]\'>Wrong metadata</p></body>',
    '<body><p style="behavior:url(x.htc)">Active CSS</p></body>',
    '<style>@import "https://example.com/styles.css";</style><p>External CSS</p>',
    '<p style="background: u/**/rl(https://example.com/track)">External CSS</p>',
    '<p style="background: \\75rl(https://example.com/track)">Escaped external CSS</p>',
    '<tr><td>A row without its table</td></tr>',
    '<td>A cell without its row</td>',
    '<ruby><rt>Implicit close<rp>wrong nesting</rp></rt></ruby>',
    '<table><caption>Implicit close<table><tr><td>Nested table</td></tr></table></caption></table>',
    '<p data-oc-id="outer"><summary data-oc-id="inner">Implicit close</summary></p>',
    '<table>&nbsp;<tr><td>Fostered text</td></tr></table>',
    '<table>\u00a0<tr><td>Fostered text</td></tr></table>',
    '<table>&#x2003;<tr><td>Fostered text</td></tr></table>',
    '<html><head>&nbsp;</head><body>Moved text</body></html>',
    '<html><head></head>&#x2003;<body>Moved text</body></html>',
])
def test_unsafe_or_malformed_html_cannot_be_saved(workspace, content):
    client, files = workspace
    response = save(client, files, content)
    assert response.status_code == 422, response.text
    assert files.read("page.html", missing=True) is None


def test_deeply_nested_provenance_is_a_validation_error_without_server_failure(workspace):
    client, files = workspace
    content = "<p data-source-ids='" + "[" * 10000 + '"report"' + "]" * 10000 + "'>Deep metadata</p>"
    response = save(client, files, content)
    assert response.status_code == 422, response.text
    assert files.read("page.html", missing=True) is None


def test_size_limit_is_checked_after_id_insertion(workspace):
    client, files = workspace
    content = "<body><p>" + "x" * 199978 + "</p></body>"
    assert len(content) < 200000
    response = save(client, files, content)
    assert response.status_code == 422, response.text


def test_manual_save_preserves_well_formed_source_metadata_after_source_removal(workspace):
    client, files = workspace
    response = save(client, files, '<p data-source-ids=\'["removed-source"]\'>Evidence</p>')
    assert response.status_code == 200, response.text
    assert 'data-source-ids=\'["removed-source"]\'' in response.json()["content"]


def test_removing_a_source_still_allows_unrelated_selected_edit_and_approval(workspace, monkeypatch):
    from workspace_agent.models import Invocation
    from workspace_agent.tools import WorkspaceTools

    client, files = workspace
    added = client.post(f"/api/workspaces/{files.workspace}/sources", json=SOURCE)
    assert added.status_code == 200, added.text
    saved = save(client, files, HISTORICAL_PROVENANCE)
    assert saved.status_code == 200, saved.text
    removed = client.delete(f"/api/workspaces/{files.workspace}/sources/report")
    assert removed.status_code == 200, removed.text
    replacement = '<section data-oc-id="second"><p data-oc-id="nested">고친 문장</p></section>'

    def invoke_tools(payload):
        with WorkspaceTools(files.root, Invocation.model_validate(payload)) as tools:
            tools.execute("propose_edit", {
                "path": "page.html", "replacement": replacement, "explanation": "선택 영역만 교정",
            })
            return {"message": "교정안", "proposals": tools.proposals, "events": tools.events}

    monkeypatch.setattr("api.workspaces.service.invoke_agent", invoke_tools)
    start = HISTORICAL_PROVENANCE.index(SELECTED)
    response = client.post(f"/api/workspaces/{files.workspace}/chat", json={
        "message": "선택 영역만 교정", "requestId": "after-source-removal", "activePath": "page.html",
        "activeVersion": saved.json()["version"],
        "selection": {
            "from": len(HISTORICAL_PROVENANCE[:start].encode("utf-16-le")) // 2,
            "to": len(HISTORICAL_PROVENANCE[:start + len(SELECTED)].encode("utf-16-le")) // 2,
            "text": SELECTED, "nodeId": "second",
        },
    })
    assert response.status_code == 202, response.text
    job = client.get(f"/api/workspaces/{files.workspace}/jobs/{response.json()['job']['id']}").json()
    assert job["status"] == "completed", job
    assert len(job["proposalIds"]) == 1
    approved = client.post(f"/api/workspaces/{files.workspace}/proposals/{job['proposalIds'][0]}/decisions", json={
        "decisions": {"c0": "accepted"},
    })
    assert approved.status_code == 200, approved.text
    assert approved.json()["file"]["content"] == HISTORICAL_PROVENANCE.replace(SELECTED, replacement)
    assert client.get(f"/api/workspaces/{files.workspace}").json()["sources"] == []


def test_imported_historical_provenance_survives_whole_document_proposal_and_approval(workspace):
    from api.workspaces.proposals import apply_decisions, create_proposal

    client, files = workspace
    saved = save(client, files, HISTORICAL_PROVENANCE)
    assert saved.status_code == 200, saved.text
    after = HISTORICAL_PROVENANCE.replace("같음", "Imported source retained", 1)
    proposal = create_proposal(edit(HISTORICAL_PROVENANCE, after), "job", "교정", [])
    with files.lock():
        files.put_proposal(proposal)
        result = apply_decisions(files, proposal["id"], {"c0": "accepted"})
    assert result["file"]["content"] == after
    assert 'data-source-ids=\'["report"]\'' in result["file"]["content"]


def test_historical_provenance_does_not_authorize_new_ids_at_creation_or_approval(workspace):
    from api.workspaces.proposals import apply_decisions, create_proposal

    client, files = workspace
    saved = save(client, files, HISTORICAL_PROVENANCE)
    assert saved.status_code == 200, saved.text
    after = HISTORICAL_PROVENANCE.replace("같음", "Revised", 1)
    proposal = create_proposal(edit(HISTORICAL_PROVENANCE, after), "job", "교정", [])
    invented = after.replace('["report"]', '["report","invented"]')
    with pytest.raises(ValueError):
        create_proposal(edit(HISTORICAL_PROVENANCE, invented), "job", "교정", [])
    proposal["changes"][0]["after"] = invented
    with files.lock():
        files.put_proposal(proposal)
        with pytest.raises(HTTPException) as rejected:
            apply_decisions(files, proposal["id"], {"c0": "accepted"})
    assert rejected.value.status_code == 409
    assert files.read("page.html")["content"] == HISTORICAL_PROVENANCE


def test_html_selection_resolves_the_exact_element_after_emoji(workspace):
    client, files = workspace
    saved = save(client, files, DOCUMENT)
    assert saved.status_code == 200, saved.text
    from api.workspaces.models import ChatRequest
    from api.workspaces.service import prepare_job

    start = DOCUMENT.index(SELECTED)
    payload = {
        "message": "이 영역만 수정", "requestId": "selected", "activePath": "page.html",
        "activeVersion": saved.json()["version"],
        "selection": {
            "from": len(DOCUMENT[:start].encode("utf-16-le")) // 2,
            "to": len(DOCUMENT[:start + len(SELECTED)].encode("utf-16-le")) // 2,
            "text": SELECTED, "nodeId": "second",
        },
    }
    with files.lock():
        _, result = prepare_job(files, ChatRequest.model_validate(payload))
    assert result["selection"] == selected()


@pytest.mark.parametrize("node_id,text", [
    ("first", SELECTED), ("missing", SELECTED), (None, SELECTED), ("second", "같음 😀"),
])
def test_html_selection_cannot_lie_about_node_or_select_partial_text(workspace, node_id, text):
    client, files = workspace
    saved = save(client, files, DOCUMENT)
    assert saved.status_code == 200, saved.text
    start = DOCUMENT.index(text)
    response = client.post(f"/api/workspaces/{files.workspace}/chat", json={
        "message": "영역 수정", "requestId": "bad-selection", "activePath": "page.html",
        "activeVersion": saved.json()["version"],
        "selection": {"from": len(DOCUMENT[:start].encode("utf-16-le")) // 2,
                      "to": len(DOCUMENT[:start + len(text)].encode("utf-16-le")) // 2,
                      "text": text, "nodeId": node_id},
    })
    assert response.status_code in {409, 422}, response.text
    assert files.read("page.html")["content"] == DOCUMENT


def test_html_selection_proposal_is_one_whole_element_and_preserves_outside_bytes():
    from api.workspaces.proposals import create_proposal

    replacement = '<article data-oc-id="second"><h2>다른 제목</h2><p style="color: red">다른 문장</p></article>'
    proposal = create_proposal(edit(after=DOCUMENT.replace(SELECTED, replacement)), "job", "영역 수정", [], selected())
    assert len(proposal["changes"]) == 1
    change = proposal["changes"][0]
    assert change["before"] == SELECTED
    assert change["after"].startswith('<article data-oc-id="second">')
    assert len(re.findall(r'data-oc-id=', change["after"])) == 3
    start = DOCUMENT.index(SELECTED)
    assert change["from"] == len(DOCUMENT[:start].encode("utf-16-le")) // 2
    assert change["to"] == len(DOCUMENT[:start + len(SELECTED)].encode("utf-16-le")) // 2
    assert proposal["proposedContent"] == DOCUMENT[:start] + change["after"] + DOCUMENT[start + len(SELECTED):]


def test_selection_descendant_cannot_reuse_an_id_owned_outside_the_selection():
    from api.workspaces.proposals import create_proposal

    replacement = '<section data-oc-id="second"><p data-oc-id="first">New descendant</p></section>'
    proposal = create_proposal(edit(after=DOCUMENT.replace(SELECTED, replacement)), "job", "영역 수정", [], selected())
    content = proposal["proposedContent"]
    assert '<p data-oc-id="first">같음 😀</p>' in content
    assert '<p data-oc-id="first">New descendant</p>' not in content
    ids = re.findall(r'data-oc-id="([^"]+)"', content)
    assert len(ids) == len(set(ids))
    assert content == DOCUMENT.replace(SELECTED, proposal["changes"][0]["after"])


def test_table_row_selection_is_valid_in_its_original_table_context():
    from api.workspaces.proposals import create_proposal

    before = '<table data-oc-id="table"><tbody data-oc-id="body"><tr data-oc-id="row"><td data-oc-id="cell">Old</td></tr></tbody></table>'
    old = '<tr data-oc-id="row"><td data-oc-id="cell">Old</td></tr>'
    replacement = '<tr data-oc-id="row"><td>New</td></tr>'
    proposal = create_proposal(edit(before, before.replace(old, replacement)), "job", "표 수정", [],
                               selected(before, old, node_id="row"))
    assert proposal["changes"][0]["before"] == old
    assert re.search(r'<td data-oc-id="[^"]+">New</td>', proposal["changes"][0]["after"])
    assert proposal["proposedContent"].startswith('<table data-oc-id="table"><tbody data-oc-id="body">')


@pytest.mark.parametrize("replacement", [
    '<section data-oc-id="different">Changed root</section>',
    '<section>No root ID</section>',
    '<section data-oc-id="second">First</section><aside>Sibling</aside>',
    '<section data-oc-id="second">Unclosed',
    '<section data-oc-id="second"><style>body {display: none}</style></section>',
    '<section data-oc-id="second"><p data-source-ids=\'["invented"]\'>Invented provenance</p></section>',
])
def test_selection_proposal_rejects_invalid_replacement_or_global_styles(replacement):
    from api.workspaces.proposals import create_proposal

    with pytest.raises((HTTPException, ValueError)):
        create_proposal(edit(after=DOCUMENT.replace(SELECTED, replacement)), "job", "영역 수정", [], selected())


def test_selection_proposal_cannot_rewrite_outside_or_use_wrong_node():
    from api.workspaces.proposals import create_proposal

    for changed, selection in [
        (DOCUMENT.replace("같음", "외부 변경"), selected()),
        (DOCUMENT.replace(SELECTED, '<section data-oc-id="second">Changed</section>'), selected(node_id="first")),
    ]:
        with pytest.raises((HTTPException, ValueError)):
            create_proposal(edit(after=changed), "job", "영역 수정", [], selection)


def test_html_whole_document_proposal_is_atomic_and_keeps_empty_new_file_base(workspace):
    from api.workspaces.proposals import apply_decisions, create_proposal

    client, files = workspace
    content = (
        '<html><head><style>p {color: red}</style></head><body>'
        '<p data-source-ids=\'["report"]\'>Supported <a href="https://example.com/report">[1]</a></p>'
        "</body></html>"
    )
    proposal = create_proposal({
        "path": "new.html", "baseVersion": None, "baseContent": "", "proposedContent": content,
        "explanation": "HTML 문서를 만듭니다.",
    }, "job", "문서 생성", [SOURCE])
    assert proposal["baseContent"] == ""
    assert proposal["baseVersion"] is None
    assert len(proposal["changes"]) == 1
    assert proposal["changes"][0]["before"] == ""
    assert proposal["changes"][0]["after"] == proposal["proposedContent"]
    assert 'data-source-ids=\'["report"]\'' in proposal["proposedContent"]
    with files.lock():
        files.put_proposal(proposal)
        result = apply_decisions(files, proposal["id"], {"c0": "accepted"})
    assert result["file"]["content"] == proposal["proposedContent"]
    assert result["file"]["version"] == result["proposal"]["appliedVersion"]
    assert result["proposal"]["status"] == "accepted"


def test_generated_html_navigation_and_external_citations_survive_atomic_approval(workspace):
    from api.workspaces.proposals import apply_decisions, create_proposal

    _, files = workspace
    proposal = create_proposal({
        "path": "navigation.html", "baseVersion": None, "baseContent": "",
        "proposedContent": NAVIGATION_DOCUMENT, "explanation": "탐색과 출처를 포함한 문서",
    }, "job", "새 HTML", [SOURCE])
    assert 'href="#features"' in proposal["proposedContent"]
    assert 'href="#"' in proposal["proposedContent"]
    assert 'href="https://example.com/report"' in proposal["proposedContent"]
    with files.lock():
        files.put_proposal(proposal)
        result = apply_decisions(files, proposal["id"], {"c0": "accepted"})
    assert result["file"]["content"] == proposal["proposedContent"]
    assert result["proposal"]["status"] == "accepted"


def test_html_navigation_never_substitutes_for_a_retained_citation(workspace):
    from api.workspaces.proposals import apply_decisions, create_proposal

    client, files = workspace
    saved = save(client, files, NAVIGATION_DOCUMENT)
    assert saved.status_code == 200, saved.text
    before = saved.json()["content"]
    after = before.replace("Supported result", "Clarified result")
    proposal = create_proposal(edit(before, after), "job", "개정", [SOURCE])
    missing_citation = after.replace(' href="https://example.com/report"', "")
    with pytest.raises(HTTPException):
        create_proposal(edit(before, missing_citation), "job", "개정", [SOURCE])
    tampered = deepcopy(proposal)
    tampered["changes"][0]["after"] = missing_citation
    with files.lock():
        files.put_proposal(tampered)
        with pytest.raises(HTTPException) as rejected:
            apply_decisions(files, tampered["id"], {"c0": "accepted"})
    assert rejected.value.status_code == 409
    assert files.read("page.html")["content"] == before


def test_html_citations_cannot_be_replaced_by_source_metadata():
    from api.workspaces.proposals import create_proposal

    before = '<p data-oc-id="cite">Claim <a data-oc-id="link" href="https://example.com/report">[1]</a></p>'
    with pytest.raises(HTTPException):
        create_proposal(edit(before, '<p data-oc-id="cite" data-source-ids=\'["report"]\'>Claim</p>'),
                        "job", "교정", [SOURCE])


def test_atomic_html_approval_revalidates_assembled_html_and_base_version(workspace):
    from api.workspaces.proposals import apply_decisions, create_proposal

    client, files = workspace
    saved = save(client, files, DOCUMENT)
    assert saved.status_code == 200, saved.text
    proposal = create_proposal(edit(), "job", "교정", [])
    bad = deepcopy(proposal)
    bad["changes"][0]["after"] = '<script>alert("must not persist")</script>'
    with files.lock():
        files.put_proposal(bad)
        with pytest.raises(HTTPException):
            apply_decisions(files, bad["id"], {"c0": "accepted"})
    assert files.read("page.html")["content"] == DOCUMENT
    with files.lock():
        files.put_proposal(proposal)
        files.save("page.html", DOCUMENT.replace("같음", "수동 수정"), saved.json()["version"])
        with pytest.raises(HTTPException) as conflict:
            apply_decisions(files, proposal["id"], {"c0": "accepted"})
    assert conflict.value.status_code == 409
    assert "수동 수정" in files.read("page.html")["content"]


def test_html_generation_routes_output_format_through_api_and_rejects_selections(workspace, monkeypatch):
    from api.workspaces.models import ChatRequest
    from api.workspaces.service import prepare_job

    client, files = workspace
    monkeypatch.setattr("api.workspaces.research.run_research", lambda *args: {"message": "완료", "proposals": []})
    monkeypatch.setattr("api.workspaces.service.invoke_agent", lambda *args: {"message": "완료", "proposals": []})
    for extra in [
        {"selection": {"from": 0, "to": 1, "text": "x"}},
        {"researchGenre": "blog", "selection": {"from": 0, "to": 1, "text": "x"}},
    ]:
        response = client.post(f"/api/workspaces/{files.workspace}/chat", json={
            "message": "HTML 생성", "requestId": "invalid-mode", "outputFormat": "html", **extra,
        })
        assert response.status_code == 422, response.text
    with files.lock():
        _, payload = prepare_job(files, ChatRequest.model_validate({
            "message": "HTML 생성", "requestId": "html-generation", "outputFormat": "html",
        }))
    assert payload["outputFormat"] == "html"


@pytest.mark.parametrize("path", ["wrong.md", "page.html"])
def test_api_generation_rejects_forged_format_or_existing_path(workspace, monkeypatch, path):
    client, files = workspace
    saved = save(client, files, DOCUMENT)
    assert saved.status_code == 200, saved.text
    monkeypatch.setattr("api.workspaces.service.invoke_agent", lambda _payload: {
        "message": "HTML 생성", "proposals": [{
            "path": path, "baseVersion": None, "baseContent": "", "proposedContent": "<p>Overwrite</p>",
            "explanation": "A forged new file.",
        }],
    })
    response = client.post(f"/api/workspaces/{files.workspace}/chat", json={
        "message": "새 HTML 문서", "requestId": "forged-output", "outputFormat": "html",
    })
    assert response.status_code == 202, response.text
    job = client.get(f"/api/workspaces/{files.workspace}/jobs/{response.json()['job']['id']}").json()
    assert job["status"] == "failed"
    assert job["proposalIds"] == []
    assert files.read("page.html")["content"] == DOCUMENT


@pytest.fixture
def agent_project(tmp_path):
    from workspace_agent.models import Invocation
    from workspace_agent.tools import WorkspaceTools

    directory = tmp_path / ("a" * 64) / "workspace-1" / "files"
    directory.mkdir(parents=True)

    def tools(**fields):
        return WorkspaceTools(tmp_path, Invocation.model_validate({
            "ownerKey": "a" * 64, "workspaceId": "workspace-1", "message": "영역 수정",
            "history": [], "sources": [], **fields,
        }))
    return directory, tools


def test_agent_lists_reads_and_replaces_only_selected_html_element(agent_project):
    directory, tools_for = agent_project
    (directory / "page.html").write_bytes(DOCUMENT.encode("utf-8"))
    with tools_for(activePath="page.html", selection=selected()) as tools:
        assert tools.execute("list_files", {})["files"][0]["path"] == "page.html"
        assert tools.execute("read_file", {"path": "page.html"})["content"] == DOCUMENT
        tools.execute("propose_edit", {
            "path": "page.html", "replacement": '<section data-oc-id="second"><h2>새 제목</h2></section>',
            "explanation": "영역만 수정",
        })
        result = tools.proposals[0]
        assert result["baseContent"] == DOCUMENT
        start = DOCUMENT.index(SELECTED)
        assert result["proposedContent"][:start] == DOCUMENT[:start]
        assert result["proposedContent"].endswith(DOCUMENT[start + len(SELECTED):])
        assert re.search(r'<h2 data-oc-id="[^"]+">새 제목</h2>', result["proposedContent"])
    assert (directory / "page.html").read_bytes() == DOCUMENT.encode("utf-8")


def test_agent_can_generate_html_with_fragment_navigation_and_evidence_links(agent_project):
    _, tools_for = agent_project
    with tools_for(outputFormat="html", sources=[SOURCE]) as tools:
        tools.execute("read_source", {"id": SOURCE["id"]})
        tools.execute("propose_edit", {
            "path": "navigation.html", "replacement": NAVIGATION_DOCUMENT,
            "explanation": "페이지 탐색 및 출처",
        })
        content = tools.proposals[0]["proposedContent"]
    assert 'href="#features"' in content
    assert 'href="#"' in content
    assert 'href="https://example.com/report"' in content


def test_agent_html_selection_can_add_navigation_to_target_outside_its_subtree(agent_project):
    directory, tools_for = agent_project
    before = (
        '<nav data-oc-id="navigation"><a data-oc-id="nav" href="#overview">Overview</a></nav>'
        '<section data-oc-id="overview" id="overview">Overview</section>'
        '<section data-oc-id="features" id="features">Features</section>'
    )
    old = '<a data-oc-id="nav" href="#overview">Overview</a>'
    replacement = '<a data-oc-id="nav" href="#features">Features</a>'
    (directory / "page.html").write_bytes(before.encode("utf-8"))
    with tools_for(activePath="page.html", selection=selected(before, old, node_id="nav")) as tools:
        tools.execute("propose_edit", {
            "path": "page.html", "replacement": replacement, "explanation": "탐색 대상 변경",
        })
        assert tools.proposals[0]["proposedContent"] == before.replace(old, replacement)


@pytest.mark.parametrize("href", [
    "https://invented.example/report#features", "//invented.example/report#features",
    "other.html#features", "javascript:alert(1)", "data:text/html,bad",
])
def test_html_navigation_exception_does_not_allow_unsupported_or_unsafe_links(agent_project, href):
    from api.workspaces.proposals import create_proposal

    _, tools_for = agent_project
    content = NAVIGATION_DOCUMENT.replace('href="#features"', f'href="{href}"')
    with pytest.raises((HTTPException, ValueError)):
        create_proposal({
            "path": "new.html", "baseVersion": None, "baseContent": "", "proposedContent": content,
            "explanation": "Invalid navigation.",
        }, "job", "HTML 생성", [SOURCE])
    with tools_for(outputFormat="html", sources=[SOURCE]) as tools:
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": "new.html", "replacement": content, "explanation": "Invalid navigation.",
            })
        assert tools.proposals == []


def test_agent_html_navigation_does_not_allow_dropping_an_external_citation(agent_project):
    directory, tools_for = agent_project
    before = html_module().prepare_html(NAVIGATION_DOCUMENT)
    (directory / "page.html").write_bytes(before.encode("utf-8"))
    with tools_for(activePath="page.html", sources=[SOURCE]) as tools:
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": "page.html", "replacement": before.replace(' href="https://example.com/report"', ""),
                "explanation": "Dropped source.",
            })
        assert tools.proposals == []


@pytest.mark.parametrize("content", ['[Features](#features)', '<a href="#features">Features</a>'])
def test_html_navigation_exception_does_not_change_markdown_citation_rules(agent_project, content):
    from api.workspaces.proposals import create_proposal

    _, tools_for = agent_project
    with pytest.raises(HTTPException):
        create_proposal({
            "path": "new.md", "baseVersion": None, "baseContent": "", "proposedContent": content,
            "explanation": "Same existing citation policy.",
        }, "job", "Markdown 생성", [])
    with tools_for() as tools:
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": "new.md", "replacement": content, "explanation": "Same existing citation policy.",
            })
        assert tools.proposals == []


def test_agent_rejects_wrong_html_node_even_when_text_offsets_match(agent_project):
    directory, tools_for = agent_project
    (directory / "page.html").write_bytes(DOCUMENT.encode("utf-8"))
    with pytest.raises(ValueError):
        with tools_for(activePath="page.html", selection=selected(node_id="first")):
            pass


def test_agent_preserves_historical_provenance_without_accepting_new_ids(agent_project):
    directory, tools_for = agent_project
    (directory / "page.html").write_bytes(HISTORICAL_PROVENANCE.encode("utf-8"))
    with tools_for(activePath="page.html", selection=selected(HISTORICAL_PROVENANCE)) as tools:
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": "page.html",
                "replacement": '<section data-oc-id="second" data-source-ids=\'["invented"]\'>New</section>',
                "explanation": "Invented identity.",
            })
        assert tools.proposals == []
        tools.execute("propose_edit", {
            "path": "page.html", "replacement": '<section data-oc-id="second">New</section>',
            "explanation": "Unrelated edit.",
        })
        assert 'data-source-ids=\'["report"]\'' in tools.proposals[0]["proposedContent"]


@pytest.mark.parametrize("path", ["page.html", "new.md", "new.htm"])
def test_html_output_format_cannot_overwrite_existing_or_propose_other_formats(agent_project, path):
    directory, tools_for = agent_project
    (directory / "page.html").write_bytes(DOCUMENT.encode("utf-8"))
    with tools_for(outputFormat="html") as tools:
        tools.execute("read_file", {"path": "page.html"})
        with pytest.raises(ValueError):
            tools.execute("propose_edit", {
                "path": path, "replacement": "<p>New</p>", "explanation": "HTML 생성",
            })
        assert tools.proposals == []
        tools.execute("propose_edit", {
            "path": "new.html", "replacement": "<p>New</p>", "explanation": "HTML 생성",
        })
        assert tools.proposals[0]["baseContent"] == ""
        assert re.search(r'<p data-oc-id="[^"]+">New</p>', tools.proposals[0]["proposedContent"])


def test_html_generation_reaches_the_model_as_explicit_context(agent_project, monkeypatch):
    from workspace_agent.agent import run_agent

    directory, _ = agent_project
    monkeypatch.setenv("WORKSPACE_ROOT", str(directory.parents[2]))
    captured = []

    class Bedrock:
        def converse(self, **request):
            captured.append(request)
            return {
                "stopReason": "end_turn", "output": {"message": {"role": "assistant", "content": [{"text": "완료"}]}},
                "usage": {"outputTokens": 10},
            }
    monkeypatch.setattr("workspace_agent.agent.boto3.client", lambda *args, **kwargs: Bedrock())
    result = run_agent({
        "ownerKey": "a" * 64, "workspaceId": "workspace-1", "message": "HTML 생성",
        "outputFormat": "html", "history": [], "sources": [],
    })
    assert result["message"] == "완료"
    context = json.loads(captured[0]["messages"][0]["content"][0]["text"])
    assert context["outputFormat"] == "html"
