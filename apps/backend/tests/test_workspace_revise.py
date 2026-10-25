"""Whole-document revisions run as bounded, parallel section rewrites."""
import json
import threading
import time

import pytest


def section_reply(text, reason="end_turn"):
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": reason,
        "usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20},
    }


def passage_of(request):
    return json.loads(request["messages"][0]["content"][0]["text"])["passage"]


def test_sections_rejoin_exactly_and_never_split_code_or_tables():
    from workspace_agent.revise import split_sections

    paragraph = "문단 " * 400 + "\r\n\r\n"
    code = "```python\n" + "line\n\n" * 600 + "```\n\n"
    document = "﻿# 제목\r\n\r\n" + paragraph * 3 + "## 코드\n\n" + code + paragraph + "| a |\n| - |\n| b |\n"
    sections = split_sections(document, target=3000)
    assert "".join(sections) == document
    assert len(sections) > 3
    assert any(code.strip() in section for section in sections)
    assert any(section.startswith("## 코드") for section in sections)


@pytest.mark.parametrize("opening,example,closing", [
    ("````markdown", "```", "````"),
    ("```text", "```not-a-closing-fence", "```"),
    ("```text", "    ```", "```"),
    ("```text", "\t```", "```"),
    ("~~~~text", "~~~", "~~~~"),
    ("```text", "~~~", "```"),
])
def test_section_splitter_keeps_complete_fences_with_code_that_resembles_a_closer(opening, example, closing):
    from workspace_agent.revise import split_sections

    code = (
        opening + "\r\n" + "first code line\r\n\r\n" * 250 + example
        + "\r\n\r\n# This heading is code\r\n\r\n" + "second code line\r\n\r\n" * 250
        + closing + "\r\n"
    )
    document = (
        "\ufeff# 시작 😀\r\n\r\n" + "앞 문단입니다. " * 300 + "\r\n\r\n"
        + "## Examples\r\n\r\n" + code + "\r\n## After\r\n\r\n" + "뒤 문단입니다. " * 300 + "\r\n"
    )
    sections = split_sections(document, target=1000)
    assert "".join(sections) == document
    assert len(sections) >= 3
    assert any(code in section for section in sections)
    assert any(section.startswith("## Examples") for section in sections)
    assert any(section.startswith("## After") for section in sections)


def test_sections_are_revised_in_parallel_and_keep_surrounding_whitespace():
    from workspace_agent.revise import revise_sections

    active = []
    peak = []
    lock = threading.Lock()

    def converse(**request):
        with lock:
            active.append(1)
            peak.append(len(active))
        time.sleep(0.05)
        with lock:
            active.pop()
        return section_reply(passage_of(request).replace("긴 표현", "짧게"))

    sections = [f"\n문단 {index} 긴 표현.\n\n" for index in range(6)]
    revised, kept = revise_sections(
        sections, "간결하게", converse=converse, validate=lambda before, after: None,
        deadline=time.monotonic() + 30, workers=6,
    )
    assert revised == [f"\n문단 {index} 짧게.\n\n" for index in range(6)]
    assert kept == []
    assert max(peak) > 1


def test_rejected_section_is_retried_with_feedback_then_kept_unchanged():
    from workspace_agent.revise import revise_sections

    requests = []

    def converse(**request):
        requests.append(request)
        passage = passage_of(request)
        return section_reply("링크를 지웠습니다." if "출처" in passage else passage + " 수정")

    def validate(before, after):
        if "링크를 지웠습니다" in after:
            raise ValueError("AI가 기존 출처 링크를 누락했습니다.")

    sections = ["출처 [1](https://example.com/a).", "\n\n일반 문단."]
    revised, kept = revise_sections(
        sections, "간결하게", converse=converse, validate=validate,
        deadline=time.monotonic() + 30, workers=2,
    )
    assert revised == ["출처 [1](https://example.com/a).", "\n\n일반 문단. 수정"]
    assert kept == [1]
    retry = [item for item in requests if "출처" in passage_of(item)][1]
    assert "기존 출처 링크를 누락" in json.loads(retry["messages"][0]["content"][0]["text"])["rejected"]


@pytest.mark.parametrize("reply", [section_reply("잘림", reason="max_tokens"), section_reply("   ")])
def test_incomplete_or_empty_section_replies_keep_the_original(reply):
    from workspace_agent.revise import revise_sections

    revised, kept = revise_sections(
        ["원문."], "간결하게", converse=lambda **_request: reply,
        validate=lambda before, after: None, deadline=time.monotonic() + 30, workers=1,
    )
    assert revised == ["원문."] and kept == [1]


def test_sections_unfinished_at_the_deadline_keep_the_original():
    from workspace_agent.revise import revise_sections

    release = threading.Event()

    def converse(**request):
        if "느린" in passage_of(request):
            release.wait(5)
        return section_reply(passage_of(request) + "!")

    try:
        revised, kept = revise_sections(
            ["빠른.", "느린."], "간결하게", converse=converse,
            validate=lambda before, after: None, deadline=time.monotonic() + 0.3, workers=2,
        )
    finally:
        release.set()
    assert revised == ["빠른.!", "느린."] and kept == [2]
