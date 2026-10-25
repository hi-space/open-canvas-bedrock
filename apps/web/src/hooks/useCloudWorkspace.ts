"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  CloudWorkspaceController,
  isDirty,
  type CloudDraft,
} from "@/lib/workspace/cloud-state";
import { loadCloudDrafts, saveCloudDraft } from "@/lib/workspace/cloud-storage";
import { loadWorkspace } from "@/lib/workspace/storage";
import { isDocumentFile, readTextFile } from "@/lib/workspace/files";
import type { WorkspaceDocument } from "@/lib/workspace/types";

export function useCloudWorkspace() {
  const controller = useMemo(() => new CloudWorkspaceController(), []);
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  );
  const hydrated = useRef(new Set<string>());
  const hydrating = useRef(new Set<string>());
  const revisions = useRef(new Map<string, number>());
  const persisted = useRef(new Map<string, CloudDraft | null>());
  const running = useRef(false);
  const persistenceWanted = useRef(false);
  const failed = useRef(new Set<string>());
  const [legacyDrafts, setLegacyDrafts] = useState<WorkspaceDocument[]>([]);
  const [importing, setImporting] = useState(false);
  const [persistence, setPersistence] = useState<"saved" | "saving" | "error">(
    "saved"
  );

  useEffect(() => {
    if (state.ready && state.activeId) {
      try {
        localStorage.setItem("open-canvas-cloud-project", state.activeId);
      } catch {
        /* Selection still works. */
      }
    }
  }, [state.activeId, state.ready]);

  const selectedPath = state.activeId
    ? state.projects[state.activeId]?.activePath
    : undefined;
  useEffect(() => {
    if (state.ready && state.activeId && selectedPath) {
      try {
        localStorage.setItem(
          `open-canvas-cloud-path:${state.activeId}`,
          selectedPath
        );
      } catch {
        /* Selection still works. */
      }
    }
  }, [state.activeId, state.ready, selectedPath]);

  useEffect(() => {
    let preferred: string | undefined;
    let preferredPath: string | undefined;
    try {
      preferred =
        localStorage.getItem("open-canvas-cloud-project") ?? undefined;
      if (preferred)
        preferredPath =
          localStorage.getItem(`open-canvas-cloud-path:${preferred}`) ??
          undefined;
    } catch {
      /* Storage may be unavailable. */
    }
    void controller.initialize(preferred, preferredPath);
    void loadWorkspace()
      .then((legacy) => {
        setLegacyDrafts(legacy?.documents ?? []);
      })
      .catch(controller.report);
    const interval = setInterval(() => {
      void controller.poll().catch(controller.report);
    }, 2000);
    const focus = () => {
      const id = controller.getSnapshot().activeId;
      if (id) {
        void controller.refresh(id).catch(controller.report);
        const path = controller.getSnapshot().projects[id]?.activePath;
        if (path && controller.getSnapshot().projects[id]?.documents[path])
          void controller.fetchFile(id, path).catch(controller.report);
      }
      void controller.poll().catch(controller.report);
    };
    window.addEventListener("focus", focus);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", focus);
    };
  }, [controller]);

  useEffect(() => {
    const id = state.activeId;
    if (
      !id ||
      !state.projects[id] ||
      hydrated.current.has(id) ||
      hydrating.current.has(id)
    )
      return;
    hydrating.current.add(id);
    void loadCloudDrafts(id)
      .then((stored) => {
        for (const row of stored) {
          const key = `${id}/${row.path}`;
          revisions.current.set(key, row.revision);
          persisted.current.set(key, row.draft);
          if (row.draft) controller.restoreDraft(id, row.path, row.draft);
        }
      })
      .then(() => {
        hydrated.current.add(id);
      })
      .catch((error) => {
        failed.current.add(id);
        setPersistence("error");
        controller.report(error);
      });
  }, [controller, state.activeId, state.projects]);

  useEffect(() => {
    const timer = setTimeout(() => {
      persistenceWanted.current = true;
      if (running.current) return;
      running.current = true;
      void (async () => {
        try {
          while (persistenceWanted.current) {
            persistenceWanted.current = false;
            for (const [id, project] of Object.entries(
              controller.getSnapshot().projects
            )) {
              if (!hydrated.current.has(id) || failed.current.has(id)) continue;
              for (const [path, draft] of Object.entries(project.documents)) {
                const key = `${id}/${path}`;
                const next =
                  isDirty(draft) ||
                  draft.recovery !== undefined ||
                  draft.recoveryCopies?.length
                    ? draft
                    : null;
                if (
                  persisted.current.get(key) === next ||
                  (!next && !persisted.current.has(key))
                )
                  continue;
                setPersistence("saving");
                const revision = await saveCloudDraft(
                  id,
                  path,
                  next,
                  revisions.current.get(key) ?? 0
                );
                revisions.current.set(key, revision);
                persisted.current.set(key, next);
              }
            }
          }
          setPersistence("saved");
        } catch (error) {
          setPersistence("error");
          controller.report(error);
        } finally {
          running.current = false;
        }
      })();
    }, 350);
    return () => clearTimeout(timer);
  }, [controller, state.projects]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (
        Object.values(controller.getSnapshot().projects).some((project) =>
          Object.values(project.documents).some(isDirty)
        )
      ) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [controller]);

  const importFiles = async (files: File[]) => {
    const id = controller.getSnapshot().activeId;
    if (!id) throw new Error("파일을 가져올 프로젝트를 먼저 만들어 주세요.");
    setImporting(true);
    let imported = 0;
    const failures: string[] = [];
    try {
      for (const file of files.slice(0, 200)) {
        try {
          if (!isDocumentFile(file.name))
            throw new Error(
              `${file.name}: Markdown 또는 TXT 파일을 선택해 주세요.`
            );
          const content = await readTextFile(file);
          await controller.createFile(
            id,
            file.webkitRelativePath || file.name,
            content
          );
          imported++;
        } catch (error) {
          failures.push(
            error instanceof Error
              ? `${file.name}: ${error.message}`
              : file.name
          );
        }
      }
      if (imported)
        controller.notify(`${imported}개 파일을 프로젝트에 가져왔습니다.`);
      if (failures.length) throw new Error(failures.join("\n"));
    } finally {
      setImporting(false);
    }
  };

  const importLegacy = async () => {
    const id = controller.getSnapshot().activeId;
    if (!id) throw new Error("가져올 프로젝트를 먼저 만들어 주세요.");
    setImporting(true);
    let imported = 0;
    const failures: string[] = [];
    try {
      for (const draft of legacyDrafts.slice(0, 200)) {
        try {
          const originalPath = draft.path || draft.name;
          let path = originalPath;
          const existing = new Set(
            controller.getSnapshot().projects[id].files.map((file) => file.path)
          );
          for (let number = 2; existing.has(path); number++)
            path = originalPath.replace(/(\.[^.]+)$/, ` (${number})$1`);
          await controller.createFile(id, path, draft.content);
          imported++;
          for (const source of draft.sources) {
            if (
              !controller
                .getSnapshot()
                .projects[id].sources.some((item) => item.url === source.url)
            )
              await controller.addSource(id, source);
          }
        } catch (error) {
          failures.push(
            `${draft.name}: ${error instanceof Error ? error.message : "가져오기 실패"}`
          );
        }
      }
      controller.notify(
        `${imported}개 브라우저 초안을 가져왔습니다. 기존 초안도 보관되어 있습니다.`
      );
      if (failures.length) throw new Error(failures.join("\n"));
      setLegacyDrafts([]);
    } finally {
      setImporting(false);
    }
  };

  return {
    controller,
    state,
    project: state.activeId ? state.projects[state.activeId] : undefined,
    legacyDrafts,
    importing,
    persistence,
    importFiles,
    importLegacy,
  };
}

export type CloudWorkspaceHook = ReturnType<typeof useCloudWorkspace>;
