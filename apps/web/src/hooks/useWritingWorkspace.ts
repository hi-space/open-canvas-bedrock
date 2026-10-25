"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  bindDocumentFile,
  createDocument,
  decideDocumentChanges,
  receiveDiskSnapshot,
  reviseDocument,
} from "@/lib/workspace/documents";
import {
  downloadMarkdown,
  FileConflictError,
  isDocumentFile,
  readFileSnapshot,
  readTextFile,
  requestWritePermission,
  scanDirectory,
  writeFileSafely,
} from "@/lib/workspace/files";
import { createProposal } from "@/lib/workspace/review";
import {
  insertCitation,
  mergeReferences,
  referenceUrl,
  validateProposalReferences,
} from "@/lib/workspace/sources";
import { loadWorkspace, saveWorkspace } from "@/lib/workspace/storage";
import { WELCOME_MARKDOWN } from "@/lib/workspace/welcome";
import type {
  ChangeDecision,
  LocalDirectoryHandle,
  LocalFileHandle,
  SourceReference,
  TextSelection,
  WorkspaceDocument,
  WorkspaceFolder,
  WorkspaceState,
  WritingRequest,
  WritingResponse,
} from "@/lib/workspace/types";

const EMPTY: WorkspaceState = {
  version: 1,
  documents: [],
  activeDocumentId: null,
};

interface FilePickerBrowser {
  showDirectoryPicker?: (options: {
    mode: "readwrite";
    id: string;
  }) => Promise<LocalDirectoryHandle>;
  showSaveFilePicker?: (options: {
    suggestedName: string;
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<LocalFileHandle>;
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "작업을 완료하지 못했습니다. 다시 시도해 주세요.";
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function uniqueName(name: string, documents: WorkspaceDocument[]): string {
  if (!documents.some((document) => document.name === name)) return name;
  const dot = name.lastIndexOf(".");
  const base = dot > 0 ? name.slice(0, dot) : name;
  const extension = dot > 0 ? name.slice(dot) : ".md";
  let index = 2;
  while (
    documents.some(
      (document) => document.name === `${base} (${index})${extension}`
    )
  )
    index++;
  return `${base} (${index})${extension}`;
}

export function useWritingWorkspace() {
  const [state, setState] = useState<WorkspaceState>(EMPTY);
  const stateRef = useRef(state);
  const [ready, setReady] = useState(false);
  const [persistence, setPersistence] = useState<"saving" | "saved" | "error">(
    "saving"
  );
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [directorySupported, setDirectorySupported] = useState(false);
  const [folderPermission, setFolderPermission] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const refreshInProgress = useRef(false);
  const [savingId, setSavingId] = useState<string>();
  const savingRef = useRef(false);
  const [request, setRequest] = useState<{
    documentId: string;
    instruction: string;
    selection?: TextSelection;
  }>();
  const requestController = useRef<AbortController | undefined>(undefined);
  const mayPersist = useRef(false);
  const persistenceQueue = useRef<WorkspaceState | undefined>(undefined);
  const persistenceRunning = useRef(false);
  const mounted = useRef(true);

  const commit = useCallback(
    (update: (previous: WorkspaceState) => WorkspaceState) => {
      const next = update(stateRef.current);
      if (next === stateRef.current) return;
      stateRef.current = next;
      if (mayPersist.current) setPersistence("saving");
      setState(next);
    },
    []
  );

  const updateDocument = useCallback(
    (
      id: string,
      update: (document: WorkspaceDocument) => WorkspaceDocument
    ) => {
      commit((previous) => {
        const document = previous.documents.find((item) => item.id === id);
        if (!document) return previous;
        const next = update(document);
        return next === document
          ? previous
          : {
              ...previous,
              documents: previous.documents.map((item) =>
                item.id === id ? next : item
              ),
            };
      });
    },
    [commit]
  );

  useEffect(() => {
    mounted.current = true;
    setDirectorySupported(
      typeof (window as FilePickerBrowser).showDirectoryPicker === "function"
    );
    let cancelled = false;
    void (async () => {
      try {
        const saved = await loadWorkspace();
        if (cancelled) return;
        const welcome = saved
          ? undefined
          : createDocument("시작하기.md", WELCOME_MARKDOWN);
        commit(
          () =>
            saved ?? {
              version: 1,
              documents: [welcome!],
              activeDocumentId: welcome!.id,
            }
        );
        mayPersist.current = true;
        if (saved?.folder) {
          try {
            const permission = await saved.folder.handle.queryPermission?.({
              mode: "read",
            });
            if (!cancelled) setFolderPermission(permission === "granted");
          } catch {
            if (!cancelled) setFolderPermission(false);
          }
        }
      } catch (failure) {
        if (cancelled) return;
        mayPersist.current = false;
        setPersistence("error");
        setError(
          `브라우저 저장소를 열지 못했습니다. ${errorMessage(failure)} 파일 저장·다운로드는 사용할 수 있습니다.`
        );
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
      mounted.current = false;
      requestController.current?.abort();
    };
  }, [commit]);

  useEffect(() => {
    if (!ready || !mayPersist.current) return;
    persistenceQueue.current = state;
    setPersistence("saving");
    if (persistenceRunning.current) return;
    persistenceRunning.current = true;
    void (async () => {
      try {
        while (persistenceQueue.current) {
          const snapshot = persistenceQueue.current;
          persistenceQueue.current = undefined;
          await saveWorkspace(snapshot);
        }
        if (mounted.current) setPersistence("saved");
      } catch (failure) {
        if (mounted.current) {
          setPersistence("error");
          setError(
            `브라우저에 초안을 저장하지 못했습니다. 파일로 저장하거나 다운로드해 주세요. ${errorMessage(failure)}`
          );
        }
      } finally {
        persistenceRunning.current = false;
      }
    })();
  }, [ready, state]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (persistence !== "saved") {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [persistence]);

  const refreshFolder = useCallback(
    async (manual = false, override?: WorkspaceFolder) => {
      const folder = override ?? stateRef.current.folder;
      if (
        !folder ||
        refreshInProgress.current ||
        (!override && !folderPermission)
      )
        return;
      refreshInProgress.current = true;
      setRefreshing(true);
      try {
        const result = await scanDirectory(folder.handle);
        commit((previous) => {
          if (previous.folder?.id !== folder.id) return previous;
          const byPath = new Map(result.files.map((file) => [file.path, file]));
          let changed = false;
          const documents = previous.documents.map((document) => {
            if (document.folderId !== folder.id) return document;
            const file = byPath.get(document.path);
            if (!file) {
              if (result.complete && !document.missing) {
                changed = true;
                return { ...document, missing: true };
              }
              return document;
            }
            byPath.delete(document.path);
            const next = receiveDiskSnapshot(document, file.snapshot);
            if (next !== document) changed = true;
            return next;
          });
          for (const [path, file] of byPath) {
            documents.push({
              ...createDocument(file.handle.name, file.snapshot.content),
              path,
              folderId: folder.id,
              folderName: folder.name,
              disk: file.snapshot,
              fileHandle: file.handle,
            });
            changed = true;
          }
          if (!changed) return previous;
          return {
            ...previous,
            documents,
            activeDocumentId:
              previous.activeDocumentId ?? documents[0]?.id ?? null,
          };
        });
        if (manual) {
          setNotice(
            result.skipped.length
              ? `${result.files.length}개 파일을 확인했습니다. ${result.skipped.length}개 항목을 건너뛰었습니다: ${result.skipped[0]}`
              : `${result.files.length}개 파일의 변경 사항을 확인했습니다.`
          );
        }
      } catch (failure) {
        if (failure instanceof Error && failure.name === "NotAllowedError")
          setFolderPermission(false);
        setError(
          `폴더를 읽지 못했습니다. 초안은 유지됩니다. ${errorMessage(failure)}`
        );
      } finally {
        refreshInProgress.current = false;
        if (mounted.current) setRefreshing(false);
      }
    },
    [commit, folderPermission]
  );

  useEffect(() => {
    if (!ready) return;
    const checkActiveFile = async () => {
      const current = stateRef.current.documents.find(
        (document) => document.id === stateRef.current.activeDocumentId
      );
      if (
        !current?.fileHandle ||
        savingRef.current ||
        document.visibilityState === "hidden"
      )
        return;
      try {
        const snapshot = await readFileSnapshot(current.fileHandle);
        if (mounted.current)
          updateDocument(current.id, (latest) =>
            receiveDiskSnapshot(latest, snapshot)
          );
      } catch (failure) {
        if (failure instanceof Error && failure.name === "NotFoundError") {
          updateDocument(current.id, (latest) =>
            latest.missing ? latest : { ...latest, missing: true }
          );
        } else if (
          failure instanceof Error &&
          failure.name === "NotAllowedError"
        ) {
          setFolderPermission(false);
        }
      }
    };
    const onFocus = () => {
      void checkActiveFile();
      void refreshFolder();
    };
    const activeTimer = setInterval(() => void checkActiveFile(), 3000);
    const folderTimer = setInterval(() => {
      if (document.visibilityState !== "hidden") void refreshFolder();
    }, 10000);
    window.addEventListener("focus", onFocus);
    void checkActiveFile();
    return () => {
      clearInterval(activeTimer);
      clearInterval(folderTimer);
      window.removeEventListener("focus", onFocus);
    };
  }, [ready, state.activeDocumentId, refreshFolder, updateDocument]);

  const connectFolder = async () => {
    try {
      const browser = window as FilePickerBrowser;
      if (!browser.showDirectoryPicker) {
        setNotice(
          "이 브라우저에서는 파일 가져오기와 다운로드를 이용해 주세요. 폴더 연결은 지원하는 브라우저에서 사용할 수 있습니다."
        );
        return;
      }
      const handle = await browser.showDirectoryPicker({
        mode: "readwrite",
        id: "open-canvas-writing",
      });
      const previous = stateRef.current.folder;
      const same = previous && (await previous.handle.isSameEntry?.(handle));
      const folder = {
        id: same ? previous.id : crypto.randomUUID(),
        name: handle.name,
        handle,
      };
      commit((current) => ({ ...current, folder }));
      setFolderPermission(true);
      await refreshFolder(true, folder);
      commit((current) => {
        const first = current.documents.find(
          (document) => document.folderId === folder.id
        );
        return first ? { ...current, activeDocumentId: first.id } : current;
      });
    } catch (failure) {
      if (!isAbort(failure)) setError(errorMessage(failure));
    }
  };

  const reconnectFolder = async () => {
    const folder = stateRef.current.folder;
    if (!folder) return connectFolder();
    try {
      const permission = await folder.handle.requestPermission?.({
        mode: "readwrite",
      });
      if (permission !== "granted")
        throw new Error("폴더를 다시 연결하려면 접근 권한을 허용해 주세요.");
      setFolderPermission(true);
      await refreshFolder(true, folder);
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };

  const importFiles = async (files: File[]) => {
    const imported: WorkspaceDocument[] = [];
    const failures: string[] = [];
    for (const file of files.slice(0, 200)) {
      if (!isDocumentFile(file.name)) {
        failures.push(`${file.name}: Markdown 또는 TXT 파일을 선택해 주세요.`);
        continue;
      }
      try {
        const content = await readTextFile(file);
        imported.push(
          createDocument(
            uniqueName(file.name, [...stateRef.current.documents, ...imported]),
            content
          )
        );
      } catch (failure) {
        failures.push(errorMessage(failure));
      }
    }
    if (imported.length) {
      commit((previous) => ({
        ...previous,
        documents: [...previous.documents, ...imported],
        activeDocumentId: imported[0].id,
      }));
      setNotice(
        `${imported.length}개 파일을 가져왔습니다. 수정한 파일은 저장하거나 다운로드할 수 있습니다.`
      );
    }
    if (failures.length) setError(failures.join("\n"));
  };

  const newDocument = () => {
    const document = createDocument(
      uniqueName("새 문서.md", stateRef.current.documents),
      ""
    );
    commit((previous) => ({
      ...previous,
      documents: [...previous.documents, document],
      activeDocumentId: document.id,
    }));
  };

  const saveDocument = async (id: string, saveAs = false) => {
    const current = stateRef.current.documents.find(
      (document) => document.id === id
    );
    if (!current || savingRef.current) return;
    savingRef.current = true;
    setSavingId(id);
    try {
      let handle = !saveAs && !current.missing ? current.fileHandle : undefined;
      const newBinding = !handle;
      let expectedContent = current.disk?.content;
      if (handle && current.external)
        throw new FileConflictError(current.external);
      if (!handle) {
        const picker = (window as FilePickerBrowser).showSaveFilePicker;
        if (!picker) {
          downloadMarkdown(current.name, current.content);
          setNotice(
            "파일을 다운로드했습니다. 브라우저 초안은 계속 보관됩니다."
          );
          return;
        }
        handle = await picker({
          suggestedName: current.name,
          types: [
            {
              description: "Markdown 문서",
              accept: { "text/markdown": [".md", ".markdown", ".txt"] },
            },
          ],
        });
        expectedContent = (await readFileSnapshot(handle)).content;
      }
      await requestWritePermission(handle);
      if (expectedContent === undefined)
        throw new Error(
          "파일 상태를 확인하지 못했습니다. 다른 이름으로 저장해 주세요."
        );
      const snapshot = await writeFileSafely(
        handle,
        current.content,
        expectedContent
      );
      const selectedHandle = handle;
      updateDocument(id, (latest) =>
        bindDocumentFile(latest, selectedHandle, snapshot, newBinding)
      );
      setNotice(`${selectedHandle.name} 파일에 저장했습니다.`);
    } catch (failure) {
      if (failure instanceof FileConflictError) {
        updateDocument(id, (latest) =>
          receiveDiskSnapshot(latest, failure.snapshot)
        );
      }
      if (!isAbort(failure)) setError(errorMessage(failure));
    } finally {
      savingRef.current = false;
      if (mounted.current) setSavingId(undefined);
    }
  };

  const propose = async (
    id: string,
    instruction: string,
    selection?: TextSelection,
    model?: string
  ) => {
    const current = stateRef.current.documents.find(
      (document) => document.id === id
    );
    if (!current || requestController.current) return;
    if (!instruction.trim()) {
      setError("어떻게 수정할지 입력해 주세요.");
      return;
    }
    if (current.content.length > 200000) {
      setError(
        "AI 검토는 20만 자 이하의 문서에서 사용할 수 있습니다. 문서를 나누어 주세요."
      );
      return;
    }
    if (
      selection &&
      current.content.slice(selection.from, selection.to) !== selection.text
    ) {
      setError("선택 내용이 달라졌습니다. 문장을 다시 선택해 주세요.");
      return;
    }
    const controller = new AbortController();
    requestController.current = controller;
    setRequest({ documentId: id, instruction, selection });
    setError(undefined);
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 180000);
    try {
      const body: WritingRequest = {
        document: current.content,
        selectedText: selection?.text || undefined,
        instruction,
        model,
        sources: mergeReferences(current.content, current.sources)
          .filter((source) => source.url.length <= 2048)
          .sort(
            (a, b) => Number(!!b.excerpt?.trim()) - Number(!!a.excerpt?.trim())
          )
          .slice(0, 50)
          .map(({ id: sourceId, title, url, excerpt }) => ({
            id: sourceId,
            title: title.slice(0, 500),
            url,
            excerpt,
          })),
      };
      const response = await fetch("/api/writing/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const data = (await response
        .json()
        .catch(() => ({}))) as Partial<WritingResponse> & {
        detail?: string;
        error?: string;
      };
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : data.error ||
                "AI 서버에 연결하지 못했습니다. 서버와 모델 설정을 확인해 주세요."
        );
      if (
        typeof data.replacement !== "string" ||
        typeof data.explanation !== "string"
      ) {
        throw new Error("완전한 수정안을 받지 못했습니다. 다시 요청해 주세요.");
      }
      if (controller.signal.aborted) return;
      const proposal = createProposal(current.content, data.replacement, {
        selection,
        instruction,
        explanation: data.explanation,
      });
      validateProposalReferences(
        current.content,
        proposal.proposedContent,
        current.sources
      );
      if (!proposal.changes.length) {
        setNotice("원문과 동일한 결과입니다. 반영할 변경이 없습니다.");
        return;
      }
      updateDocument(id, (latest) => ({ ...latest, proposal }));
      setNotice(
        `${current.name}의 수정안이 준비되었습니다. 내용을 검토하고 승인해 주세요.`
      );
    } catch (failure) {
      if (timedOut)
        setError(
          "AI 응답 시간이 초과되었습니다. 선택 영역을 줄이거나 다시 요청해 주세요."
        );
      else if (!isAbort(failure)) setError(errorMessage(failure));
    } finally {
      clearTimeout(timeout);
      if (requestController.current === controller) {
        requestController.current = undefined;
        if (mounted.current) setRequest(undefined);
      }
    }
  };

  const decide = (
    id: string,
    changeId: string,
    decision: Exclude<ChangeDecision, "pending">
  ) => {
    try {
      updateDocument(id, (document) =>
        decideDocumentChanges(document, changeId, decision)
      );
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };

  const reviewExternal = (id: string) =>
    updateDocument(id, (document) => {
      if (!document.external) return document;
      return {
        ...document,
        proposal: createProposal(document.content, document.external.content, {
          kind: "external",
          instruction: "외부 파일 변경",
          explanation:
            "연결된 파일에서 발견한 변경입니다. 원하는 부분을 반영하거나 현재 초안을 유지하세요.",
        }),
      };
    });

  const keepDraft = (id: string) =>
    updateDocument(id, (document) => {
      if (!document.external) return document;
      return {
        ...document,
        disk: document.external,
        external: undefined,
        proposal:
          document.proposal?.kind === "external"
            ? undefined
            : document.proposal,
      };
    });

  const addSource = (id: string, source: SourceReference) => {
    const url = referenceUrl(source.url);
    if (!url) {
      setError("올바른 http 또는 https 출처 링크를 입력해 주세요.");
      return;
    }
    updateDocument(id, (document) => ({
      ...document,
      sources: [
        ...document.sources.filter((item) => item.url !== url),
        { ...source, url },
      ],
    }));
  };

  const citeSource = (
    id: string,
    source: SourceReference,
    selection?: TextSelection
  ) => {
    try {
      updateDocument(id, (document) => {
        if (
          selection &&
          document.content.slice(selection.from, selection.to) !==
            selection.text
        ) {
          throw new Error("인용할 문장을 다시 선택해 주세요.");
        }
        return reviseDocument(
          document,
          insertCitation(
            document.content,
            source,
            selection?.to ?? document.content.length
          ),
          "출처 인용 추가"
        );
      });
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };

  return {
    state,
    activeDocument: state.documents.find(
      (document) => document.id === state.activeDocumentId
    ),
    ready,
    persistence,
    error,
    notice,
    directorySupported,
    folderPermission,
    refreshing,
    savingId,
    request,
    setError,
    setNotice,
    selectDocument: (id: string) =>
      commit((previous) => ({ ...previous, activeDocumentId: id })),
    newDocument,
    importFiles,
    connectFolder,
    reconnectFolder,
    refreshFolder,
    saveDocument,
    updateContent: (id: string, content: string) =>
      updateDocument(id, (document) =>
        document.content === content
          ? document
          : { ...document, content, updatedAt: Date.now() }
      ),
    renameDocument: (id: string, name: string) => {
      const trimmed = name.trim();
      if (!trimmed || /[/\\]/.test(trimmed)) return;
      updateDocument(id, (document) =>
        document.fileHandle
          ? document
          : {
              ...document,
              name: isDocumentFile(trimmed) ? trimmed : `${trimmed}.md`,
              path: isDocumentFile(trimmed) ? trimmed : `${trimmed}.md`,
            }
      );
    },
    propose,
    decide,
    reviewExternal,
    keepDraft,
    addSource,
    citeSource,
    cancelRequest: () => requestController.current?.abort(),
    dismissProposal: (id: string) =>
      updateDocument(id, (document) => ({ ...document, proposal: undefined })),
    restoreRevision: (id: string, content: string) =>
      updateDocument(id, (document) =>
        reviseDocument(document, content, "이전 버전 복원")
      ),
    removeSource: (id: string, sourceId: string) =>
      updateDocument(id, (document) => ({
        ...document,
        sources: document.sources.filter((source) => source.id !== sourceId),
      })),
  };
}

export type WritingWorkspaceController = ReturnType<typeof useWritingWorkspace>;
