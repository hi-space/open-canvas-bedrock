import { describe, expect, it } from "vitest";
import {
  FileConflictError,
  readTextFile,
  scanDirectory,
  writeFileSafely,
} from "./files";
import type { LocalDirectoryHandle, LocalFileHandle } from "./types";

function fakeFile(initial: string, onOpen?: () => string) {
  let disk = initial;
  let staged = initial;
  const handle: LocalFileHandle = {
    kind: "file",
    name: "draft.md",
    getFile: async () => new File([disk], "draft.md", { lastModified: 123 }),
    createWritable: async () => {
      if (onOpen) disk = onOpen();
      return {
        write: async (data) => {
          staged = data;
        },
        close: async () => {
          disk = staged;
        },
        abort: async () => {
          staged = disk;
        },
      };
    },
  };
  return { handle, disk: () => disk };
}

describe("local document files", () => {
  it("preserves UTF-8 BOM and Windows line endings on import", async () => {
    const file = new File(["\uFEFF# 제목\r\n\r\n본문\r\n"], "draft.md");
    expect(await readTextFile(file)).toBe("\uFEFF# 제목\r\n\r\n본문\r\n");
  });

  it("does not write over an external change, even with unchanged timestamps", async () => {
    const file = fakeFile("external revision");
    await expect(
      writeFileSafely(file.handle, "my draft", "old")
    ).rejects.toBeInstanceOf(FileConflictError);
    expect(file.disk()).toBe("external revision");
  });

  it("aborts if the file changes while the save is being opened", async () => {
    const file = fakeFile("old", () => "agent revision");
    await expect(
      writeFileSafely(file.handle, "my draft", "old")
    ).rejects.toBeInstanceOf(FileConflictError);
    expect(file.disk()).toBe("agent revision");
  });

  it("commits an approved draft against the known disk snapshot", async () => {
    const file = fakeFile("old");
    expect(await writeFileSafely(file.handle, "approved", "old")).toEqual({
      content: "approved",
      modifiedAt: 123,
    });
    expect(file.disk()).toBe("approved");
  });

  it("rejects oversized UTF-8 output before writing a file it could not reopen", async () => {
    const file = fakeFile("original");
    await expect(
      writeFileSafely(file.handle, "가".repeat(700000), "original")
    ).rejects.toThrow(/2MB/);
    expect(
      file.disk() === "original",
      "The original file must not be changed"
    ).toBe(true);
  });

  it("scans Markdown files recursively without opening dependency directories", async () => {
    const document = fakeFile("nested").handle;
    const nested: LocalDirectoryHandle = {
      kind: "directory",
      name: "notes",
      async *values() {
        yield document;
      },
      getFileHandle: async () => document,
    };
    const ignored: LocalDirectoryHandle = {
      ...nested,
      name: "node_modules",
      values() {
        throw new Error("This folder must never be traversed");
      },
    };
    const root: LocalDirectoryHandle = {
      ...nested,
      name: "writing",
      async *values() {
        yield ignored;
        yield nested;
      },
    };
    const result = await scanDirectory(root);
    expect(result.files.map((file) => file.path)).toEqual(["notes/draft.md"]);
    expect(result.complete).toBe(true);
  });
});
