"""Verify skill-free native HTML/SVG diagrams through the real graph and browser.

Start research_html_backend.py with NATIVE_HTML_DIAGRAMS_ONLY=1 (port 9017).
Use a production web server with that API_URL, then run this script.
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
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = Path(os.environ.get("OPEN_CANVAS_TEST_ARTIFACTS", str(PROJECT_ROOT / "docs/verification/research-html")))
TITLE = "프로젝트 자료로 완성한 리서치 보고서"


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1540, "height": 1040}, accept_downloads=True)
        page = await context.new_page()
        image_requests = []
        page.on("request", lambda request: image_requests.append(request.url)
                if "/api/research/assets/" in request.url else None)
        await page.goto(BASE)
        workspace = await create_project(page, f"네이티브 도식 {uuid.uuid4().hex[:6]}")
        await page.get_by_test_id("file-import").set_input_files({
            "name": "brief.md", "mimeType": "text/markdown",
            "buffer": "# 구조\n\nAPI가 문서 버전을 고정하고 리서치 그래프에 전달합니다. 대상은 세 팀입니다.".encode(),
        })
        response = await page.request.post(f"{BASE}/api/workspaces/{workspace}/sources", data={
            "id": "project-guide", "title": "프로젝트 가이드", "url": "https://example.org/project-guide",
            "excerpt": "API passes a versioned document snapshot to research and renders an HTML report. " * 5,
        })
        assert response.ok
        await page.reload()
        await page.get_by_label("작성 방식", exact=True).select_option("blog")
        await page.get_by_label("결과 형식", exact=True).select_option("html")
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill(
            "프로젝트의 계층과 기술적인 호출 관계를 HTML과 SVG 도식으로 설명해 주세요."
        )
        await page.get_by_role("button", name="메시지 보내기", exact=True).click()
        review = page.get_by_role("button", name=re.compile("검토할 수정안 1개"))
        await expect(review).to_be_visible(timeout=30000)
        await review.click()
        preview = page.frame_locator('iframe[title="새 HTML 제안 미리보기"]')
        await expect(preview.locator('[data-diagram-layout="layers"]')).to_be_visible()
        await expect(preview.locator("svg")).to_be_visible()
        await expect(preview.locator("svg [data-edge-source]")).to_have_count(4)
        assert await preview.locator("svg").evaluate("(svg) => svg.namespaceURI") == "http://www.w3.org/2000/svg"
        await preview.locator("svg").scroll_into_view_if_needed()
        await page.screenshot(path=str(ARTIFACTS / "native-preview.png"))
        detail = await (await page.request.get(f"{BASE}/api/workspaces/{workspace}")).json()
        proposal = await (await page.request.get(
            f"{BASE}/api/workspaces/{workspace}/proposals/{detail['proposals'][0]['id']}"
        )).json()
        assert "<svg" in proposal["proposedContent"]
        assert "oc-diagram:" not in proposal["proposedContent"]
        assert "/api/research/assets/" not in proposal["proposedContent"]
        await page.get_by_role("button", name="변경 승인", exact=True).click()
        frame = page.frame_locator(f'iframe[title="{proposal["path"].split("/")[-1]} 미리보기"]')
        await expect(frame.locator("svg")).to_be_visible()
        diagram_id = await frame.locator("svg").get_attribute("data-oc-id")
        await frame.locator('svg [data-component-id="api"] text').first.click()
        await expect(page.get_by_label("영역 선택", exact=True)).to_have_value(diagram_id)
        saved = await read_file(page, workspace, proposal["path"])
        assert saved["content"] == proposal["proposedContent"]
        async with page.expect_download() as pending:
            await page.get_by_role("button", name="HTML 다운로드", exact=True).click()
        download = await pending.value
        destination = ARTIFACTS / "native-report.html"
        await download.save_as(destination)
        assert destination.read_text() == saved["content"]
        offline_context = await browser.new_context(offline=True, viewport={"width": 1280, "height": 1000})
        offline = await offline_context.new_page()
        await offline.goto(destination.as_uri())
        await expect(offline.locator("svg [data-edge-source]")).to_have_count(4)
        await expect(offline.get_by_role("heading", name=TITLE, exact=True)).to_be_visible()
        await offline.screenshot(path=str(ARTIFACTS / "native-desktop.png"), full_page=True)
        await offline.set_viewport_size({"width": 390, "height": 844})
        assert await offline.evaluate("document.documentElement.scrollWidth <= innerWidth")
        await offline.screenshot(path=str(ARTIFACTS / "native-mobile.png"), full_page=True)
        wide_response = await page.request.get(f"{BACKEND}/__test/wide-native")
        assert wide_response.ok
        wide_file = ARTIFACTS / "wide-sequence.html"
        wide_file.write_text(await wide_response.text())
        await offline.goto(wide_file.as_uri())
        metrics = await offline.locator("svg").evaluate("""svg => {
          const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
          const texts = [...svg.querySelectorAll('g[data-component-id]')].flatMap(group => {
            const box = group.querySelector('rect').getBBox();
            return [...group.querySelectorAll('text')].map(text => {
              const bounds = text.getBBox();
              return {px: parseFloat(getComputedStyle(text).fontSize) * scale,
                fits: bounds.x >= box.x && bounds.x + bounds.width <= box.x + box.width &&
                  bounds.y >= box.y && bounds.y + bounds.height <= box.y + box.height};
            });
          });
          return {scale, texts, scrollable: svg.parentElement.scrollWidth > svg.parentElement.clientWidth};
        }""")
        assert metrics["scale"] >= 1 and metrics["scrollable"], metrics
        assert all(text["fits"] and text["px"] >= 13 for text in metrics["texts"]), metrics
        await offline.locator("svg").evaluate("(svg) => svg.parentElement.focus()")
        await offline.keyboard.press("ArrowRight")
        await offline.wait_for_function("document.querySelector('svg').parentElement.scrollLeft > 0")
        await offline.screenshot(path=str(ARTIFACTS / "wide-sequence-mobile.png"), full_page=True)
        diagnostics = await (await page.request.get(f"{BACKEND}/__test/diagram-calls")).json()
        assert diagnostics == {"skillCalls": [], "nativeOnly": True}
        assert not image_requests, image_requests
        await offline_context.close()
        await context.close()
        await browser.close()
    result = {
        "checks": ["HTML layers and SVG flow without skills", "all technical relationships rendered",
                   "atomic SVG selection", "approval and byte-preserving offline download",
                   "mobile containment", "six-participant readable text and keyboard scrolling",
                   "zero image requests or rasterizer calls"],
        "artifacts": str(ARTIFACTS.relative_to(PROJECT_ROOT)) if ARTIFACTS.is_relative_to(PROJECT_ROOT) else str(ARTIFACTS),
    }
    (ARTIFACTS / "native-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
