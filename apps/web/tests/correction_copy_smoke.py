"""Full correction copies, reloads and immutable comparisons in real Chromium.

Start cloud_workspace_backend.py and Next as in cloud_workspace_smoke.py.
Run OPEN_CANVAS_TEST_URL=http://127.0.0.1:3102 python tests/correction_copy_smoke.py.
"""
import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from playwright.async_api import async_playwright, expect
from cloud_workspace_smoke import create_project, read_file, write_file
from comparison_smoke import HTML, SAMPLE, request_comparison


BASE = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3102")
ARTIFACTS = Path(os.environ.get("OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-correction-copy-browser"))


async def saved_copy(page, project, source_path):
    response = await page.request.get(f"{BASE}/api/workspaces/{project}")
    assert response.ok, await response.text()
    detail = await response.json()
    proposal = next(item for item in detail["proposals"] if item["path"] == source_path)
    path = proposal["savedCopy"]["path"]
    assert path != source_path
    return proposal["id"], await read_file(page, project, path)


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1500, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            await page.goto(BASE)
            project = await create_project(page, f"전체 교정본 {uuid.uuid4().hex[:7]}")
            source_path = "review-copy.md"
            await page.get_by_test_id("file-import").set_input_files({
                "name": source_path, "mimeType": "text/markdown", "buffer": SAMPLE.encode("utf-8"),
            })
            await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장 입니다.")
            dialog = await request_comparison(page)
            await dialog.get_by_role("button", name="변경 1 승인", exact=True).click()
            await expect(dialog.get_by_text("✓ 파일에 저장됨", exact=True)).to_be_visible()
            await dialog.get_by_role("button", name="변경 2 거절", exact=True).click()
            await expect(dialog.get_by_text("검토 완료 · 1개 반영", exact=True)).to_be_visible()
            approved = SAMPLE.replace("첫 문장 입니다.", "첫 문장입니다.")
            corrected = SAMPLE.replace("문장 입니다", "문장입니다")
            await dialog.get_by_role("button", name="전체 교정본 저장", exact=True).click()
            await expect(dialog.get_by_role("button", name="교정본 열기", exact=True)).to_be_visible()
            proposal_id, copy = await saved_copy(page, project, source_path)
            assert copy["content"] == corrected
            assert (await read_file(page, project, source_path))["content"] == approved
            await page.screenshot(path=str(ARTIFACTS / "saved-copy-review.png"))
            # Retrying the same server operation must not create another file.
            repeated = await page.request.post(f"{BASE}/api/workspaces/{project}/proposals/{proposal_id}/copy")
            assert repeated.ok, await repeated.text()
            assert (await repeated.json())["file"]["path"] == copy["path"]
            results.append("partial approval/rejection, full copy, original preserved, idempotent retry")

            await dialog.get_by_role("button", name="교정본 열기", exact=True).click()
            await expect(dialog).not_to_be_visible()
            await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("두 번째 문장입니다.")
            await expect(page.get_by_role("button", name="교정 전후 비교", exact=True)).to_be_visible()
            await page.wait_for_function(
                "({key, path}) => localStorage.getItem(key) === path",
                arg={"key": f"open-canvas-cloud-path:{project}", "path": copy["path"]},
            )
            await page.reload()
            await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("두 번째 문장입니다.")
            await page.get_by_role("tab", name="이력", exact=True).click()
            await page.get_by_role("button", name="교정 전후 비교", exact=True).click()
            dialog = page.get_by_role("dialog", name=re.compile("버전 비교"))
            await dialog.get_by_role("button", name="원문 비교", exact=True).click()
            assert await dialog.get_by_label("교정 당시 원문 원문", exact=True).text_content() == SAMPLE
            assert await dialog.get_by_label("저장한 교정본 원문", exact=True).text_content() == corrected
            await dialog.get_by_role("button", name="문서 보기", exact=True).click()
            await page.screenshot(path=str(ARTIFACTS / "saved-correction-comparison.png"))
            results.append("open copy, reload, exact BOM/CRLF/emoji/citation snapshots from history")

            await page.set_viewport_size({"width": 375, "height": 812})
            await expect(dialog.get_by_role("region", name="교정 당시 원문 비교 영역")).to_be_in_viewport(ratio=0.8)
            await expect(dialog.get_by_role("region", name="저장한 교정본 비교 영역")).to_be_in_viewport(ratio=0.8)
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            await page.screenshot(path=str(ARTIFACTS / "mobile-correction-comparison.png"))
            await page.keyboard.press("Escape")
            await page.set_viewport_size({"width": 1500, "height": 1000})
            results.append("mobile comparison panes and keyboard close")

            original = await read_file(page, project, source_path)
            await write_file(page, project, source_path, "# 나중에 수정한 원본\n", original["version"])
            await write_file(page, project, copy["path"], "# 나중에 바꾼 교정본\n\n후속 수동 편집입니다.\n", copy["version"])
            await page.reload()
            await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("후속 수동 편집입니다.")
            await page.get_by_role("tab", name="이력", exact=True).click()
            await page.get_by_role("button", name="교정 전후 비교", exact=True).click()
            dialog = page.get_by_role("dialog", name=re.compile("버전 비교"))
            await expect(dialog.get_by_role("document", name="교정 당시 원문 문서")).to_contain_text("첫 문장 입니다.")
            await expect(dialog.get_by_role("document", name="저장한 교정본 문서")).to_contain_text("두 번째 문장입니다.")
            await expect(dialog).not_to_contain_text("후속 수동 편집입니다.")
            await dialog.get_by_role("button", name="비교 닫기", exact=True).click()
            results.append("later original and copy edits leave the archived comparison unchanged")

            html_path = "review-copy.html"
            await page.get_by_test_id("file-import").set_input_files({
                "name": html_path, "mimeType": "text/html", "buffer": HTML.encode("utf-8"),
            })
            await expect(page.get_by_title(f"{html_path} 미리보기")).to_be_visible()
            dialog = await request_comparison(page)
            await dialog.get_by_role("button", name="전체 교정본 저장", exact=True).click()
            await expect(dialog.get_by_role("button", name="교정본 열기", exact=True)).to_be_visible()
            _, html_copy = await saved_copy(page, project, html_path)
            assert html_copy["content"] == HTML.replace("문장 입니다", "문장입니다")
            assert (await read_file(page, project, html_path))["content"] == HTML
            await dialog.get_by_role("button", name="교정본 열기", exact=True).click()
            await page.get_by_role("button", name="교정 전후 비교", exact=True).click()
            dialog = page.get_by_role("dialog", name=re.compile("버전 비교"))
            await expect(dialog.locator("iframe")).to_have_count(2)
            await expect(dialog.frame_locator('iframe[title="교정 당시 원문 HTML"]').locator("body")).to_contain_text("문장 입니다.")
            await expect(dialog.frame_locator('iframe[title="저장한 교정본 HTML"]').locator("body")).to_contain_text("문장입니다.")
            for frame in await dialog.locator("iframe").all():
                await expect(frame).to_have_attribute("sandbox", "")
                assert "<script" not in (await frame.get_attribute("srcdoc")).lower()
            await page.screenshot(path=str(ARTIFACTS / "html-correction-comparison.png"))
            results.append("HTML full copy, unchanged original, two isolated archived previews")
            assert not errors, errors
        except Exception:
            await page.screenshot(path=str(ARTIFACTS / "failure.png"), full_page=True)
            raise
        finally:
            await browser.close()
    print(json.dumps({"passed": results, "artifacts": str(ARTIFACTS)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
