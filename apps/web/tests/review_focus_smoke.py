"""Revision-to-source navigation checks against the local deterministic backend.

Start cloud_workspace_backend.py and Next as described in cloud_workspace_smoke.py.
Run OPEN_CANVAS_TEST_URL=http://127.0.0.1:3102 python tests/review_focus_smoke.py.
"""
import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from playwright.async_api import async_playwright, expect
from cloud_workspace_smoke import create_project, read_file, send

BASE = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3102")
ARTIFACTS = Path(os.environ.get("OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-review-focus-browser"))
UNCHANGED = "\r\n\r\n".join(
    f"## 기록 {number}\r\n\r\n이 문단은 수정하지 않습니다. 긴 글을 검토할 때도 본문 위치를 정확하게 찾을 수 있어야 합니다."
    for number in range(1, 15)
)
SAMPLE = (
    "\ufeff# 수정안과 본문 연결 😀\r\n\r\n첫 문장 입니다.\r\n\r\n"
    + UNCHANGED
    + "\r\n\r\n같은 문장 입니다.\r\n\r\n같은 문장 입니다.\r\n"
)


async def open_latest_review(page):
    await page.get_by_role("button", name=re.compile("검토할 수정안 1개")).last.click()
    await expect(page.get_by_text("AI 수정 제안", exact=True)).to_be_visible()

async def request_review(page, message):
    await page.get_by_role("tab", name="대화", exact=True).click()
    buttons = page.get_by_role("button", name=re.compile("검토할 수정안 1개"))
    previous = await buttons.count()
    await send(page, message)
    await expect(buttons).to_have_count(previous + 1, timeout=15000)
    await open_latest_review(page)


async def assert_last_occurrence(page):
    source = page.locator("[data-review-source]")
    await expect(source).to_have_count(1)
    await expect(source).to_contain_text("같은 문장 입니다.")
    assert await source.evaluate("""element => {
      const repeated = [...document.querySelectorAll('[role="document"] p')]
        .filter(item => item.textContent === '같은 문장 입니다.');
      return element === repeated.at(-1);
    }""")
    await expect(source).to_be_in_viewport(ratio=1)


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1500, "height": 1000})
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(BASE)
        project = await create_project(page, f"수정 위치 검증 {uuid.uuid4().hex[:7]}")
        await page.get_by_test_id("file-import").set_input_files({
            "name": "review-focus.md", "mimeType": "text/markdown", "buffer": SAMPLE.encode("utf-8"),
        })
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장 입니다.")
        await request_review(page, "문장을 다듬어 주세요.")
        await expect(page.locator("[data-review-card]")).to_have_count(3)
        locate = page.get_by_role("button", name="변경 3 본문에서 보기", exact=True)
        await locate.click()
        await assert_last_occurrence(page)
        await expect(locate).to_have_attribute("aria-pressed", "true")
        await expect(page.get_by_label("선택 영역 작업")).to_have_count(0)
        assert (await read_file(page, project, "review-focus.md"))["content"] == SAMPLE
        await page.screenshot(path=str(ARTIFACTS / "desktop-read-focus.png"))
        results.append("navigate to the correct repeated paragraph without changing the document or AI selection")

        await page.locator("[class*='documentScroll']").evaluate("element => element.scrollTop = 0")
        await expect(page.locator("[data-review-source]")).not_to_be_in_viewport()
        await locate.click()
        await assert_last_occurrence(page)
        results.append("the same location button can reveal its paragraph again")

        await page.get_by_role("button", name="변경 1 승인", exact=True).click()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장입니다.")
        await locate.click()
        await assert_last_occurrence(page)
        approved = SAMPLE.replace("첫 문장 입니다.", "첫 문장입니다.")
        assert (await read_file(page, project, "review-focus.md"))["content"] == approved
        results.append("locations remain aligned after an earlier accepted deletion with BOM, CRLF, and emoji")

        await page.get_by_role("button", name="Markdown 편집", exact=True).click()
        mark = page.locator(".cm-review-mark")
        await expect(mark).to_have_count(1)
        # The backend groups the final deletion with the unchanged sentence suffix.
        await expect(mark).to_have_text(" 입니다.", use_inner_text=False)
        await expect(mark).to_be_in_viewport()
        await expect(page.locator(".cm-review-line")).to_contain_text("같은 문장 입니다.")
        await expect(page.get_by_label("선택 영역 작업")).to_have_count(0)
        assert (await read_file(page, project, "review-focus.md"))["content"] == approved
        await page.screenshot(path=str(ARTIFACTS / "desktop-editor-focus.png"))
        results.append("Markdown mode highlights the exact changed text and keeps the editing selection independent")

        await page.locator("[class*='documentScroll']").evaluate("element => element.scrollTop = 0")
        await page.get_by_role("button", name="읽기", exact=True).click()
        await assert_last_occurrence(page)
        await page.get_by_role("button", name="Markdown 편집", exact=True).click()
        await expect(mark).to_be_in_viewport()
        results.append("switching reading modes reveals the active change even after scrolling away")

        await page.locator(".cm-content").click()
        await page.keyboard.press("Control+End")
        await page.keyboard.insert_text("\n직접 추가한 문장.")
        await expect(mark).to_have_count(0)
        await expect(page.locator("[data-review-source]")).to_have_count(0)
        await expect(locate).to_be_disabled()
        await page.keyboard.press("Control+z")
        await expect(locate).to_be_enabled()
        await page.get_by_role("button", name="읽기", exact=True).click()
        results.append("a manual edit clears outdated highlights and disables stale navigation")

        await page.set_viewport_size({"width": 375, "height": 812})
        await page.reload()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장입니다.")
        await page.get_by_role("button", name="대화 도구 열기", exact=True).click()
        await page.get_by_role("tab", name=re.compile("^검토")).click()
        inspector = page.get_by_label("대화와 문서 도구", exact=True)
        await inspector.get_by_role("button", name=re.compile("review-focus.md")).click()
        await page.get_by_role("button", name="변경 3 본문에서 보기", exact=True).click()
        await expect(inspector).not_to_be_visible()
        await assert_last_occurrence(page)
        toolbar = page.get_by_label("본문 수정 위치", exact=True)
        await expect(toolbar).to_be_focused()
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        await page.screenshot(path=str(ARTIFACTS / "mobile-source-focus.png"))
        await toolbar.get_by_role("button", name="수정안 보기", exact=True).click()
        await expect(inspector).to_be_visible()
        await expect(page.get_by_role("button", name="변경 3 본문에서 보기", exact=True)).to_have_attribute("aria-pressed", "true")
        results.append("mobile navigation reveals the source, moves keyboard focus out of the closed panel, and returns to review")

        await page.set_viewport_size({"width": 1500, "height": 1000})
        await page.get_by_role("button", name="모두 승인", exact=True).click()
        await expect(page.get_by_text(re.compile("검토 완료 · 3개 반영"))).to_be_visible()
        await request_review(page, "새 문장을 추가해 주세요.")
        await page.get_by_role("button", name="변경 1 본문에서 보기", exact=True).click()
        await expect(page.locator("[data-review-source]")).to_be_in_viewport()
        await expect(page.locator("[data-review-source]")).to_have_attribute("data-review-label", re.compile("위치"))
        await page.get_by_role("button", name="본문 강조 해제", exact=True).click()
        await expect(page.locator("[data-review-source]")).to_have_count(0)
        await expect(page.get_by_label("본문 수정 위치", exact=True)).to_have_count(0)
        results.append("an insertion at the end of the document has a visible anchor and can be cleared")

        hidden = (
            '# Reference note\n\nSee [the guide][ref].\n\n'
            'This paragraph is unrelated.\n\n'
            '[ref]: https://example.org/guide "문장 입니다"\n'
        )
        await page.get_by_test_id("file-import").set_input_files({
            "name": "reference.md", "mimeType": "text/markdown", "buffer": hidden.encode("utf-8"),
        })
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("This paragraph is unrelated.")
        await request_review(page, "문장을 다듬어 주세요.")
        await page.get_by_role("button", name="변경 1 본문에서 보기", exact=True).click()
        await expect(page.get_by_role("button", name="Markdown 편집", exact=True)).to_have_attribute("aria-pressed", "true")
        await expect(page.locator(".cm-review-line")).to_contain_text('[ref]: https://example.org/guide "문장 입니다"')
        await expect(page.locator(".cm-review-mark")).to_be_in_viewport()
        assert (await read_file(page, project, "reference.md"))["content"] == hidden
        results.append("hidden Markdown definitions open their exact source instead of highlighting an unrelated paragraph")
        await page.get_by_role("button", name="변경 1 본문에서 보기", exact=True).click()
        await page.get_by_role("button", name="읽기", exact=True).click()
        await expect(page.get_by_role("button", name="읽기", exact=True)).to_have_attribute("aria-pressed", "true")
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("This paragraph is unrelated.")
        await expect(page.locator("[data-review-source]")).to_have_count(0)
        await page.get_by_role("button", name="Markdown 편집", exact=True).click()
        await page.get_by_role("button", name="변경 1 본문에서 보기", exact=True).click()
        await page.get_by_role("button", name="읽기", exact=True).click()
        await expect(page.get_by_role("document", name="문서 읽기")).to_be_visible()
        await expect(page.locator("[data-review-source]")).to_have_count(0)
        results.append("the author can return to reading after locating hidden source")

        assert not errors, errors
        report = {"passed": results, "page_errors": errors, "inference": "deterministic local fixture"}
        (ARTIFACTS / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
