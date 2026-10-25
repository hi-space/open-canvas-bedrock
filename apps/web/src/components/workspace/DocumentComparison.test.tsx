// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DocumentComparison } from "./DocumentComparison";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (
    globalThis as typeof globalThis & {
      IS_REACT_ACT_ENVIRONMENT: boolean;
    }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function open(before: string, after: string, path = "draft.md") {
  await act(async () =>
    root.render(
      <DocumentComparison
        name={path}
        path={path}
        before={{ content: before, label: "수정 전" }}
        after={{ content: after, label: "수정 후" }}
        description="문서 전체 비교"
        trigger={<button>나란히 비교</button>}
      />
    )
  );
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  await act(async () => container.querySelector("button")!.click());
  return document.querySelector<HTMLElement>('[role="dialog"]')!;
}

describe("whole-document comparison", () => {
  it("renders both Markdown versions and highlights only changed blocks", async () => {
    const dialog = await open(
      "# 제목\n\nOld paragraph\n\nUnchanged",
      "# 제목\n\nNew paragraph\n\nUnchanged"
    );
    const before = dialog.querySelector('[aria-label="수정 전 문서"]')!;
    const after = dialog.querySelector('[aria-label="수정 후 문서"]')!;
    expect(before.querySelector("h1")?.textContent).toBe("제목");
    expect(after.querySelector("h1")?.textContent).toBe("제목");
    expect(before.querySelectorAll("[data-comparison-change]").length).toBe(1);
    expect(after.querySelectorAll("[data-comparison-change]").length).toBe(1);
    expect(before.querySelector("[data-comparison-change]")?.textContent).toBe(
      "Old paragraph"
    );
    expect(after.querySelector("[data-comparison-change]")?.textContent).toBe(
      "New paragraph"
    );
    expect(dialog.querySelector("textarea, [contenteditable]")).toBeNull();
  });

  it("preserves exact source and reveals changes to a link destination", async () => {
    const before = "\uFEFF# 제목\r\n\r\n[참고](https://example.org/old) 😀";
    const after = "\uFEFF# 제목\r\n\r\n[참고](https://example.org/new) 😁";
    const dialog = await open(before, after);
    await act(async () =>
      Array.from(dialog.querySelectorAll("button"))
        .find((button) => button.textContent === "원문 비교")!
        .click()
    );
    expect(
      dialog.querySelector('[aria-label="수정 전 원문"]')?.textContent
    ).toBe(before);
    expect(
      dialog.querySelector('[aria-label="수정 후 원문"]')?.textContent
    ).toBe(after);
    expect(dialog.querySelector("del")?.textContent).toContain("old");
    expect(dialog.querySelector("ins")?.textContent).toContain("new");
  });

  it.each([
    ["- foo\n\n- bar", "1. foo\n\n2. bar", "li"],
    ["Text", "> Text", "blockquote"],
    ["| A |\n| --- |\n| x |", "| A |\n| ---: |\n| x |", "table"],
  ])(
    "highlights structural Markdown changes: %s",
    async (before, after, tag) => {
      const dialog = await open(before, after);
      expect(
        dialog.querySelector(
          `[aria-label="수정 후 문서"] ${tag}[data-comparison-change]`
        )
      ).not.toBeNull();
    }
  );

  it("renders two isolated HTML previews with their respective versions", async () => {
    const dialog = await open(
      '<h1>이전 화면</h1><script>alert("before")</script>',
      '<h1>수정 화면</h1><script>alert("after")</script>',
      "page.html"
    );
    const frames = dialog.querySelectorAll("iframe");
    expect(frames.length).toBe(2);
    expect(frames[0].srcdoc).toContain("이전 화면");
    expect(frames[1].srcdoc).toContain("수정 화면");
    for (const frame of frames) {
      expect(frame.getAttribute("sandbox")).toBe("");
      expect(frame.srcdoc).not.toContain("<script");
    }
  });

  it("explains an empty previous version and identical versions", async () => {
    let dialog = await open("", "# 새 문서");
    expect(
      dialog.querySelector('[aria-label="수정 전 문서"]')?.textContent
    ).toContain("내용이 없습니다");
    await act(async () =>
      dialog
        .querySelector<HTMLButtonElement>('[aria-label="비교 닫기"]')!
        .click()
    );
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    dialog = await open("같은 내용", "같은 내용");
    expect(dialog.textContent).toContain("두 버전의 내용이 같습니다");
    expect(dialog.querySelector("[data-comparison-change]")).toBeNull();
  });
});
