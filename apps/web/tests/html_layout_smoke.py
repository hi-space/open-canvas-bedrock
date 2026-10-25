"""HTML canvas geometry and editing against cloud_workspace_backend.py.

Run OPEN_CANVAS_TEST_URL=http://127.0.0.1:3311 python tests/html_layout_smoke.py.
"""
import asyncio
import json
import os
from pathlib import Path
import uuid

from playwright.async_api import async_playwright, expect
from cloud_workspace_smoke import create_project

BASE = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3311")
ARTIFACTS = Path(os.environ.get(
    "OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-html-layout-browser"
))
HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<style>body{margin:0;padding:28px;background:#f7f8f3;font:16px/1.7 sans-serif;color:#284733}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
article{padding:24px;background:white;border:1px solid #d8e3d3;border-radius:12px}
footer{margin-top:30px;height:1200px}@media(max-width:600px){.cards{grid-template-columns:1fr}}
</style></head><body><h1>자료로 만드는 페이지</h1>
<section class="cards" data-oc-id="cards">
<article data-oc-id="first"><h2>첫 번째 카드</h2><p data-oc-id="copy">함께 다듬는 문장 입니다.</p></article>
<article data-oc-id="second"><h2>두 번째 카드</h2><p>자료와 근거를 연결합니다.</p></article>
<article data-oc-id="third"><h2>세 번째 카드</h2><p>선택한 부분을 수정합니다.</p></article>
</section><footer>긴 페이지도 미리보기 안에서 스크롤합니다.</footer></body></html>"""


async def frame_bounds(page):
    return await page.locator('iframe[title="layout.html 미리보기"]').evaluate(
        """frame => {
          const rect = frame.getBoundingClientRect();
          return {left:rect.left, top:rect.top, width:rect.width,
                  height:rect.height, bottom:rect.bottom,
                  viewportWidth:innerWidth, viewportHeight:innerHeight};
        }"""
    )


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(type(error).__name__))
        try:
            await page.goto(BASE)
            await create_project(page, "HTML 화면 검증 " + uuid.uuid4().hex[:6])
            await page.get_by_test_id("file-import").set_input_files({
                "name": "layout.html", "mimeType": "text/html", "buffer": HTML.encode(),
            })
            frame = page.frame_locator('iframe[title="layout.html 미리보기"]')
            await expect(frame.get_by_role("heading", name="자료로 만드는 페이지")).to_be_visible()
            results["desktop"] = await frame_bounds(page)
            print(json.dumps(results, ensure_ascii=False), flush=True)
            await page.screenshot(path=str(ARTIFACTS / "desktop.png"))
            assert results["desktop"]["width"] >= 1000, results["desktop"]
            assert results["desktop"]["top"] <= 250, results["desktop"]
            assert results["desktop"]["height"] >= 700, results["desktop"]
            assert results["desktop"]["bottom"] <= 992, results["desktop"]
            await expect(page.get_by_role("complementary", name="프로젝트와 파일")).not_to_be_visible()
            await expect(page.get_by_role("complementary", name="대화와 문서 도구")).to_be_visible()

            # File navigation overlays the canvas and closes with Escape.
            opener = page.get_by_role("button", name="파일 목록 열기", exact=True)
            await opener.focus()
            await opener.press("Enter")
            await expect(page.get_by_role("complementary", name="프로젝트와 파일")).to_be_visible()
            assert abs((await frame_bounds(page))["width"] - results["desktop"]["width"]) < 1
            await expect(page.get_by_label("파일 찾기", exact=True)).to_be_focused()
            await page.keyboard.press("Tab")
            assert await page.evaluate(
                "document.getElementById('cloud-workspace-files').contains(document.activeElement)"
            )
            await page.keyboard.press("Escape")
            await expect(page.get_by_role("complementary", name="프로젝트와 파일")).not_to_be_visible()
            await expect(opener).to_be_focused()
            await expect(page.get_by_role("complementary", name="대화와 문서 도구")).to_be_visible()

            await frame.get_by_text("함께 다듬는 문장 입니다.", exact=True).click()
            await expect(page.get_by_label("영역 선택", exact=True)).to_have_value("copy")
            await frame.locator("body").evaluate("() => { window.__layoutSentinel = 'same-frame'; }")
            await page.get_by_role("button", name="넓게 보기", exact=True).click()
            await expect(page.get_by_role("complementary", name="대화와 문서 도구")).not_to_be_visible()
            results["expanded"] = await frame_bounds(page)
            assert results["expanded"]["width"] >= 1400, results["expanded"]
            assert await frame.locator("body").evaluate("() => window.__layoutSentinel") == "same-frame"
            await expect(page.get_by_label("영역 선택", exact=True)).to_have_value("copy")
            await page.screenshot(path=str(ARTIFACTS / "expanded.png"))

            await page.get_by_role("button", name="대화 보기", exact=True).click()
            await expect(page.get_by_role("complementary", name="대화와 문서 도구")).to_be_visible()
            assert abs((await frame_bounds(page))["width"] - results["desktop"]["width"]) < 1
            assert await frame.locator("body").evaluate("() => window.__layoutSentinel") == "same-frame"
            await page.get_by_role("button", name="선택 해제", exact=True).first.click()

            # The document scrolls inside the frame; surrounding controls stay put.
            top = (await frame_bounds(page))["top"]
            await frame.locator("body").evaluate("() => window.scrollTo(0, 700)")
            assert await frame.locator("body").evaluate("() => window.scrollY") > 100
            assert abs((await frame_bounds(page))["top"] - top) < 1
            await expect(page.get_by_label("영역 선택", exact=True)).to_be_visible()
            await frame.locator("body").evaluate("() => window.scrollTo(0, 0)")

            await page.set_viewport_size({"width": 375, "height": 812})
            await page.keyboard.press("Escape")
            results["mobile"] = await frame_bounds(page)
            assert results["mobile"]["width"] >= 345, results["mobile"]
            assert results["mobile"]["height"] >= 500, results["mobile"]
            assert results["mobile"]["bottom"] <= 812, results["mobile"]
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            await page.screenshot(path=str(ARTIFACTS / "mobile.png"))

            await page.set_viewport_size({"width": 320, "height": 568})
            await frame.get_by_text("함께 다듬는 문장 입니다.", exact=True).click()
            toolbar = page.get_by_label("선택 영역 작업", exact=True)
            await expect(toolbar).to_be_visible()
            toolbar_bounds = await toolbar.bounding_box()
            results["smallSelected"] = await frame_bounds(page)
            assert results["smallSelected"]["bottom"] <= toolbar_bounds["y"] - 4, {
                "frame": results["smallSelected"], "toolbar": toolbar_bounds,
            }
            await page.get_by_role("button", name="선택 해제", exact=True).first.click()
            await page.set_viewport_size({"width": 812, "height": 375})
            await page.keyboard.press("Escape")
            results["landscape"] = await frame_bounds(page)
            assert results["landscape"]["height"] >= 140, results["landscape"]
            assert results["landscape"]["bottom"] <= 375, results["landscape"]

            # Markdown continues to use its writing layout and persistent file list.
            await page.set_viewport_size({"width": 1440, "height": 1000})
            await page.get_by_test_id("file-import").set_input_files({
                "name": "notes.md", "mimeType": "text/markdown",
                "buffer": "# 문서 화면\n\n기존 문서 레이아웃입니다.".encode(),
            })
            await expect(page.get_by_role("heading", name="문서 화면", exact=True)).to_be_visible()
            await expect(page.get_by_role("complementary", name="프로젝트와 파일")).to_be_visible()
            await expect(page.get_by_role("button", name="넓게 보기", exact=True)).not_to_be_visible()
            assert not errors, errors
            (ARTIFACTS / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(json.dumps({"ok": True, "geometry": results, "pageErrors": errors}, ensure_ascii=False))
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
