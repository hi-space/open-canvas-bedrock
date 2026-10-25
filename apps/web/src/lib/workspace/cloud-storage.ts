import type { CloudDraft } from "./cloud-state";
import type { SyncDirectoryHandle } from "./cloud-sync";

export interface StoredCloudDraft {
  workspaceId: string;
  path: string;
  draft: CloudDraft | null;
  revision: number;
}

export interface CloudFolder {
  workspaceId: string;
  id: string;
  name: string;
  handle: SyncDirectoryHandle;
  baselines: Record<string, string>;
}

let opening: Promise<IDBDatabase> | undefined;
function database(): Promise<IDBDatabase> {
  opening ??= new Promise((resolve, reject) => {
    const request = indexedDB.open("open-canvas-cloud", 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("drafts", {
        keyPath: ["workspaceId", "path"],
      });
      request.result.createObjectStore("folders", { keyPath: "workspaceId" });
    };
    request.onerror = () => {
      opening = undefined;
      reject(request.error);
    };
    request.onblocked = () => {
      opening = undefined;
      reject(new Error("다른 Open Canvas 탭을 닫고 다시 열어 주세요."));
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => {
        db.close();
        opening = undefined;
      };
      resolve(db);
    };
  });
  return opening;
}

function value<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function done(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () =>
      reject(transaction.error ?? new Error("브라우저 저장이 중단되었습니다."));
  });
}

export async function loadCloudDrafts(
  workspaceId: string
): Promise<StoredCloudDraft[]> {
  const db = await database();
  const transaction = db.transaction("drafts", "readonly");
  const completed = done(transaction);
  const rows = await value<StoredCloudDraft[]>(
    transaction
      .objectStore("drafts")
      .getAll(IDBKeyRange.bound([workspaceId, ""], [workspaceId, "\uffff"]))
  );
  await completed;
  return rows;
}

export async function saveCloudDraft(
  workspaceId: string,
  path: string,
  draft: CloudDraft | null,
  expectedRevision: number
): Promise<number> {
  const db = await database();
  const transaction = db.transaction("drafts", "readwrite");
  const completed = done(transaction);
  const store = transaction.objectStore("drafts");
  const current = await value<StoredCloudDraft | undefined>(
    store.get([workspaceId, path])
  );
  if ((current?.revision ?? 0) !== expectedRevision) {
    transaction.abort();
    await completed.catch(() => undefined);
    throw new Error(
      "다른 탭에서 초안이 변경되었습니다. 이 탭의 내용은 다운로드한 뒤 다시 열어 주세요."
    );
  }
  const revision = expectedRevision + 1;
  store.put({ workspaceId, path, draft, revision } satisfies StoredCloudDraft);
  await completed;
  return revision;
}

export async function loadCloudFolder(
  workspaceId: string
): Promise<CloudFolder | undefined> {
  const db = await database();
  const transaction = db.transaction("folders", "readonly");
  const completed = done(transaction);
  const result = await value<CloudFolder | undefined>(
    transaction.objectStore("folders").get(workspaceId)
  );
  await completed;
  return result;
}

export async function saveCloudFolder(folder: CloudFolder): Promise<void> {
  const db = await database();
  const transaction = db.transaction("folders", "readwrite");
  const completed = done(transaction);
  transaction.objectStore("folders").put(folder);
  await completed;
}

export async function saveSyncBaselines(
  workspaceId: string,
  folderId: string,
  baselines: Record<string, string>
): Promise<CloudFolder | undefined> {
  const db = await database();
  const transaction = db.transaction("folders", "readwrite");
  const completed = done(transaction);
  const store = transaction.objectStore("folders");
  const current = await value<CloudFolder | undefined>(store.get(workspaceId));
  if (current?.id === folderId) {
    current.baselines = { ...current.baselines, ...baselines };
    store.put(current);
  }
  await completed;
  return current?.id === folderId ? current : undefined;
}
