import { describe, expect, it } from "vitest";
import {
  decideSync,
  contentVersion,
  uploadedSyncBaseline,
  safeSyncDirection,
  validateCloudFile,
  writeRelativeFile,
} from "./cloud-sync";
import type { SyncDirectoryHandle } from "./cloud-sync";
import type { LocalFileHandle } from "./types";

describe("three-way folder synchronization", () => {
  it("downloads canonical IDs after upload and does not invent a conflict for a later remote-only edit", async () => {
    const local = "<p>원문</p>";
    const canonical = '<p data-oc-id="p">원문</p>';
    const saved = {
      content: canonical,
      version: await contentVersion(canonical),
    };
    const baseline = await uploadedSyncBaseline(local, saved);
    const localVersion = await contentVersion(local);
    expect(decideSync(localVersion, saved.version, baseline)).toBe("download");
    const remoteEdit = await contentVersion(
      '<p data-oc-id="p">승인한 수정</p>'
    );
    expect(decideSync(localVersion, remoteEdit, baseline)).toBe("download");
    expect(
      decideSync(await contentVersion("<p>로컬 수정</p>"), remoteEdit, baseline)
    ).toBe("conflict");
  });

  it("includes only unambiguous changes in a batch, leaving divergence and deletion for a decision", () => {
    expect(safeSyncDirection("upload")).toBe("upload");
    expect(safeSyncDirection("download")).toBe("download");
    for (const status of [
      "conflict",
      "local-deleted",
      "remote-deleted",
      "synced",
      "absent",
    ] as const)
      expect(safeSyncDirection(status)).toBeUndefined();
  });
  it.each([
    ["same", "same", undefined, "synced"],
    ["new-local", "base", "base", "upload"],
    ["base", "new-cloud", "base", "download"],
    ["new-local", "new-cloud", "base", "conflict"],
    ["local", "cloud", undefined, "conflict"],
    ["new", null, undefined, "upload"],
    [null, "new", undefined, "download"],
    [null, "base", "base", "local-deleted"],
    ["base", null, "base", "remote-deleted"],
    [null, "new-cloud", "base", "local-deleted"],
    ["new-local", null, "base", "remote-deleted"],
    [null, null, "base", "absent"],
  ] as const)(
    "classifies local=%s remote=%s base=%s as %s without propagating deletion",
    (local, remote, base, expected) => {
      expect(decideSync(local, remote, base)).toBe(expected);
    }
  );

  it("enforces nested paths, exact UTF-8 limits and hidden-path restrictions", () => {
    expect(() =>
      validateCloudFile("notes/한글.md", "\uFEFF# 글\r\n")
    ).not.toThrow();
    for (const path of [
      "../escape.md",
      "/absolute.md",
      "a//empty.md",
      ".hidden.md",
      "folder/.git/note.md",
      "a\\escape.md",
      "a/b/c/d/e/f/g/h/i.md",
      "script.js",
    ]) {
      expect(() => validateCloudFile(path, "text"), path).toThrow();
    }
    expect(() => validateCloudFile("large.md", "x".repeat(200001))).toThrow();
    expect(() => validateCloudFile("empty.md", "")).not.toThrow();
  });

  it("does not overwrite an existing empty local file when the scan said absent", async () => {
    let writes = 0;
    const handle: LocalFileHandle = {
      kind: "file",
      name: "note.md",
      getFile: async () => new File([""], "note.md"),
      createWritable: async () => {
        writes++;
        throw new Error("must not open a writer");
      },
    };
    const directory: SyncDirectoryHandle = {
      kind: "directory",
      name: "folder",
      async *values() {
        yield handle;
      },
      getFileHandle: async () => handle,
      getDirectoryHandle: async () => directory,
    };
    await expect(
      writeRelativeFile(directory, "note.md", "cloud text", null)
    ).rejects.toThrow(/변경|존재/);
    expect(writes).toBe(0);
  });
});
