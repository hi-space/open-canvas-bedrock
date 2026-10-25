"""Real API + Chromium regression workflow, with a deterministic agent fixture.

Start cloud_workspace_backend.py, then Next with API_URL=http://127.0.0.1:9011.
Run OPEN_CANVAS_TEST_URL=http://127.0.0.1:3102 python tests/cloud_workspace_smoke.py.
The test creates isolated projects and uses native OPFS handles for folder sync.
"""
import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from playwright.async_api import async_playwright, expect
from workspace_smoke import select_passage

BASE = os.environ.get("OPEN_CANVAS_TEST_URL", "http://127.0.0.1:3102")
ARTIFACTS = Path(os.environ.get("OPEN_CANVAS_TEST_ARTIFACTS", "/tmp/open-canvas-cloud-browser"))
SAMPLE = "\ufeff# 검토 테스트\r\n\r\n첫 문장 입니다.\r\n\r\n두 번째 문장 입니다.\r\n\r\n참고 [1](https://example.org/source).\r\n"


async def create_project(page, name):
    await page.get_by_role("button", name="새 프로젝트", exact=True).click()
    dialog = page.get_by_role("dialog", name="새 프로젝트")
    await dialog.get_by_label("프로젝트 이름", exact=True).fill(name)
    await dialog.get_by_role("button", name="만들기", exact=True).click()
    await expect(dialog).not_to_be_visible()
    await expect(page.get_by_label("프로젝트", exact=True)).to_contain_text(name)
    return await page.get_by_label("프로젝트", exact=True).input_value()


async def read_file(page, project, path):
    response = await page.request.get(f"{BASE}/api/workspaces/{project}/files", params={"path": path})
    assert response.ok, await response.text()
    return await response.json()


async def write_file(page, project, path, content, version=None):
    response = await page.request.put(f"{BASE}/api/workspaces/{project}/files",
                                      data={"path": path, "content": content, "baseVersion": version})
    assert response.ok, await response.text()
    return await response.json()


async def send(page, message):
    await page.get_by_role("tab", name="대화", exact=True).click()
    await page.get_by_label("무엇을 함께 할까요?", exact=True).fill(message)
    await page.get_by_role("button", name="메시지 보내기", exact=True).click()


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = []
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1500, "height": 1000})
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        await page.goto(BASE)
        await expect(page.get_by_role("button", name="새 프로젝트", exact=True)).to_be_visible()
        project_a = await create_project(page, f"브라우저 검증 {uuid.uuid4().hex[:7]}")
        await page.get_by_test_id("file-import").set_input_files({
            "name": "review.md", "mimeType": "text/markdown", "buffer": SAMPLE.encode("utf-8"),
        })
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장 입니다.")
        assert (await read_file(page, project_a, "review.md"))["content"] == SAMPLE
        await page.screenshot(path=str(ARTIFACTS / "desktop-workspace.png"))
        results.append("project creation, cloud import, exact BOM and CRLF content")

        await select_passage(page, "첫 문장 입니다.")
        await page.get_by_label("선택 영역 작업").get_by_role("button", name="교정", exact=True).click()
        await expect(page.get_by_role("button", name=re.compile("검토할 수정안 1개"))).to_be_visible(timeout=15000)
        assert (await read_file(page, project_a, "review.md"))["content"] == SAMPLE
        await page.get_by_role("button", name=re.compile("검토할 수정안 1개")).last.click()
        await expect(page.get_by_text("AI 수정 제안", exact=True)).to_be_visible()
        await page.screenshot(path=str(ARTIFACTS / "desktop-review.png"))
        await page.get_by_role("button", name="변경 1 승인", exact=True).click()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장입니다.")
        approved = await read_file(page, project_a, "review.md")
        assert approved["content"] == SAMPLE.replace("첫 문장 입니다.", "첫 문장입니다.")
        results.append("exact selected passage, persisted proposal, no writes before granular approval")

        await send(page, "여러 파일을 다듬어 주세요.")
        await expect(page.get_by_role("button", name=re.compile("검토할 수정안 2개"))).to_be_visible(timeout=15000)
        await page.get_by_role("button", name=re.compile("검토할 수정안 2개")).click()
        await expect(page.get_by_role("button", name="모두 거절", exact=True)).to_be_enabled()
        await page.get_by_role("button", name="모두 거절", exact=True).click()
        assert (await read_file(page, project_a, "review.md"))["content"] == approved["content"]
        await page.get_by_role("button", name="notes/agent-note.md", exact=False).click()
        await expect(page.get_by_text("새 문서가 제안되었어요.", exact=True)).to_be_visible()
        absent = await page.request.get(f"{BASE}/api/workspaces/{project_a}/files", params={"path": "notes/agent-note.md"})
        assert absent.status == 404
        await page.get_by_role("button", name="모두 승인", exact=True).click()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("함께 만든 메모")
        results.append("multiple file proposals, reject without mutation, explicit new-file approval")

        await page.get_by_role("navigation", name="파일 목록").get_by_role("button", name=re.compile("review.md")).click()
        await page.get_by_role("button", name="Markdown 편집", exact=True).click()
        editor = page.get_by_role("textbox", name="문서 Markdown 편집기")
        await editor.click()
        await page.keyboard.press("ControlOrMeta+End")
        await page.keyboard.insert_text("\n\n직접 고친 문장.")
        await send(page, "현재 문서 전체를 교정해 주세요.")
        await expect(page.get_by_role("button", name=re.compile("검토할 수정안 1개"))).to_have_count(2, timeout=15000)
        saved = await read_file(page, project_a, "review.md")
        assert "직접 고친 문장." in saved["content"]
        assert saved["content"].startswith("\ufeff")
        assert "\r\n" in saved["content"]
        await page.get_by_role("button", name=re.compile("검토할 수정안 1개")).last.click()
        await page.get_by_role("button", name="모두 거절", exact=True).click()
        results.append("manual editor changes saved with a base version before chat")

        await editor.click()
        await page.keyboard.press("ControlOrMeta+End")
        await page.keyboard.insert_text("\n\n보관할 내 초안.")
        await page.wait_for_timeout(800)
        await page.reload()
        await expect(page.get_by_text("저장할 변경 있음", exact=True).last).to_be_visible()
        await page.get_by_role("button", name="Markdown 편집", exact=True).click()
        editor = page.get_by_role("textbox", name="문서 Markdown 편집기")
        await expect(editor).to_contain_text("보관할 내 초안.")
        remote = await read_file(page, project_a, "review.md")
        external = await write_file(page, project_a, "review.md", "# 외부 버전\n\n다른 곳에서 저장한 내용.", remote["version"])
        await page.get_by_role("button", name="클라우드 저장", exact=True).click()
        await expect(page.get_by_text("클라우드 파일이 변경되었습니다.", exact=True)).to_be_visible()
        await expect(editor).to_contain_text("보관할 내 초안.")
        assert (await read_file(page, project_a, "review.md"))["content"] == external["content"]
        await page.get_by_role("button", name="클라우드 버전 열기", exact=True).click()
        await expect(editor).to_contain_text("다른 곳에서 저장한 내용.")
        await expect(page.get_by_role("button", name="보관한 초안 다운로드")).to_be_visible()
        results.append("IndexedDB unsaved draft recovery, 409 refresh without overwriting either version")

        await send(page, "기다림 작업을 해 주세요.")
        await expect(page.get_by_text("문서와 자료를 살펴보고 있어요…", exact=False)).to_be_visible(timeout=10000)
        await page.reload()
        await expect(page.get_by_text("문서와 자료를 살펴보고 있어요…", exact=False)).to_be_visible()
        project_b = await create_project(page, f"다른 프로젝트 {uuid.uuid4().hex[:7]}")
        await page.request.post("http://127.0.0.1:9011/__test/release")
        await expect(page.get_by_text("문서를 만들거나 파일을 가져오세요.", exact=True)).to_be_visible()
        await page.get_by_label("프로젝트", exact=True).select_option(project_a)
        await expect(page.get_by_text("검토할 수정안을 준비했습니다.", exact=False).first).to_be_visible(timeout=15000)
        assert (await page.request.get(f"{BASE}/api/workspaces/{project_b}")).ok
        other = await (await page.request.get(f"{BASE}/api/workspaces/{project_b}")).json()
        assert other["files"] == [] and other["proposals"] == []
        results.append("reload running job and switch projects during inference without misplaced results")

        # A late 202 response owns only the submitted composer revision/selection.
        await write_file(page, project_b, "other.md", "# 다른 파일\n\n다른 선택 영역.")
        await page.get_by_role("button", name="읽기", exact=True).click()
        await select_passage(page, "다른 곳에서 저장한 내용.")
        reply_seen = asyncio.Event()
        release_reply = asyncio.Event()
        async def delayed_reply(route):
            response = await route.fetch()
            reply_seen.set()
            await release_reply.wait()
            await route.fulfill(response=response)
        chat_route = f"**/api/workspaces/{project_a}/chat"
        await context.route(chat_route, delayed_reply)
        await send(page, "이 문장을 살펴봐 주세요.")
        await asyncio.wait_for(reply_seen.wait(), 10)
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill("A에서 다음에 보낼 메시지")
        await page.get_by_label("프로젝트", exact=True).select_option(project_b)
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("다른 선택 영역.")
        await select_passage(page, "다른 선택 영역.")
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill("B에서 작성하는 메시지")
        release_reply.set()
        await page.wait_for_timeout(500)
        await expect(page.get_by_label("무엇을 함께 할까요?", exact=True)).to_have_value("B에서 작성하는 메시지")
        await expect(page.get_by_label("선택 영역 작업")).to_be_visible()
        await page.get_by_label("프로젝트", exact=True).select_option(project_a)
        await expect(page.get_by_label("무엇을 함께 할까요?", exact=True)).to_have_value("A에서 다음에 보낼 메시지")
        await page.get_by_label("무엇을 함께 할까요?", exact=True).fill("")
        await context.unroute(chat_route, delayed_reply)
        results.append("late chat response preserves another project's selection and newly typed composer drafts")

        await page.get_by_role("tab", name="출처", exact=True).click()
        await page.get_by_role("button", name="참고 자료 추가", exact=True).click()
        await page.get_by_label("원문 링크", exact=True).fill("https://example.org/evidence")
        await page.get_by_label("제목", exact=True).fill("확인한 참고 글")
        await page.get_by_label("참고할 발췌", exact=False).fill("프로젝트에 보관할 발췌문.")
        await page.get_by_role("button", name="출처 추가", exact=True).click()
        await expect(page.get_by_role("link", name="확인한 참고 글")).to_be_visible()
        await page.get_by_role("article").filter(has=page.get_by_role("link", name="확인한 참고 글")).get_by_role("button", name="인용 넣기").click()
        await page.get_by_role("button", name="클라우드 저장", exact=True).click()
        await expect(page.get_by_role("button", name="클라우드 저장", exact=True)).to_have_text("저장됨")
        assert "https://example.org/evidence" in (await read_file(page, project_a, "review.md"))["content"]
        await page.get_by_role("tab", name="이력", exact=True).click()
        await expect(page.get_by_role("button", name="내용 보기", exact=False).first).to_be_visible()
        results.append("persistent project sources, manual citation save, cloud revision history")

        await context.add_init_script("""window.showDirectoryPicker = async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('cloud-sync-fixture', {create:true});
          const notes = await folder.getDirectoryHandle('nested', {create:true});
          const file = await notes.getFileHandle('local.md', {create:true});
          if ((await file.getFile()).size === 0) {
            const writer = await file.createWritable();
            await writer.write('\\ufeff# 로컬 문서\\r\\n\\r\\n원본 내용.\\r\\n'); await writer.close();
          }
          return folder;
        };""")
        await page.reload()
        await page.get_by_role("button", name=re.compile("내 폴더와 연결")).click()
        await page.get_by_role("button", name="폴더 연결", exact=True).click()
        local_card = page.get_by_role("article").filter(has=page.get_by_text("nested/local.md", exact=True))
        await expect(local_card.get_by_text("로컬에 새 변경", exact=True)).to_be_visible()
        missing = await page.request.get(f"{BASE}/api/workspaces/{project_a}/files", params={"path": "nested/local.md"})
        assert missing.status == 404
        await page.get_by_role("button", name=re.compile("안전한 변경 모두 반영")).click()
        await expect(local_card.get_by_text("동일한 내용", exact=True)).to_be_visible()
        local_remote = await read_file(page, project_a, "nested/local.md")
        assert local_remote["content"] == "\ufeff# 로컬 문서\r\n\r\n원본 내용.\r\n"
        await page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const folder = await root.getDirectoryHandle('cloud-sync-fixture');
          const nested = await folder.getDirectoryHandle('nested');
          const writer = await (await nested.getFileHandle('local.md')).createWritable();
          await writer.write('# 로컬에서 고친 내용'); await writer.close();
        }""")
        await write_file(page, project_a, "nested/local.md", "# 클라우드에서 고친 내용", local_remote["version"])
        await page.get_by_role("button", name="변경 비교", exact=True).click()
        await expect(local_card.get_by_text("양쪽 내용 비교 필요", exact=True)).to_be_visible()
        await expect(local_card.get_by_role("button", name="클라우드 내용 다운로드", exact=True)).to_have_count(0)
        await local_card.get_by_role("button", name="내용 비교", exact=True).click()
        await expect(local_card.locator("pre").last).to_have_text("# 클라우드에서 고친 내용")
        await page.screenshot(path=str(ARTIFACTS / "folder-conflict.png"))
        await local_card.get_by_role("button", name="클라우드 내용 다운로드", exact=True).click()
        await expect(local_card.get_by_text("동일한 내용", exact=True)).to_be_visible()
        disk = await page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const nested = await (await root.getDirectoryHandle('cloud-sync-fixture')).getDirectoryHandle('nested');
          return await (await (await nested.getFileHandle('local.md')).getFile()).text();
        }""")
        assert disk == "# 클라우드에서 고친 내용"
        await page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const nested = await (await root.getDirectoryHandle('cloud-sync-fixture')).getDirectoryHandle('nested');
          await nested.removeEntry('local.md');
        }""")
        await page.get_by_role("button", name="변경 비교", exact=True).click()
        await expect(local_card.get_by_text("로컬 파일 없음 · 복원 가능", exact=True)).to_be_visible()
        assert (await read_file(page, project_a, "nested/local.md"))["content"] == disk
        await local_card.get_by_role("button", name="로컬 파일 복원", exact=True).click()
        await expect(local_card.get_by_text("동일한 내용", exact=True)).to_be_visible()
        await page.reload()
        await page.get_by_role("button", name=re.compile("cloud-sync-fixture")).click()
        await expect(page.get_by_role("button", name="변경 비교", exact=True)).to_be_enabled()
        results.append("native nested-folder handles, no upload on connect, batch safe sync, common baseline, explicit divergence and deletion recovery")

        await page.evaluate("""async () => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open('open-canvas-writing', 1);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const transaction = db.transaction(['documents', 'metadata'], 'readwrite');
          transaction.objectStore('documents').put({
            id: 'browser-draft-fixture', name: 'browser-draft.md', path: 'browser-draft.md',
            content: '\\ufeff# 브라우저 초안\\r\\n\\r\\n보관한 글입니다.\\r\\n',
            sources: [], revisions: [], updatedAt: Date.now(),
          });
          transaction.objectStore('metadata').put({
            version: 1, revision: 1, documentIds: ['browser-draft-fixture'],
            activeDocumentId: 'browser-draft-fixture',
          }, 'current');
          await new Promise((resolve, reject) => {
            transaction.oncomplete = resolve; transaction.onerror = () => reject(transaction.error);
          });
          db.close();
        }""")
        await page.reload()
        await expect(page.get_by_role("button", name=re.compile("브라우저 초안 가져오기"))).to_be_visible()
        absent_draft = await page.request.get(f"{BASE}/api/workspaces/{project_a}/files", params={"path": "browser-draft.md"})
        assert absent_draft.status == 404
        await page.get_by_role("button", name=re.compile("브라우저 초안 가져오기")).click()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("보관한 글입니다.")
        assert (await read_file(page, project_a, "browser-draft.md"))["content"] == "\ufeff# 브라우저 초안\r\n\r\n보관한 글입니다.\r\n"
        retained = await page.evaluate("""async () => {
          const db = await new Promise(resolve => {
            const request = indexedDB.open('open-canvas-writing', 1);
            request.onsuccess = () => resolve(request.result);
          });
          return await new Promise(resolve => {
            const request = db.transaction('documents').objectStore('documents').get('browser-draft-fixture');
            request.onsuccess = () => { resolve(request.result.content); db.close(); };
          });
        }""")
        assert retained == "\ufeff# 브라우저 초안\r\n\r\n보관한 글입니다.\r\n"
        results.append("browser drafts stay local until explicit import and remain recoverable afterward")

        old = await (await page.request.post(f"{BASE}/api/threads", data={"metadata": {"title": "보관된 이전 대화"}})).json()
        thread_id = old["thread_id"]
        await page.request.post(f"{BASE}/api/threads/{thread_id}/state", data={"values": {
            "messages": [{"id": "legacy-message", "type": "human", "content": "보관된 질문입니다."}],
            "artifact": {"currentIndex": 1, "contents": [{"index": 1, "type": "text", "title": "보관된 문서", "fullMarkdown": "# 이전 문서\n\n원래 보관된 내용."}]},
        }})
        await page.goto(f"{BASE}/canvas?threadId={thread_id}")
        await expect(page).to_have_url(re.compile(r"/\?.*legacyThreadId="))
        await page.get_by_role("button", name="이전 대화 열기", exact=True).click()
        legacy = page.get_by_role("dialog", name="보관된 이전 대화")
        await expect(legacy.get_by_text("보관된 질문입니다.", exact=True)).to_be_visible()
        await expect(legacy.get_by_text("원래 보관된 내용.", exact=True)).to_be_visible()
        await legacy.get_by_role("button", name="프로젝트에 문서로 가져오기", exact=True).click()
        await expect(legacy).not_to_be_visible()
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("원래 보관된 내용.")
        preserved = await (await page.request.get(f"{BASE}/api/threads/{thread_id}")).json()
        assert preserved["values"]["messages"][0]["content"] == "보관된 질문입니다."
        results.append("legacy deep-link forwarding, inline read-only conversation, explicit document import")

        await page.set_viewport_size({"width": 375, "height": 812})
        await page.reload()
        await expect(page.get_by_label("프로젝트", exact=True)).to_have_value(project_a)
        await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("원래 보관된 내용.")
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        await page.get_by_role("button", name="파일 목록 열기").click()
        await expect(page.get_by_label("프로젝트와 파일").get_by_role("button", name="새 문서", exact=True)).to_be_visible()
        await page.get_by_role("button", name="파일 목록 닫기").click()
        await page.get_by_role("button", name="대화 도구 열기").click()
        await expect(page.get_by_role("tab", name="출처", exact=True)).to_be_visible()
        await page.screenshot(path=str(ARTIFACTS / "mobile-chat.png"))
        await page.get_by_role("button", name="도구 패널 닫기").click()
        await page.screenshot(path=str(ARTIFACTS / "mobile-document.png"))
        results.append("375px responsive reading, file navigation, conversation and tools")
        assert not errors, errors
        report = {"passed": results, "page_errors": errors, "api": "real local FastAPI", "inference": "deterministic fixture", "filesystem": "native OPFS"}
        (ARTIFACTS / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
