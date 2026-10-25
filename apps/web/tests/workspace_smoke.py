"""Browser integration checks. Run against a running development server.

Requires Python Playwright and its Chromium browser. AI and scraping responses
are stubbed; IndexedDB and File System handles are real browser implementations.
OPFS supplies isolated test files in place of an OS directory picker.
No AWS inference or external scraping is performed.
"""
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright, expect

BASE_URL = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3101")
ARTIFACTS = Path(os.environ.get("OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-workspace"))
MODEL = "global.anthropic.claude-opus-5-5"
SAMPLE = "# 검토 테스트\n\n첫 문장 입니다.\n\n두 번째 문장입니다.\n\n참고 [1](https://example.org/source).\n"


async def persisted(page):
    await expect(page.get_by_text("이 브라우저에 초안 보관 중", exact=True)).to_be_visible()


async def select_passage(page, paragraph, start=0, end=None):
    await page.evaluate(
        """({paragraph, start, end}) => {
          const block = [...document.querySelectorAll('[data-source-start]')]
            .find(node => node.textContent === paragraph);
          if (!block) throw new Error('Paragraph not found: ' + paragraph);
          const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
          const nodes = []; let node; let offset = 0;
          while ((node = walker.nextNode())) {
            nodes.push({node, from: offset, to: offset + node.textContent.length});
            offset += node.textContent.length;
          }
          const lastOffset = end ?? offset;
          const first = nodes.find(item => item.from <= start && start < item.to);
          const last = nodes.find(item => item.from < lastOffset && lastOffset <= item.to);
          const range = document.createRange();
          range.setStart(first.node, start - first.from);
          range.setEnd(last.node, lastOffset - last.from);
          const selection = window.getSelection();
          selection.removeAllRanges(); selection.addRange(range);
          block.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
        }""",
        {"paragraph": paragraph, "start": start, "end": end},
    )


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1500, "height": 1000})
        await context.route(
            "**/api/models/list",
            lambda route: route.fulfill(json={
                "models": [{"name": MODEL, "label": "Claude Opus 5.5"}],
                "defaultModelName": MODEL,
            }),
        )
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        response_ready = asyncio.Event()
        response_ready.set()
        request_seen = asyncio.Event()
        requests = []
        replacement = {"text": "첫 문장입니다."}

        async def propose(route):
            requests.append(route.request.post_data_json)
            request_seen.set()
            await response_ready.wait()
            await route.fulfill(json={"replacement": replacement["text"], "explanation": "띄어쓰기를 교정했습니다."})

        await context.route("**/api/writing/propose", propose)
        await page.goto(BASE_URL)
        await persisted(page)
        await page.get_by_test_id("file-import").set_input_files({
            "name": "review.md", "mimeType": "text/markdown", "buffer": SAMPLE.encode(),
        })
        await expect(page.get_by_label("문서 파일 이름")).to_have_value("review.md")
        await select_passage(page, "첫 문장 입니다.")
        await page.get_by_role("button", name="교정", exact=True).first.click()
        await expect(page.get_by_text("AI 수정 제안", exact=True)).to_be_visible()
        assert requests[-1]["selectedText"] == "첫 문장 입니다."
        await expect(page.get_by_role("document", name="문서 읽기").get_by_text("첫 문장 입니다.", exact=True)).to_be_visible()
        await page.screenshot(path=str(ARTIFACTS / "review-desktop.png"))
        await page.get_by_role("button", name="모두 승인", exact=True).click()
        await expect(page.get_by_role("document", name="문서 읽기").get_by_text("첫 문장입니다.", exact=True)).to_be_visible()
        await persisted(page)
        await page.reload()
        await persisted(page)
        await expect(page.get_by_role("document", name="문서 읽기").get_by_text("첫 문장입니다.", exact=True)).to_be_visible()
        results.append("import, exact selection, preview-before-approval, approval, reload")

        # A slow result stays attached to its original file.
        response_ready.clear()
        request_seen.clear()
        replacement["text"] = "두 번째 문장도 다듬었습니다."
        await select_passage(page, "두 번째 문장입니다.")
        await page.get_by_role("button", name="교정", exact=True).first.click()
        await asyncio.wait_for(request_seen.wait(), 10)
        await page.get_by_role("button", name="새 문서").click()
        editor = page.get_by_role("textbox", name="문서 Markdown 편집기")
        await expect(editor).to_be_visible()
        await editor.click()
        await page.keyboard.insert_text("# 다른 파일\n\n그대로 남을 내용.")
        response_ready.set()
        await persisted(page)
        await expect(page.get_by_text("AI 수정 제안", exact=True)).to_have_count(0)
        await page.get_by_role("button", name="review.md", exact=False).click()
        await page.get_by_role("button", name="읽기", exact=True).click()
        await expect(page.get_by_text("AI 수정 제안", exact=True)).to_be_visible()
        await page.get_by_role("button", name="모두 거절", exact=True).click()
        await expect(page.get_by_role("document", name="문서 읽기").get_by_text("두 번째 문장입니다.", exact=True)).to_be_visible()
        results.append("file switch during inference and reject-without-mutation")

        # Manual evidence and inline Markdown citations survive export.
        await select_passage(page, "두 번째 문장입니다.")
        await page.get_by_role("tab", name="출처", exact=True).click()
        await page.get_by_role("button", name="참고 자료 추가", exact=True).click()
        await page.get_by_label("원문 링크", exact=True).fill("https://example.org/new")
        await page.get_by_label("제목", exact=True).fill("새 참고 글")
        await page.get_by_label("참고할 발췌", exact=False).fill("사실 확인을 위한 발췌입니다.")
        await page.get_by_role("button", name="출처 추가", exact=True).click()
        source_card = page.get_by_role("article").filter(has=page.get_by_role("link", name="새 참고 글"))
        await source_card.get_by_role("button", name="인용 넣기").click()
        citation = page.get_by_role("document", name="문서 읽기").locator('a[href="https://example.org/new"]')
        await expect(citation).to_have_attribute("target", "_blank")
        async with page.expect_download() as download_info:
            await page.get_by_role("button", name="Markdown 다운로드", exact=True).click()
        download = await download_info.value
        destination = ARTIFACTS / "export.md"
        await download.save_as(destination)
        exported = destination.read_text()
        assert '[2](<https://example.org/new> "새 참고 글")' in exported
        assert "[1](https://example.org/source)" in exported
        results.append("source evidence, inline citation, clickable URL, lossless Markdown export")

        # Changing URL while its scrape is pending cannot attach A's evidence to B.
        scrape_seen = asyncio.Event()
        scrape_release = asyncio.Event()

        async def scrape(route):
            scrape_seen.set()
            await scrape_release.wait()
            try:
                await route.fulfill(json={
                    "success": True,
                    "documents": [{"name": "Wrong A title", "type": "text", "data": "Evidence from A", "metadata": {"title": "Wrong A title"}}],
                })
            except Exception:
                pass  # A changing URL cancels this request.

        await context.route("**/api/firecrawl/scrape", scrape)
        await page.get_by_role("button", name="참고 자료 추가", exact=True).click()
        await page.get_by_label("원문 링크", exact=True).fill("https://example.org/a")
        await page.get_by_role("button", name="링크에서 제목·발췌 불러오기").click()
        await asyncio.wait_for(scrape_seen.wait(), 10)
        await page.get_by_label("원문 링크", exact=True).fill("https://example.org/b")
        scrape_release.set()
        await expect(page.get_by_label("제목", exact=True)).to_have_value("")
        await expect(page.get_by_label("참고할 발췌", exact=False)).to_have_value("")
        results.append("scrape URL/evidence race")
        await page.get_by_role("button", name="입력 닫기").click()
        await persisted(page)

        # Native browser file handles, isolated in OPFS.
        file_context = await browser.new_context(viewport={"width": 1500, "height": 1000})
        await file_context.route("**/api/models/list", lambda route: route.fulfill(json={
            "models": [{"name": MODEL, "label": "Claude Opus 5.5"}], "defaultModelName": MODEL,
        }))
        await file_context.add_init_script("""window.showDirectoryPicker = async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('writing-fixture', {create:true});
          const file = await folder.getFileHandle('local.md', {create:true});
          const writer = await file.createWritable();
          await writer.write('# 로컬 파일\\n\\n원래 내용.'); await writer.close();
          return folder;
        };
        window.showSaveFilePicker = async () => {
          const root = await navigator.storage.getDirectory();
          return root.getFileHandle('saved-elsewhere.md', {create:true});
        };""")
        file_page = await file_context.new_page()
        file_page.on("pageerror", lambda error: errors.append(str(error)))
        await file_page.goto(BASE_URL)
        await persisted(file_page)
        await file_page.get_by_role("button", name="폴더 연결", exact=True).click()
        await expect(file_page.get_by_text("파일과 동기화됨", exact=True)).to_be_visible()
        await file_page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('writing-fixture');
          const file = await folder.getFileHandle('local.md');
          const writer = await file.createWritable();
          await writer.write('# 로컬 파일\\n\\n외부에서 고친 내용.'); await writer.close();
        }""")
        await expect(file_page.get_by_text("파일이 다른 곳에서 변경되었어요.")).to_be_visible(timeout=15000)
        await expect(file_page.get_by_role("document", name="문서 읽기").get_by_text("원래 내용.", exact=True)).to_be_visible()
        await file_page.get_by_role("button", name="변경 비교", exact=True).click()
        await file_page.get_by_role("button", name="모두 승인", exact=True).click()
        await expect(file_page.get_by_role("document", name="문서 읽기").get_by_text("외부에서 고친 내용.", exact=True)).to_be_visible()
        await persisted(file_page)
        await file_page.reload()
        await persisted(file_page)
        await expect(file_page.get_by_text("파일과 동기화됨", exact=True)).to_be_visible()
        results.append("directory handles, external change detection/review, persisted handle reload")

        await file_page.get_by_role("button", name="Markdown 편집", exact=True).click()
        file_editor = file_page.get_by_role("textbox", name="문서 Markdown 편집기")
        await file_editor.click()
        await file_page.keyboard.press("ControlOrMeta+End")
        await file_page.keyboard.insert_text("\n\n브라우저에서 추가한 내용.")
        await file_page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('writing-fixture');
          const writer = await (await folder.getFileHandle('local.md')).createWritable();
          await writer.write('# 로컬 파일\\n\\n다시 바뀐 외부 원본.'); await writer.close();
        }""")
        await file_page.get_by_role("button", name="파일 저장", exact=True).click()
        await expect(file_page.get_by_role("alert").filter(has_text="파일이 다른 곳에서")).to_contain_text("변경")
        disk = await file_page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('writing-fixture');
          return await (await (await folder.getFileHandle('local.md')).getFile()).text();
        }""")
        assert disk == "# 로컬 파일\n\n다시 바뀐 외부 원본."
        await file_page.get_by_role("button", name="오류 안내 닫기").click()
        await file_page.get_by_role("button", name="현재 초안 유지", exact=True).click()
        await file_page.get_by_role("button", name="파일 저장", exact=True).click()
        await expect(file_page.get_by_text("파일과 동기화됨", exact=True)).to_be_visible()
        results.append("compare-before-save conflict, explicit keep-draft resolution, file save")

        await file_page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('writing-fixture');
          await folder.removeEntry('local.md');
        }""")
        await expect(file_page.get_by_text("원본 파일이 이동되거나 삭제되었습니다.", exact=False)).to_be_visible(timeout=15000)
        await file_page.get_by_role("button", name="파일 저장", exact=True).click()
        await expect(file_page.get_by_text("파일과 동기화됨", exact=True)).to_be_visible()
        await file_page.get_by_role("button", name="폴더 변경 사항 새로고침").click()
        await expect(file_page.get_by_text("원본 파일이 이동되거나 삭제되었습니다.", exact=False)).to_have_count(0)
        results.append("deleted file recovery through normal Save and replacement binding")

        mobile = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        await mobile.route("**/api/models/list", lambda route: route.fulfill(json={
            "models": [{"name": MODEL, "label": "Claude Opus 5.5"}], "defaultModelName": MODEL,
        }))
        mobile_page = await mobile.new_page()
        mobile_page.on("pageerror", lambda error: errors.append(str(error)))
        await mobile_page.goto(BASE_URL)
        await expect(mobile_page.get_by_role("button", name="파일 목록 열기")).to_be_visible()
        assert await mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        await mobile_page.screenshot(path=str(ARTIFACTS / "mobile.png"), full_page=True)
        await mobile_page.get_by_role("button", name="파일 목록 열기").click()
        await expect(mobile_page.get_by_role("button", name="새 문서")).to_be_visible()
        await mobile_page.get_by_role("button", name="파일 목록 닫기").click()
        await mobile_page.get_by_role("button", name="검토 도구 열기").click()
        await expect(mobile_page.get_by_role("tab", name="출처", exact=True)).to_be_visible()
        await mobile_page.get_by_role("button", name="검토 패널 닫기").click()
        results.append("390px mobile layout and accessible panel navigation")

        assert not errors, errors
        report = {"passed": results, "page_errors": errors, "inference": "mocked", "filesystem": "native OPFS handles"}
        (ARTIFACTS / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
