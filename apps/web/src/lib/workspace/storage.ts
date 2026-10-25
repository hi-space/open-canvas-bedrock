import type { WorkspaceDocument, WorkspaceState } from "./types";

type StoredMetadata = Omit<WorkspaceState, "documents"> & {
  documentIds: string[];
  revision?: number;
};
let databasePromise: Promise<IDBDatabase> | undefined;
let storedDocuments = new Map<string, WorkspaceDocument>();
let storedMetadata: StoredMetadata | undefined;
let storedRevision = 0;

function database(): Promise<IDBDatabase> {
  databasePromise ??= new Promise((resolve, reject) => {
    const request = indexedDB.open("open-canvas-writing", 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("documents", { keyPath: "id" });
      request.result.createObjectStore("metadata");
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => {
        db.close();
        databasePromise = undefined;
      };
      resolve(db);
    };
    request.onerror = () => {
      databasePromise = undefined;
      reject(request.error);
    };
    request.onblocked = () => {
      databasePromise = undefined;
      reject(new Error("다른 Open Canvas 탭을 닫고 다시 열어 주세요."));
    };
  });
  return databasePromise;
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () =>
      reject(transaction.error ?? new Error("저장이 중단되었습니다."));
  });
}

function requestValue<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function loadWorkspace(): Promise<WorkspaceState | undefined> {
  const db = await database();
  const transaction = db.transaction(["documents", "metadata"], "readonly");
  const done = transactionDone(transaction);
  const [metadata, documents] = await Promise.all([
    requestValue<StoredMetadata | undefined>(
      transaction.objectStore("metadata").get("current")
    ),
    requestValue<WorkspaceDocument[]>(
      transaction.objectStore("documents").getAll()
    ),
  ]);
  await done;
  if (!metadata) return undefined;
  if (
    metadata.version !== 1 ||
    !Array.isArray(metadata.documentIds) ||
    documents.some(
      (document) =>
        typeof document.id !== "string" ||
        typeof document.content !== "string" ||
        typeof document.name !== "string" ||
        !Array.isArray(document.revisions) ||
        !Array.isArray(document.sources)
    )
  ) {
    throw new Error(
      "저장된 작업 공간을 읽지 못했습니다. 기존 데이터는 보존되어 있습니다."
    );
  }
  const byId = new Map(documents.map((document) => [document.id, document]));
  const ordered = metadata.documentIds.map((id) => byId.get(id));
  if (ordered.some((document) => !document)) {
    throw new Error(
      "문서 목록을 복구하지 못했습니다. 기존 데이터는 보존되어 있습니다."
    );
  }
  storedDocuments = byId;
  storedMetadata = metadata;
  storedRevision = metadata.revision ?? 0;
  return {
    version: 1,
    documents: ordered as WorkspaceDocument[],
    activeDocumentId: metadata.activeDocumentId,
    folder: metadata.folder,
  };
}

export async function saveWorkspace(state: WorkspaceState): Promise<void> {
  const nextDocuments = new Map(
    state.documents.map((document) => [document.id, document])
  );
  const changedDocuments = state.documents.filter(
    (document) => storedDocuments.get(document.id) !== document
  );
  const deletedIds = [...storedDocuments.keys()].filter(
    (id) => !nextDocuments.has(id)
  );
  const sameMetadata =
    storedMetadata &&
    storedMetadata.activeDocumentId === state.activeDocumentId &&
    storedMetadata.folder?.id === state.folder?.id &&
    storedMetadata.documentIds.length === state.documents.length &&
    storedMetadata.documentIds.every(
      (id, index) => state.documents[index].id === id
    );
  if (!changedDocuments.length && !deletedIds.length && sameMetadata) return;
  const db = await database();
  const transaction = db.transaction(["documents", "metadata"], "readwrite");
  const done = transactionDone(transaction);
  const metadataStore = transaction.objectStore("metadata");
  const latest = await requestValue<StoredMetadata | undefined>(
    metadataStore.get("current")
  );
  if ((latest?.revision ?? 0) !== storedRevision) {
    transaction.abort();
    await done.catch(() => undefined);
    throw new Error(
      "다른 탭에서 작업 공간이 변경되었습니다. 이 탭의 초안은 다운로드한 뒤 다시 열어 주세요. 다른 탭의 문서는 덮어쓰지 않았습니다."
    );
  }
  const documentStore = transaction.objectStore("documents");
  // Only clone changed documents: a keystroke must not serialize the whole folder.
  for (const document of changedDocuments) documentStore.put(document);
  for (const id of deletedIds) documentStore.delete(id);
  const metadata: StoredMetadata = {
    version: 1,
    revision: storedRevision + 1,
    documentIds: state.documents.map((document) => document.id),
    activeDocumentId: state.activeDocumentId,
    folder: state.folder,
  };
  metadataStore.put(metadata, "current");
  await done;
  storedDocuments = nextDocuments;
  storedMetadata = metadata;
  storedRevision = metadata.revision!;
}
