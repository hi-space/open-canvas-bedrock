import {
  MAX_FILE_BYTES,
  isDocumentFile,
  readFileSnapshot,
  requestWritePermission,
  writeFileSafely,
} from "./files";
import type { LocalDirectoryHandle, LocalFileHandle } from "./types";

export type SyncStatus =
  | "synced"
  | "upload"
  | "download"
  | "conflict"
  | "local-deleted"
  | "remote-deleted"
  | "absent";

export function safeSyncDirection(
  status: SyncStatus
): "upload" | "download" | undefined {
  return status === "upload" || status === "download" ? status : undefined;
}

export interface SyncDirectoryHandle extends LocalDirectoryHandle {
  getDirectoryHandle(
    name: string,
    options?: { create?: boolean }
  ): Promise<SyncDirectoryHandle>;
}

/** Inputs are hashes of exact UTF-8 content, never timestamps or sizes. */
export function decideSync(
  local: string | null,
  remote: string | null,
  base?: string
): SyncStatus {
  if (local === null && remote === null) return "absent";
  if (local === remote) return "synced";
  if (local === null) return base ? "local-deleted" : "download";
  if (remote === null) return base ? "remote-deleted" : "upload";
  if (base && remote === base) return "upload";
  if (base && local === base) return "download";
  return "conflict";
}

export function validateCloudFile(path: string, content: string): void {
  const parts = path.split("/");
  if (
    !path ||
    path.length > 500 ||
    path.includes("\\") ||
    Array.from(path).some(
      (character) =>
        character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127
    ) ||
    parts.length > 8 ||
    parts.some(
      (part) =>
        !part ||
        part.startsWith(".") ||
        part.includes(":") ||
        part.trim() !== part ||
        new TextEncoder().encode(part).byteLength > 240
    ) ||
    !isDocumentFile(path)
  ) {
    throw new Error(
      "파일 경로는 숨김 폴더나 .. 없이 8단계 이내의 Markdown·TXT·HTML 경로로 입력해 주세요."
    );
  }
  if (
    content.length > 200000 ||
    content.includes("\0") ||
    new TextEncoder().encode(content).byteLength > MAX_FILE_BYTES
  ) {
    throw new Error("문서는 20만 자, 2 MiB 이하로 나누어 주세요.");
  }
}

export async function contentVersion(content: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(content)
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

/** Keep the actual local baseline when the server normalizes an uploaded file. */
export async function uploadedSyncBaseline(
  local: string,
  saved: { content: string; version: string }
): Promise<string> {
  return saved.content === local ? saved.version : contentVersion(local);
}

function notFound(error: unknown): boolean {
  return error instanceof Error && error.name === "NotFoundError";
}

export async function relativeFile(
  root: SyncDirectoryHandle,
  path: string
): Promise<LocalFileHandle | undefined> {
  validateCloudFile(path, "");
  const parts = path.split("/");
  let directory = root;
  try {
    for (const part of parts.slice(0, -1))
      directory = await directory.getDirectoryHandle(part);
    return await directory.getFileHandle(parts.at(-1)!);
  } catch (error) {
    if (notFound(error)) return undefined;
    throw error;
  }
}

/** A missing file is a distinct baseline from an existing empty file. */
export async function writeRelativeFile(
  root: SyncDirectoryHandle,
  path: string,
  content: string,
  expectedContent: string | null
): Promise<void> {
  validateCloudFile(path, content);
  let handle = await relativeFile(root, path);
  if (expectedContent === null && handle)
    throw new Error(
      "로컬 파일이 새로 존재합니다. 변경 내용을 다시 비교해 주세요."
    );
  if (expectedContent !== null && !handle)
    throw new Error(
      "로컬 파일이 이동되거나 삭제되었습니다. 다시 비교해 주세요."
    );
  if (!handle) {
    let directory = root;
    const parts = path.split("/");
    for (const part of parts.slice(0, -1))
      directory = await directory.getDirectoryHandle(part, { create: true });
    // Recheck after directory creation, before creating the new leaf.
    if (await relativeFile(root, path))
      throw new Error("로컬 파일이 새로 존재합니다. 다시 비교해 주세요.");
    handle = await directory.getFileHandle(parts.at(-1)!, { create: true });
  }
  await requestWritePermission(handle);
  await writeFileSafely(handle, content, expectedContent ?? "");
}

export async function readRelativeContent(
  root: SyncDirectoryHandle,
  path: string
): Promise<string | null> {
  const handle = await relativeFile(root, path);
  return handle ? (await readFileSnapshot(handle)).content : null;
}
