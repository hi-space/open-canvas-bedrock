// @vitest-environment jsdom

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDocument } from "../../lib/workspace/documents";
import { createProposal, decideChanges } from "../../lib/workspace/review";
import type { WorkspaceDocument } from "../../lib/workspace/types";
import { ReviewPanel } from "./ReviewPanel";
import { HistoryPanel } from "./HistoryPanel";

let container: HTMLDivElement;
let root: Root;
const original = "# 제목\n\nFirst old paragraph.\n\nLast old paragraph.";
const proposed = "# 제목\n\nFirst new paragraph.\n\nLast new paragraph.";

function fixture() {
  return {
    ...createDocument("draft.md", original),
    proposal: createProposal(original, proposed),
  };
}

function button(scope: ParentNode, label: string) {
  const found = Array.from(scope.querySelectorAll("button")).find(
    (item) =>
      item.getAttribute("aria-label") === label ||
      item.textContent?.trim() === label
  );
  expect(found, `button: ${label}`).toBeDefined();
  return found!;
}

function ReviewHarness({ initial }: { initial: WorkspaceDocument }) {
  const [current, setCurrent] = useState(initial);
  return (
    <>
      <output data-current-document>{current.content}</output>
      <ReviewPanel
        document={current}
        pending={false}
        onDecide={(changeId, decision) =>
          setCurrent((document) => ({
            ...document,
            ...decideChanges(
              document.content,
              document.proposal!,
              changeId,
              decision
            ),
          }))
        }
        onDismiss={() =>
          setCurrent((document) => ({ ...document, proposal: undefined }))
        }
        onCancel={() => undefined}
      />
    </>
  );
}

beforeEach(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("comparison entry points", () => {
  it("keeps proposal snapshots stable through individual approval and rejection", async () => {
    await act(async () => root.render(<ReviewHarness initial={fixture()} />));
    await act(async () => button(container, "나란히 비교").click());
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(container.querySelector("output")?.textContent).toBe(original);
    const before = dialog.querySelector('[aria-label="수정 전 문서"]')!;
    const after = dialog.querySelector('[aria-label="수정 후 문서"]')!;
    expect(before.textContent).toContain("First old paragraph.");
    expect(after.textContent).toContain("Last new paragraph.");

    await act(async () => button(dialog, "변경 1 승인").click());
    expect(container.querySelector("output")?.textContent).toBe(
      "# 제목\n\nFirst new paragraph.\n\nLast old paragraph."
    );
    expect(before.textContent).toContain("First old paragraph.");
    expect(after.textContent).toContain("Last new paragraph.");

    await act(async () => button(dialog, "모두 거절").click());
    expect(container.querySelector("output")?.textContent).toContain(
      "Last old paragraph."
    );
    expect(after.textContent).toContain("Last new paragraph.");
    expect(dialog.textContent).toContain("검토 완료");
  });

  it("keeps approvals disabled for a stale draft and while a decision is in flight", async () => {
    const onDecide = vi.fn();
    const initial = fixture();
    for (const scenario of [
      {
        document: { ...initial, content: "직접 수정한 초안" },
        deciding: false,
      },
      { document: initial, deciding: true },
    ]) {
      await act(async () =>
        root.render(
          <ReviewPanel
            {...scenario}
            pending={false}
            onDecide={onDecide}
            onDismiss={() => undefined}
            onCancel={() => undefined}
          />
        )
      );
      await act(async () => button(container, "나란히 비교").click());
      const dialog = document.querySelector('[role="dialog"]')!;
      expect(button(dialog, "모두 승인").disabled).toBe(true);
      expect(button(dialog, "변경 1 승인").disabled).toBe(true);
      await act(async () => button(dialog, "모두 승인").click());
      expect(onDecide).not.toHaveBeenCalled();
      await act(async () => button(dialog, "비교 닫기").click());
    }
  });

  it("compares history with the current draft without restoring it", async () => {
    const initial = fixture();
    initial.content = "# 현재 초안\n\n아직 저장하지 않은 내용.";
    const onRestore = vi.fn();
    await act(async () =>
      root.render(
        <HistoryPanel document={initial} onRestore={onRestore} cloud />
      )
    );
    await act(async () => button(container, "나란히 비교").click());
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(
      dialog.querySelector('[aria-label="이전 버전 문서"]')?.textContent
    ).toContain("First old paragraph.");
    expect(
      dialog.querySelector('[aria-label="현재 문서"]')?.textContent
    ).toContain("아직 저장하지 않은 내용.");
    expect(onRestore).not.toHaveBeenCalled();
  });

  it("closes an obsolete comparison when a different proposal is opened", async () => {
    const render = (current: WorkspaceDocument) =>
      root.render(
        <ReviewPanel
          document={current}
          pending={false}
          onDecide={() => undefined}
          onDismiss={() => undefined}
          onCancel={() => undefined}
        />
      );
    await act(async () => render(fixture()));
    await act(async () => button(container, "나란히 비교").click());
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
    await act(async () => render(fixture()));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });
});
