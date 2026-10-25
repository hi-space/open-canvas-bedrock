import { describe, expect, it } from "vitest";
import {
  bindDocumentFile,
  createDocument,
  decideDocumentChanges,
  receiveDiskSnapshot,
  reviseDocument,
} from "./documents";
import { createProposal } from "./review";

describe("document snapshots", () => {
  it("preserves the browser draft when an external editor changes the same file", () => {
    const document = createDocument("draft.md", "original");
    document.disk = { content: "original", modifiedAt: 1 };
    document.content = "my changes";
    const next = receiveDiskSnapshot(document, {
      content: "agent changes",
      modifiedAt: 2,
    });
    expect(next.content).toBe("my changes");
    expect(next.disk?.content).toBe("original");
    expect(next.external?.content).toBe("agent changes");
  });

  it("requires review even when there are no browser edits", () => {
    const document = createDocument("draft.md", "original");
    document.disk = { content: "original", modifiedAt: 1 };
    const next = receiveDiskSnapshot(document, {
      content: "agent changes",
      modifiedAt: 2,
    });
    expect(next.content).toBe("original");
    expect(next.external?.content).toBe("agent changes");
  });

  it("recognizes an external save that already matches the draft", () => {
    const document = createDocument("draft.md", "my changes");
    document.disk = { content: "original", modifiedAt: 1 };
    const next = receiveDiskSnapshot(document, {
      content: "my changes",
      modifiedAt: 2,
    });
    expect(next.disk?.content).toBe("my changes");
    expect(next.external).toBeUndefined();
  });

  it("keeps the unsaved manual draft in history before applying an AI revision", () => {
    const document = createDocument("draft.md", "original");
    document.content = "manually edited";
    const next = reviseDocument(document, "approved AI change", "AI 수정 승인");
    expect(next.revisions.map((revision) => revision.content)).toEqual([
      "original",
      "manually edited",
      "approved AI change",
    ]);
    expect(document.content).toBe("manually edited");
  });

  it("does not allow partial approval to remove a citation moved by the full proposal", () => {
    const original =
      "First [1](https://example.org/source).\n\nAn unchanged middle paragraph with enough context.\n\nLast.";
    const replacement =
      "First.\n\nAn unchanged middle paragraph with enough context.\n\nLast [1](https://example.org/source).";
    const document = createDocument("draft.md", original);
    document.proposal = createProposal(original, replacement);
    expect(() =>
      decideDocumentChanges(
        document,
        document.proposal!.changes[0].id,
        "accepted"
      )
    ).toThrow(/출처/);
    expect(decideDocumentChanges(document, "all", "accepted").content).toBe(
      replacement
    );
    expect(document.content).toBe(original);
  });

  it("clears the old folder binding when a missing file is saved to a new target", () => {
    const document = createDocument("old.md", "draft");
    document.folderId = "old-folder";
    document.folderName = "old-folder";
    document.path = "notes/old.md";
    document.missing = true;
    const handle = {
      kind: "file" as const,
      name: "new.md",
      getFile: async () => new File(["draft"], "new.md"),
      createWritable: async () => ({
        write: async () => {},
        close: async () => {},
        abort: async () => {},
      }),
    };
    const bound = bindDocumentFile(
      document,
      handle,
      { content: "draft", modifiedAt: 2 },
      true
    );
    expect(bound.path).toBe("new.md");
    expect(bound.folderId).toBeUndefined();
    expect(bound.missing).toBe(false);
  });
});
