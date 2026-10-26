// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SourcesPanel } from "./SourcesPanel";
import type {
  SourceReference,
  WorkspaceDocument,
} from "../../lib/workspace/types";

let root: Root;
let container: HTMLDivElement;
const reference = (id = "a", version = "v1"): SourceReference => ({
  id,
  title: `자료 ${id}`,
  url: `https://example.com/${id}`,
  version,
  excerptCharacters: 25,
});
const documentWith = (sources: SourceReference[]): WorkspaceDocument => ({
  id: "project/file",
  name: "file.md",
  path: "file.md",
  content: "",
  sources,
  revisions: [],
  updatedAt: 1,
});
function button(label: string) {
  const match = [...container.querySelectorAll("button")].find((item) =>
    item.textContent?.includes(label)
  );
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}
function render(sources: SourceReference[], onRead = vi.fn(), onAdd = vi.fn()) {
  root.render(
    <SourcesPanel
      document={documentWith(sources)}
      hasSelection={false}
      onCite={vi.fn()}
      onRemove={vi.fn()}
      onAdd={onAdd}
      onRead={onRead}
      projectSources
    />
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
  vi.restoreAllMocks();
});

it("loads only the excerpt the person opens", async () => {
  const read = vi.fn(async () => ({
    ...reference(),
    excerpt: "요청한 자료의 실제 발췌입니다.",
  }));
  await act(async () => render([reference(), reference("b")], read));
  expect(read).not.toHaveBeenCalled();
  expect(container.textContent).toContain("2개");
  await act(async () => button("발췌 보기").click());
  expect(read).toHaveBeenCalledExactlyOnceWith("a");
  expect(container.textContent).toContain("요청한 자료의 실제 발췌입니다.");
});

it("retries an excerpt read without removing the source", async () => {
  const read = vi
    .fn()
    .mockRejectedValueOnce(new Error("일시적인 연결 오류"))
    .mockResolvedValueOnce({ ...reference(), excerpt: "다시 읽은 발췌" });
  await act(async () => render([reference()], read));
  await act(async () => button("발췌 보기").click());
  expect(container.textContent).toContain("일시적인 연결 오류");
  await act(async () => button("다시 읽기").click());
  expect(container.textContent).toContain("다시 읽은 발췌");
});

it("does not show an old excerpt after its source version changes", async () => {
  let finish!: (source: SourceReference) => void;
  const read = vi.fn(
    () => new Promise<SourceReference>((resolve) => (finish = resolve))
  );
  await act(async () => render([reference()], read));
  await act(async () => button("발췌 보기").click());
  await act(async () => render([reference("a", "v2")], read));
  await act(async () => finish({ ...reference(), excerpt: "이전 버전 발췌" }));
  expect(container.textContent).not.toContain("이전 버전 발췌");
});

it("pages a large project library without fetching all its bodies", async () => {
  const read = vi.fn();
  await act(async () =>
    render(
      Array.from({ length: 65 }, (_, index) => reference(String(index))),
      read
    )
  );
  expect(container.querySelectorAll("article")).toHaveLength(20);
  await act(async () => button("더 보기").click());
  expect(container.querySelectorAll("article")).toHaveLength(40);
  expect(read).not.toHaveBeenCalled();
});
