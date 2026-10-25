import "fake-indexeddb/auto";
import { describe, expect, it } from "vitest";
import { loadCloudDrafts, saveCloudDraft } from "./cloud-storage";
import type { CloudDraft } from "./cloud-state";

const draft = (content: string): CloudDraft => ({
  file: {
    path: "notes/draft.md",
    name: "draft.md",
    content: "base",
    version: "base-hash",
    bytes: 4,
    updatedAt: 1,
  },
  content,
});

describe("cloud draft recovery in IndexedDB", () => {
  it("retains exact unsaved text separately for each project", async () => {
    await saveCloudDraft(
      "storage-a",
      "notes/draft.md",
      draft("\uFEFF# 글\r\n"),
      0
    );
    await saveCloudDraft("storage-b", "notes/draft.md", draft("project B"), 0);
    const a = await loadCloudDrafts("storage-a");
    const b = await loadCloudDrafts("storage-b");
    expect(a[0].draft?.content).toBe("\uFEFF# 글\r\n");
    expect(b[0].draft?.content).toBe("project B");
  });

  it("does not replace another tab's newer unsaved draft", async () => {
    const revision = await saveCloudDraft(
      "tabs",
      "notes/draft.md",
      draft("first"),
      0
    );
    await saveCloudDraft(
      "tabs",
      "notes/draft.md",
      draft("other tab"),
      revision
    );
    await expect(
      saveCloudDraft("tabs", "notes/draft.md", draft("stale tab"), revision)
    ).rejects.toThrow(/다른 탭/);
    expect((await loadCloudDrafts("tabs"))[0].draft?.content).toBe("other tab");
  });
});
