import type {
  DiskSnapshot,
  LocalDirectoryHandle,
  LocalFileHandle,
} from "./types";

export const MAX_FILE_BYTES = 2 * 1024 * 1024;
export const MAX_DIRECTORY_FILES = 200;
const IGNORED_DIRECTORIES = new Set([
  "node_modules",
  "dist",
  "build",
  "coverage",
  "vendor",
]);

export class FileConflictError extends Error {
  snapshot: DiskSnapshot;

  constructor(snapshot: DiskSnapshot) {
    super(
      "파일이 다른 곳에서 변경되었습니다. 변경 내용을 검토한 뒤 다시 저장해 주세요."
    );
    this.name = "FileConflictError";
    this.snapshot = snapshot;
  }
}

export function isDocumentFile(name: string): boolean {
  return /\.(md|markdown|txt)$/i.test(name);
}

export async function readTextFile(file: File): Promise<string> {
  if (file.size > MAX_FILE_BYTES) {
    throw new Error(`${file.name}: 2MB 이하의 텍스트 파일을 열어 주세요.`);
  }
  try {
    // Preserve a UTF-8 BOM and CRLFs; File.text() strips the BOM.
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
      await file.arrayBuffer()
    );
  } catch {
    throw new Error(`${file.name}: UTF-8로 저장된 텍스트 파일을 열어 주세요.`);
  }
}

export async function readFileSnapshot(
  handle: LocalFileHandle
): Promise<DiskSnapshot> {
  const file = await handle.getFile();
  return { content: await readTextFile(file), modifiedAt: file.lastModified };
}

export async function writeFileSafely(
  handle: LocalFileHandle,
  content: string,
  expectedContent: string
): Promise<DiskSnapshot> {
  if (new TextEncoder().encode(content).byteLength > MAX_FILE_BYTES) {
    throw new Error(
      "연결 파일 저장은 2MB까지 지원합니다. 큰 문서는 다운로드해 주세요."
    );
  }
  const current = await readFileSnapshot(handle);
  if (current.content !== expectedContent) throw new FileConflictError(current);
  const writable = await handle.createWritable();
  try {
    const beforeWrite = await readFileSnapshot(handle);
    if (beforeWrite.content !== expectedContent)
      throw new FileConflictError(beforeWrite);
    await writable.write(content);
    const beforeCommit = await readFileSnapshot(handle);
    if (beforeCommit.content !== expectedContent)
      throw new FileConflictError(beforeCommit);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => undefined);
    throw error;
  }
  const saved = await readFileSnapshot(handle);
  if (saved.content !== content) throw new FileConflictError(saved);
  return saved;
}

export async function scanDirectory(root: LocalDirectoryHandle): Promise<{
  files: { path: string; handle: LocalFileHandle; snapshot: DiskSnapshot }[];
  skipped: string[];
  complete: boolean;
}> {
  const files: {
    path: string;
    handle: LocalFileHandle;
    snapshot: DiskSnapshot;
  }[] = [];
  const skipped: string[] = [];
  let visited = 0;
  let complete = true;

  async function walk(
    directory: LocalDirectoryHandle,
    prefix: string,
    depth: number
  ) {
    if (depth > 8) {
      skipped.push(`${prefix}: 하위 폴더 깊이 제한`);
      complete = false;
      return;
    }
    for await (const entry of directory.values()) {
      visited++;
      if (files.length >= MAX_DIRECTORY_FILES || visited > 4000) {
        skipped.push(
          "파일 탐색 범위 제한에 도달했습니다. 더 작은 폴더를 선택해 주세요."
        );
        complete = false;
        return;
      }
      if (entry.name.startsWith(".")) continue;
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.kind === "directory") {
        if (!IGNORED_DIRECTORIES.has(entry.name))
          await walk(entry, path, depth + 1);
      } else if (isDocumentFile(entry.name)) {
        try {
          files.push({
            path,
            handle: entry,
            snapshot: await readFileSnapshot(entry),
          });
        } catch (error) {
          skipped.push(
            error instanceof Error ? error.message : `${path}: 읽기 실패`
          );
          complete = false;
        }
      }
    }
  }
  await walk(root, "", 0);
  files.sort((a, b) => a.path.localeCompare(b.path, "ko", { numeric: true }));
  return { files, skipped, complete };
}

export async function requestWritePermission(
  handle: LocalFileHandle
): Promise<void> {
  if (!handle.queryPermission || !handle.requestPermission) return;
  const options = { mode: "readwrite" as const };
  if ((await handle.queryPermission(options)) === "granted") return;
  if ((await handle.requestPermission(options)) !== "granted") {
    throw new Error(
      "파일 저장 권한이 필요합니다. 권한을 허용하거나 다운로드해 주세요."
    );
  }
}

export function downloadMarkdown(name: string, content: string): void {
  const url = URL.createObjectURL(
    new Blob([content], { type: "text/markdown;charset=utf-8" })
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = isDocumentFile(name) ? name : `${name}.md`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
