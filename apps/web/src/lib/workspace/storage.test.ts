import { beforeEach, describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { createDocument } from "./documents";
import type { WorkspaceState } from "./types";

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  vi.resetModules();
});

describe("multiple-tab persistence", () => {
  it("refuses a stale tab write without hiding the other tab's new document", async () => {
    const tabA = await import("./storage");
    const original = createDocument("original.md", "original");
    await tabA.saveWorkspace({
      version: 1,
      documents: [original],
      activeDocumentId: original.id,
    });
    const stateA = (await tabA.loadWorkspace())!;
    vi.resetModules();
    const tabB = await import("./storage");
    const stateB = (await tabB.loadWorkspace())!;
    const added = createDocument("from-a.md", "keep me");
    await tabA.saveWorkspace({
      ...stateA,
      documents: [...stateA.documents, added],
    });
    const stale: WorkspaceState = {
      ...stateB,
      documents: [{ ...stateB.documents[0], content: "tab B unsaved draft" }],
    };
    await expect(tabB.saveWorkspace(stale)).rejects.toThrow(/다른 탭/);
    vi.resetModules();
    const reader = await import("./storage");
    const saved = (await reader.loadWorkspace())!;
    expect(saved.documents.map((document) => document.name)).toEqual([
      "original.md",
      "from-a.md",
    ]);
    expect(saved.documents[0].content).toBe("original");
  });
});
