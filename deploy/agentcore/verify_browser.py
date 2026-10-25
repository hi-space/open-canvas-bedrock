"""Interactive production smoke. Credentials stay in memory and are never saved."""
import asyncio
import getpass
import json
import os
from pathlib import Path
import re
import sys
import uuid
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/web/tests"))
from workspace_smoke import select_passage

SITE = "https://canvas.hi-yoo.com"
LOGIN_HOST = "html-canvas-913524902871.auth.ap-northeast-2.amazoncognito.com"
SAMPLE = "\ufeff# 연결 확인\r\n\r\n첫 문장 입니다.\r\n\r\n한글과 이모지 😀를 보존합니다.\r\n"


async def verify(email, password, output):
    phase = "authentication"
    result = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = await browser.new_context(viewport={"width": 1440, "height": 1000})
            page = await context.new_page()
            await page.goto(SITE, wait_until="domcontentloaded")
            if urlsplit(page.url).hostname != LOGIN_HOST:
                raise RuntimeError("Unexpected authentication host")
            await page.locator('input[name="username"]').fill(email)
            await page.locator('input[type="password"]').fill(password)
            await page.get_by_role("button", name="로그인", exact=True).click()
            await page.wait_for_url(SITE + "/**", timeout=60000)
            phase = "workspace"
            errors = []
            page.on("pageerror", lambda _error: errors.append("pageerror"))
            await expect(page.get_by_role("button", name="새 프로젝트", exact=True)).to_be_visible(timeout=60000)
            listing = await page.request.get(SITE + "/api/workspaces")
            assert listing.status == 200
            assert (await listing.json())["storage"] == "cloud"

            name = "배포 검증 " + uuid.uuid4().hex[:8]
            await page.get_by_role("button", name="새 프로젝트", exact=True).click()
            dialog = page.get_by_role("dialog", name="새 프로젝트")
            await dialog.get_by_label("프로젝트 이름", exact=True).fill(name)
            await dialog.get_by_role("button", name="만들기", exact=True).click()
            await expect(dialog).not_to_be_visible()
            await expect(page.get_by_label("프로젝트", exact=True)).to_contain_text(name)
            project = await page.get_by_label("프로젝트", exact=True).input_value()
            result.update(projectId=project, projectName=name)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            os.chmod(output, 0o600)
            await page.get_by_test_id("file-import").set_input_files({
                "name": "verification.md", "mimeType": "text/markdown", "buffer": SAMPLE.encode(),
            })
            await expect(page.get_by_role("document", name="문서 읽기")).to_contain_text("첫 문장 입니다.")

            async def contents():
                response = await page.request.get(SITE + f"/api/workspaces/{project}/files", params={"path": "verification.md"})
                assert response.status == 200
                return (await response.json())["content"]

            assert await contents() == SAMPLE
            phase = "agent"
            await select_passage(page, "첫 문장 입니다.")
            await page.get_by_label("선택 영역 작업").get_by_role("button", name="교정", exact=True).click()
            await expect(page.get_by_role("button", name=re.compile("검토할 수정안 1개"))).to_be_visible(timeout=240000)
            assert await contents() == SAMPLE
            await page.get_by_role("button", name=re.compile("검토할 수정안 1개")).last.click()
            await expect(page.get_by_text("AI 수정 제안", exact=True)).to_be_visible()
            await page.screenshot(path=str(output.parent / "production-review.png"))

            phase = "approval"
            await page.get_by_role("button", name="모두 승인", exact=True).click()
            await expect(page.get_by_role("document", name="문서 읽기")).not_to_contain_text("첫 문장 입니다.")
            approved = await contents()
            assert approved != SAMPLE
            assert approved.startswith("\ufeff# 연결 확인\r\n\r\n")
            assert approved.endswith("\r\n\r\n한글과 이모지 😀를 보존합니다.\r\n")
            await page.reload()
            await expect(page.get_by_role("document", name="문서 읽기")).to_be_visible()
            assert await contents() == approved
            await page.screenshot(path=str(output.parent / "production-workspace.png"))
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path=str(output.parent / "production-mobile.png"))
            assert not errors
            result.update(
                ok=True, authentication=True, cloudPersistence=True,
                liveAgentProposal=True, noWriteBeforeApproval=True,
                approvedWritePersisted=True, reload=True, pageErrors=0,
            )
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps({key: value for key, value in result.items() if key not in {"projectId", "projectName"}}))
        except Exception as error:
            # Browser exception strings can echo text entered into password fields.
            print(json.dumps({"ok": False, "phase": phase, "errorType": type(error).__name__}))
            raise SystemExit(1) from None
        finally:
            await browser.close()


if __name__ == "__main__":
    email = os.environ["CANVAS_LOGIN_EMAIL"]
    output = Path(os.environ["CANVAS_VERIFY_OUTPUT"])
    password = getpass.getpass("Cognito password (not stored): ")
    asyncio.run(verify(email, password, output))
