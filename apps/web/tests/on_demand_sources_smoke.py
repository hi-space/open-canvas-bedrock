"""Real Chromium workflow with a source library exceeding the former limits."""
import asyncio
import json
import os
from pathlib import Path
import re
import uuid

from playwright.async_api import async_playwright, expect

from cloud_workspace_smoke import create_project


BASE = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3109")
BACKEND = os.environ.get("SOURCE_TEST_BACKEND", "http://127.0.0.1:9019")
ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "docs/verification/on-demand-sources"


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    checks = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1560, "height": 1060}, accept_downloads=True)
        page = await context.new_page()
        errors, body_reads = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: body_reads.append(request.url)
                if request.method == "GET" and "/sources/" in request.url else None)
        await page.goto(BASE)
        workspace = await create_project(page, f"필요할 때 출처 읽기 {uuid.uuid4().hex[:6]}")
        await page.get_by_test_id("file-import").set_input_files({
            "name": "brief.md", "mimeType": "text/markdown",
            "buffer": "# 프로젝트 자료\n\n대상은 세 팀입니다. 기존 문서를 보강합니다.\n".encode(),
        })
        for index in range(65):
            response = await page.request.post(f"{BASE}/api/workspaces/{workspace}/sources", data={
                "id": f"older-{index}", "title": f"이전 자료 {index}",
                "url": f"https://example.org/older/{index}",
                "excerpt": "IRRELEVANT_STORED_BODY " * 110,
            })
            assert response.ok, await response.text()
        response = await page.request.post(f"{BASE}/api/workspaces/{workspace}/sources", data={
            "id": "project-guide", "title": "프로젝트 가이드",
            "url": "https://example.org/project-guide",
            "excerpt": "READ_ONLY_TARGET: API passes a versioned document snapshot to research. 기존 방식 예시 정확도는 87%입니다.",
        })
        assert response.ok
        detail = await (await page.request.get(f"{BASE}/api/workspaces/{workspace}")).json()
        assert len(detail["sources"]) == 66
        assert all("excerpt" not in source for source in detail["sources"])
        assert len(json.dumps(detail)) < 50000
        checks.append("66 sources / over 150,000 stored excerpt characters; metadata-only snapshot")

        await page.reload()
        await page.get_by_role("tab", name="출처", exact=True).click()
        await expect(page.get_by_text("출처 66개를 보관 중입니다.", exact=False)).to_be_visible()
        assert not body_reads
        await page.get_by_label("출처 제목·주소 검색", exact=True).fill("프로젝트 가이드")
        await page.get_by_role("button", name="발췌 보기", exact=True).click()
        await expect(page.get_by_text("READ_ONLY_TARGET:", exact=False)).to_be_visible()
        assert len(body_reads) == 1 and body_reads[0].endswith("/sources/project-guide")
        await page.screenshot(path=str(ARTIFACTS / "source-library.png"))
        checks.append("source panel fetches only the opened excerpt")

        await page.get_by_role("button", name="참고 자료 추가", exact=True).click()
        await page.get_by_label("원문 링크", exact=True).fill("https://example.org/manual")
        await page.get_by_label("제목", exact=True).fill("수동 추가 자료")
        await page.get_by_label("참고할 발췌", exact=False).fill("사용자가 추가한 독립된 자료입니다.")
        await page.get_by_role("button", name="출처 추가", exact=True).click()
        await expect(page.get_by_text("출처 67개를 보관 중입니다.", exact=False)).to_be_visible()
        checks.append("source addition through the UI works past the old 50-source limit")

        await page.get_by_role("tab", name="대화", exact=True).click()
        await page.get_by_label("작성 방식", exact=True).select_option("")
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill("프로젝트 가이드를 읽고 현재 문서에 설명을 추가해 주세요.")
        await page.get_by_role("button", name="메시지 보내기", exact=True).click()
        review = page.get_by_role("button", name=re.compile("검토할 수정안 1개")).last
        await expect(review).to_be_visible(timeout=30000)
        await review.click()
        detail = await (await page.request.get(f"{BASE}/api/workspaces/{workspace}")).json()
        proposal = await (await page.request.get(
            f"{BASE}/api/workspaces/{workspace}/proposals/{detail['proposals'][0]['id']}"
        )).json()
        assert [source["id"] for source in proposal["sources"]] == ["project-guide"]
        await page.get_by_role("button", name="모두 승인", exact=True).click()
        await page.screenshot(path=str(ARTIFACTS / "approved-edit.png"))
        observations = await (await page.request.get(BACKEND + "/__test/source-observations")).json()
        observed = observations[-1]
        assert observed["sourceCount"] == 67 and observed["preloadedBody"] is False
        assert observed["loadedSources"] == ["project-guide"] and observed["initialCharacters"] < 5000
        checks.append("real agent search/read tools add cited text and approval updates the original")

        await page.get_by_role("tab", name="대화", exact=True).click()
        await page.get_by_label("작성 방식", exact=True).select_option("blog")
        await page.get_by_label("결과 형식", exact=True).select_option("html")
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill("자료의 정확도를 비교하고 구조를 HTML과 SVG로 설명해 주세요.")
        await page.get_by_role("button", name="메시지 보내기", exact=True).click()
        await expect(page.get_by_role("button", name=re.compile("검토할 수정안 1개"))).to_have_count(2, timeout=45000)
        await page.get_by_role("button", name=re.compile("검토할 수정안 1개")).last.click()
        preview = page.frame_locator('iframe[title="새 HTML 제안 미리보기"]')
        await expect(preview.locator("svg")).to_be_visible()
        detail = await (await page.request.get(f"{BASE}/api/workspaces/{workspace}")).json()
        research = await (await page.request.get(
            f"{BASE}/api/workspaces/{workspace}/proposals/{detail['proposals'][0]['id']}"
        )).json()
        assert research["path"].endswith(".html")
        assert len(research["sources"]) == 2
        assert "IRRELEVANT_STORED_BODY" not in json.dumps(research)
        assert "project-guide" in {source["id"] for source in research["sources"]}
        await page.get_by_role("button", name="변경 승인", exact=True).click()
        async with page.expect_download() as pending:
            await page.get_by_role("button", name="HTML 다운로드", exact=True).click()
        download = await pending.value
        await download.save_as(ARTIFACTS / "research.html")
        await page.screenshot(path=str(ARTIFACTS / "research-desktop.png"))
        checks.append("new HTML/SVG research succeeds with the large library and keeps only consumed evidence")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=str(ARTIFACTS / "research-mobile.png"))
        assert not errors, errors
        await context.close()
        await browser.close()
    result = {"checks": checks, "agentObservation": observed, "pageErrors": errors}
    (ARTIFACTS / "browser-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
