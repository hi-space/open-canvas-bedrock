"""Chromium check of research -> HTML -> proposal -> approval -> offline download.

Start research_html_backend.py and Next with API_URL=http://127.0.0.1:9017.
Run OPEN_CANVAS_TEST_URL=http://127.0.0.1:3107 python tests/research_html_smoke.py.
"""
import asyncio
import json
import os
from pathlib import Path
import re
import uuid

from playwright.async_api import async_playwright, expect

from cloud_workspace_smoke import create_project, read_file

BASE = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3107")
BACKEND = os.environ.get("RESEARCH_HTML_TEST_BACKEND", "http://127.0.0.1:9017")
ARTIFACTS = Path(os.environ.get("OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-research-html-browser"))
MATERIAL = "# 프로젝트 자료\n\n대상 고객은 세 팀입니다. 자료와 그림을 함께 검토합니다.\n"
TITLE = "프로젝트 자료로 완성한 리서치 보고서"


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    checks = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1560, "height": 1060}, accept_downloads=True)
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(BASE)
        workspace = await create_project(page, f"HTML 리서치 검증 {uuid.uuid4().hex[:6]}")
        await page.get_by_test_id("file-import").set_input_files([
            {"name": "brief.md", "mimeType": "text/markdown", "buffer": MATERIAL.encode()},
            {"name": "unused.md", "mimeType": "text/markdown", "buffer": b"UNSELECTED_PRIVATE_MATERIAL"},
        ])
        source = await page.request.post(f"{BASE}/api/workspaces/{workspace}/sources", data={
            "id": "project-guide", "title": "프로젝트 가이드", "url": "https://example.org/project-guide",
            "excerpt": "검증용 예시에서 기존 방식의 정확도는 87%입니다. " * 12,
        })
        assert source.ok, await source.text()
        await page.get_by_role("navigation", name="파일 목록").get_by_role("button", name="brief.md", exact=False).click()
        await page.reload()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("세 팀")
        await page.get_by_role("tab", name="대화", exact=True).click()
        await page.get_by_label("작성 방식", exact=True).select_option("blog")
        await page.get_by_label("결과 형식", exact=True).select_option("html")
        await expect(page.get_by_label("brief.md", exact=True)).to_be_checked()
        await expect(page.get_by_label("unused.md", exact=True)).not_to_be_checked()
        await page.screenshot(path=str(ARTIFACTS / "composer-desktop.png"))
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill("자료와 웹 근거를 비교하고 다이어그램이 있는 HTML을 만들어 주세요.")
        await page.get_by_role("button", name="메시지 보내기", exact=True).click()
        proposal_button = page.get_by_role("button", name=re.compile("검토할 수정안 1개"))
        await expect(proposal_button).to_be_visible(timeout=30000)
        detail = await (await page.request.get(f"{BASE}/api/workspaces/{workspace}")).json()
        proposal = await (await page.request.get(
            f"{BASE}/api/workspaces/{workspace}/proposals/{detail['proposals'][0]['id']}"
        )).json()
        assert proposal["path"].endswith(".html")
        assert len(detail["files"]) == 2
        assert (await read_file(page, workspace, "brief.md"))["content"] == MATERIAL
        captured = await (await page.request.get(f"{BACKEND}/__test/research-inputs")).json()
        assert captured[-1]["format"] == "html"
        assert [item["path"] for item in captured[-1]["context"]] == ["brief.md"]
        assert captured[-1]["context"][0]["content"] == MATERIAL
        checks.append("independent HTML/research choices and selected project snapshots")

        await proposal_button.click()
        preview = page.frame_locator('iframe[title="새 HTML 제안 미리보기"]')
        await expect(preview.get_by_role("heading", name=TITLE, exact=True)).to_be_visible()
        await expect(preview.locator("table")).to_contain_text("91%")
        await preview.locator("img").wait_for()
        await page.wait_for_function("""() => {
          const frame = document.querySelector('iframe[title="새 HTML 제안 미리보기"]');
          return frame && frame.srcdoc.includes('data:image/png;base64,');
        }""")
        await preview.locator("img").evaluate("(image) => image.decode()")
        assert await preview.locator("img").evaluate("(image) => image.complete && image.naturalWidth === 960")
        await page.screenshot(path=str(ARTIFACTS / "proposal-desktop.png"))
        checks.append("real PNG rendered in a sandboxed proposal before canonical writes")

        await page.get_by_role("button", name="변경 승인", exact=True).click()
        approved_frame = page.frame_locator(f'iframe[title="{proposal["path"].split("/")[-1]} 미리보기"]')
        await expect(approved_frame.get_by_role("heading", name=TITLE, exact=True)).to_be_visible()
        approved = await read_file(page, workspace, proposal["path"])
        assert approved["content"] == proposal["proposedContent"]
        assert "/api/research/assets/" in approved["content"]
        assert "data:image/png" not in approved["content"]
        checks.append("explicit approval persists canonical image references and source identities")

        async with page.expect_download() as pending:
            await page.get_by_role("button", name="HTML 다운로드", exact=True).click()
        download = await pending.value
        destination = ARTIFACTS / download.suggested_filename
        await download.save_as(destination)
        exported = destination.read_text()
        assert "data:image/png;base64," in exported
        assert "/api/research/assets/" not in exported
        assert 'href="https://example.org/project-guide"' in exported
        assert 'href="https://example.org/evaluation"' in exported
        offline_context = await browser.new_context(offline=True, viewport={"width": 1280, "height": 1000})
        offline = await offline_context.new_page()
        await offline.goto(destination.as_uri())
        await expect(offline.get_by_role("heading", name=TITLE, exact=True)).to_be_visible()
        await expect(offline.get_by_role("link", name="[1]", exact=True).first).to_be_visible()
        await offline.locator("img").evaluate("(image) => image.decode()")
        assert await offline.locator("img").evaluate("(image) => image.complete && image.naturalWidth === 960")
        await offline.screenshot(path=str(ARTIFACTS / "standalone-desktop.png"), full_page=True)
        await offline.set_viewport_size({"width": 390, "height": 844})
        assert await offline.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        await offline.screenshot(path=str(ARTIFACTS / "standalone-mobile.png"), full_page=True)
        checks.append("standalone HTML works offline with figures, citations, tables and mobile layout")
        assert not errors, errors
        await offline_context.close()
        await context.close()
        await browser.close()
    (ARTIFACTS / "results.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": checks, "artifacts": str(ARTIFACTS)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
