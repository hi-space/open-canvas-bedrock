"""Whole-document comparison against the local deterministic workspace backend.

Start cloud_workspace_backend.py and Next as in cloud_workspace_smoke.py.
Run OPEN_CANVAS_TEST_URL=http://127.0.0.1:3102 python tests/comparison_smoke.py.
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
ARTIFACTS = Path(os.environ.get(
    "OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-comparison-browser"
))
SAMPLE = (
    "\ufeff# 함께 다듬는 기획서 😀\r\n\r\n"
    "첫 문장 입니다.\r\n\r\n"
    "## 다음 단계\r\n\r\n"
    "두 번째 문장 입니다.\r\n\r\n"
    "변하지 않는 문단과 [참고 자료](https://example.org/source).\r\n"
)
HTML = """<!doctype html><html lang="ko"><head><meta charset="UTF-8">
<style>body{margin:0;padding:32px;background:#f5f1e8;color:#253f36;font-family:sans-serif}
h1{font-size:30px}section{padding:24px;background:white;border-radius:12px}
</style></head><body><h1 data-oc-id="title">새로운 글쓰기</h1>
<section data-oc-id="card"><h2 data-oc-id="heading">기획 초안</h2>
<p data-oc-id="copy">함께 다듬는 문장 입니다.</p></section>
</body></html>"""


async def request_comparison(page):
    await page.get_by_role("tab", name="대화", exact=True).click()
    proposals = page.get_by_role("button", name=re.compile("검토할 수정안 1개"))
    previous = await proposals.count()
    await send(page, "문장을 다듬어 주세요.")
    await expect(proposals).to_have_count(previous + 1, timeout=15000)
    await proposals.last.click()
    await page.get_by_role("button", name="나란히 비교", exact=True).click()
    dialog = page.get_by_role("dialog", name=re.compile("버전 비교"))
    await expect(dialog).to_be_visible()
    return dialog


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(BASE)
        project = await create_project(page, f"버전 비교 {uuid.uuid4().hex[:7]}")
        await page.get_by_test_id("file-import").set_input_files({
            "name": "comparison.md",
            "mimeType": "text/markdown",
            "buffer": SAMPLE.encode("utf-8"),
        })
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text(
            "첫 문장 입니다."
        )
        dialog = await request_comparison(page)
        before = dialog.get_by_role("document", name="수정 전 문서")
        after = dialog.get_by_role("document", name="수정 후 문서")
        await expect(before).to_contain_text("첫 문장 입니다.")
        await expect(after).to_contain_text("첫 문장입니다.")
        left = await before.bounding_box()
        right = await after.bounding_box()
        assert left["x"] < right["x"] and abs(left["y"] - right["y"]) < 2
        await expect(before.locator("[data-comparison-change]")).to_have_count(2)
        await expect(after.locator("[data-comparison-change]")).to_have_count(0)
        # Deleting a space highlights the old text; unchanged characters in the
        # revised document are intentionally not labeled as inserted text.
        assert (await read_file(page, project, "comparison.md"))["content"] == SAMPLE
        await page.screenshot(path=str(ARTIFACTS / "markdown-comparison.png"))
        results.append("formatted side-by-side Markdown and no writes when opening")

        await dialog.get_by_role("button", name="원문 비교", exact=True).click()
        assert await dialog.get_by_label("수정 전 원문", exact=True).text_content() == SAMPLE
        assert await dialog.get_by_label("수정 후 원문", exact=True).text_content() == SAMPLE.replace(
            "문장 입니다", "문장입니다"
        )
        await dialog.get_by_role("button", name="문서 보기", exact=True).click()
        await dialog.get_by_role("button", name="변경 1 승인", exact=True).click()
        await expect(dialog.get_by_text("✓ 파일에 저장됨", exact=True)).to_be_visible()
        await expect(before).to_contain_text("첫 문장 입니다.")
        await expect(after).to_contain_text("두 번째 문장입니다.")
        approved = SAMPLE.replace("첫 문장 입니다.", "첫 문장입니다.")
        assert (await read_file(page, project, "comparison.md"))["content"] == approved
        await dialog.get_by_role("button", name="변경 2 거절", exact=True).click()
        await expect(dialog.get_by_text("검토 완료 · 1개 반영", exact=True)).to_be_visible()
        await expect(after).to_contain_text("두 번째 문장입니다.")
        assert (await read_file(page, project, "comparison.md"))["content"] == approved
        await page.keyboard.press("Escape")
        await expect(dialog).not_to_be_visible()
        await expect(page.get_by_role("button", name="나란히 비교", exact=True)).to_be_focused()
        results.append("exact source, granular approval/rejection, immutable snapshots, keyboard close")

        await page.get_by_role("tab", name="이력", exact=True).click()
        await page.get_by_role("button", name="나란히 비교", exact=True).first.click()
        dialog = page.get_by_role("dialog", name=re.compile("버전 비교"))
        await expect(dialog.get_by_role("document", name="이전 버전 문서")).to_contain_text(
            "첫 문장 입니다."
        )
        await expect(dialog.get_by_role("document", name="현재 문서", exact=True)).to_contain_text(
            "첫 문장입니다."
        )
        assert (await read_file(page, project, "comparison.md"))["content"] == approved
        await page.screenshot(path=str(ARTIFACTS / "history-comparison.png"))
        results.append("saved history compared to current document without restore")

        await page.set_viewport_size({"width": 375, "height": 812})
        previous_pane = dialog.get_by_role("region", name="이전 버전 비교 영역")
        current_pane = dialog.get_by_role("region", name="현재 문서 비교 영역")
        await page.screenshot(path=str(ARTIFACTS / "mobile-comparison.png"))
        await expect(previous_pane).to_be_in_viewport(ratio=0.9)
        await expect(current_pane).to_be_in_viewport(ratio=0.9)
        assert await page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        await expect(dialog.get_by_role("button", name="비교 닫기")).to_be_in_viewport()
        scroll = dialog.get_by_role("region", name="이전 버전 스크롤")
        await scroll.focus()
        await page.keyboard.press("PageDown")
        await page.wait_for_function(
            "element => element.scrollTop > 0", arg=await scroll.element_handle()
        )
        await dialog.get_by_role("button", name="비교 닫기").click()
        results.append("both mobile panes visible, keyboard scrolling, no horizontal page overflow")

        await page.set_viewport_size({"width": 1500, "height": 1000})
        await page.get_by_test_id("file-import").set_input_files({
            "name": "comparison.html",
            "mimeType": "text/html",
            "buffer": HTML.encode("utf-8"),
        })
        await expect(page.get_by_title("comparison.html 미리보기")).to_be_visible()
        dialog = await request_comparison(page)
        await expect(dialog.locator("iframe")).to_have_count(2)
        await expect(dialog.frame_locator('iframe[title="수정 전 HTML"]').locator("body")).to_contain_text(
            "함께 다듬는 문장 입니다."
        )
        await expect(dialog.frame_locator('iframe[title="수정 후 HTML"]').locator("body")).to_contain_text(
            "함께 다듬는 문장입니다."
        )
        for frame in await dialog.locator("iframe").all():
            await expect(frame).to_have_attribute("sandbox", "")
            assert "<script" not in (await frame.get_attribute("srcdoc")).lower()
            dimensions = await frame.evaluate("""frame => ({
              frame: frame.getBoundingClientRect().height,
              pane: frame.closest('section[aria-label$="스크롤"]').getBoundingClientRect().height
            })""")
            assert dimensions["frame"] >= dimensions["pane"] - 4, dimensions
        assert (await read_file(page, project, "comparison.html"))["content"] == HTML
        await page.screenshot(path=str(ARTIFACTS / "html-comparison.png"))
        await dialog.get_by_role("button", name="변경 승인", exact=True).click()
        await expect(dialog.get_by_text("검토 완료 · 1개 반영", exact=True)).to_be_visible()
        assert (await read_file(page, project, "comparison.html"))["content"] == HTML.replace(
            "문장 입니다", "문장입니다"
        )
        results.append("two isolated HTML previews and existing whole-page approval")
        assert not errors, errors
        await browser.close()
    print(json.dumps({"passed": results, "artifacts": str(ARTIFACTS)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
