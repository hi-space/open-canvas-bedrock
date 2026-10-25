"use client";

import { useEffect, useRef, useState } from "react";
import { WorkspaceApiError } from "@/lib/workspace/cloud-api";
import {
  isDirty,
  type CloudWorkspaceController,
} from "@/lib/workspace/cloud-state";
import {
  contentVersion,
  decideSync,
  readRelativeContent,
  safeSyncDirection,
  validateCloudFile,
  writeRelativeFile,
  type SyncDirectoryHandle,
  type SyncStatus,
} from "@/lib/workspace/cloud-sync";
import {
  loadCloudFolder,
  saveCloudFolder,
  saveSyncBaselines,
  type CloudFolder,
} from "@/lib/workspace/cloud-storage";
import { scanDirectory } from "@/lib/workspace/files";
import type { CloudFileSummary } from "@/lib/workspace/cloud-types";

export interface CloudSyncRow {
  path: string;
  localContent: string | null;
  localVersion: string | null;
  remote?: CloudFileSummary;
  status: SyncStatus;
}

interface FolderView {
  workspaceId?: string;
  folder?: CloudFolder;
  permission: boolean;
  rows: CloudSyncRow[];
  skipped: string[];
  scanning: boolean;
  busyPath?: string;
}

export function useCloudFolder(
  controller: CloudWorkspaceController,
  workspaceId?: string
) {
  const [supported, setSupported] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ completed: 0, total: 0 });
  const [view, setView] = useState<FolderView>({
    permission: false,
    rows: [],
    skipped: [],
    scanning: false,
  });
  const viewRef = useRef(view);
  const activeId = useRef(workspaceId);
  const scanRunning = useRef(false);
  const transferRunning = useRef(false);
  const batchRunning = useRef(false);
  const refreshRef = useRef<() => Promise<void>>(async () => undefined);
  viewRef.current = view;
  activeId.current = workspaceId;

  useEffect(() => {
    setSupported("showDirectoryPicker" in window);
    setView({
      workspaceId,
      permission: false,
      rows: [],
      skipped: [],
      scanning: false,
    });
    if (!workspaceId) return;
    let cancelled = false;
    void loadCloudFolder(workspaceId)
      .then(async (folder) => {
        const permission = folder
          ? !folder.handle.queryPermission ||
            (await folder.handle.queryPermission({ mode: "readwrite" })) ===
              "granted"
          : false;
        if (!cancelled)
          setView({
            workspaceId,
            folder,
            permission,
            rows: [],
            skipped: [],
            scanning: false,
          });
      })
      .catch(controller.report);
    return () => {
      cancelled = true;
    };
  }, [controller, workspaceId]);

  const refresh = async (override?: CloudFolder) => {
    const folder = override ?? viewRef.current.folder;
    if (
      !folder ||
      scanRunning.current ||
      (!override && (transferRunning.current || batchRunning.current))
    )
      return;
    scanRunning.current = true;
    if (activeId.current === folder.workspaceId)
      setView((current) => ({ ...current, scanning: true }));
    try {
      const [scan] = await Promise.all([
        scanDirectory(folder.handle),
        controller.refresh(folder.workspaceId),
      ]);
      const project = controller.getSnapshot().projects[folder.workspaceId];
      if (!project) return;
      const local = new Map<string, { content: string; version: string }>();
      const skipped = [...scan.skipped];
      for (const file of scan.files) {
        try {
          validateCloudFile(file.path, file.snapshot.content);
          local.set(file.path, {
            content: file.snapshot.content,
            version: await contentVersion(file.snapshot.content),
          });
        } catch (error) {
          skipped.push(
            `${file.path}: ${error instanceof Error ? error.message : "지원하지 않는 파일"}`
          );
        }
      }
      const remote = new Map(project.files.map((file) => [file.path, file]));
      const paths = new Set([
        ...local.keys(),
        ...remote.keys(),
        ...Object.keys(folder.baselines),
      ]);
      const rows: CloudSyncRow[] = [...paths]
        .sort()
        .map((path) => ({
          path,
          localContent: local.get(path)?.content ?? null,
          localVersion: local.get(path)?.version ?? null,
          remote: remote.get(path),
          status: decideSync(
            local.get(path)?.version ?? null,
            remote.get(path)?.version ?? null,
            folder.baselines[path]
          ),
        }))
        .filter((row) => row.status !== "absent");
      const common = Object.fromEntries(
        rows
          .filter((row) => row.status === "synced" && row.localVersion)
          .map((row) => [row.path, row.localVersion!])
      );
      const updated = await saveSyncBaselines(
        folder.workspaceId,
        folder.id,
        common
      );
      if (
        activeId.current === folder.workspaceId &&
        viewRef.current.folder?.id === folder.id
      )
        setView((current) => ({
          ...current,
          folder: updated ?? folder,
          rows,
          skipped,
          permission: true,
        }));
    } finally {
      scanRunning.current = false;
      if (activeId.current === folder.workspaceId)
        setView((current) => ({ ...current, scanning: false }));
    }
  };

  const connect = async () => {
    if (!workspaceId) throw new Error("프로젝트를 먼저 만들어 주세요.");
    const picker = (
      window as unknown as {
        showDirectoryPicker?: (options: {
          id: string;
          mode: "readwrite";
        }) => Promise<SyncDirectoryHandle>;
      }
    ).showDirectoryPicker;
    if (!picker)
      throw new Error(
        "이 브라우저에서는 파일 가져오기와 다운로드를 이용해 주세요."
      );
    try {
      const handle = await picker({
        id: "open-canvas-cloud",
        mode: "readwrite",
      });
      const previous = await loadCloudFolder(workspaceId);
      const same = previous && (await previous.handle.isSameEntry?.(handle));
      const folder: CloudFolder = {
        workspaceId,
        id: same ? previous.id : crypto.randomUUID(),
        name: handle.name,
        handle,
        baselines: same ? previous.baselines : {},
      };
      await saveCloudFolder(folder);
      if (activeId.current === workspaceId) {
        const next = {
          workspaceId,
          folder,
          permission: true,
          rows: [],
          skipped: [],
          scanning: false,
        };
        viewRef.current = next;
        setView(next);
      }
      await refresh(folder);
    } catch (error) {
      if (!(error instanceof Error && error.name === "AbortError")) throw error;
    }
  };

  const reconnect = async () => {
    const folder = viewRef.current.folder;
    if (!folder) return connect();
    if (
      folder.handle.requestPermission &&
      (await folder.handle.requestPermission({ mode: "readwrite" })) !==
        "granted"
    )
      throw new Error("폴더 접근 권한을 허용해 주세요.");
    if (activeId.current === folder.workspaceId)
      setView((current) => ({ ...current, permission: true }));
    await refresh(folder);
  };

  const performTransfer = async (
    folder: CloudFolder,
    row: CloudSyncRow,
    direction: "upload" | "download",
    refreshAfter = true
  ) => {
    if (transferRunning.current) return;
    const id = folder.workspaceId;
    if (isDirty(controller.getSnapshot().projects[id]?.documents[row.path]))
      throw new Error(
        "편집기에서 수정한 내용을 먼저 저장한 뒤 동기화해 주세요."
      );
    transferRunning.current = true;
    if (activeId.current === id)
      setView((current) => ({ ...current, busyPath: row.path }));
    try {
      const local = await readRelativeContent(folder.handle, row.path);
      if (local !== row.localContent)
        throw new Error(
          "비교 이후 로컬 파일이 변경되었습니다. 다시 비교해 주세요."
        );
      const remote = await controller.api
        .file(id, row.path)
        .catch((error: unknown) => {
          if (error instanceof WorkspaceApiError && error.status === 404)
            return undefined;
          throw error;
        });
      if ((remote?.version ?? null) !== (row.remote?.version ?? null))
        throw new Error(
          "비교 이후 클라우드 파일이 변경되었습니다. 다시 비교해 주세요."
        );
      let version: string;
      if (direction === "upload") {
        if (local === null) throw new Error("업로드할 로컬 파일이 없습니다.");
        const saved = await controller.putFile(
          id,
          row.path,
          local,
          remote?.version ?? null
        );
        version = saved.version;
      } else {
        if (!remote) throw new Error("다운로드할 클라우드 파일이 없습니다.");
        await writeRelativeFile(folder.handle, row.path, remote.content, local);
        version = remote.version;
      }
      const updated = await saveSyncBaselines(id, folder.id, {
        [row.path]: version,
      });
      if (activeId.current === id && viewRef.current.folder?.id === folder.id) {
        const next = { ...viewRef.current, folder: updated ?? folder };
        viewRef.current = next;
        setView(next);
      }
      if (refreshAfter) {
        controller.notify(
          `${row.path} ${direction === "upload" ? "업로드" : "다운로드"} 완료`
        );
        await refresh(updated ?? folder);
      }
    } finally {
      transferRunning.current = false;
      if (activeId.current === id)
        setView((current) => ({ ...current, busyPath: undefined }));
    }
  };

  const transfer = async (
    row: CloudSyncRow,
    direction: "upload" | "download"
  ) => {
    const folder = viewRef.current.folder;
    if (!folder || batchRunning.current) return;
    await performTransfer(folder, row, direction);
  };

  const syncSafe = async () => {
    const folder = viewRef.current.folder;
    if (
      !folder ||
      batchRunning.current ||
      transferRunning.current ||
      scanRunning.current
    )
      return;
    const rows = viewRef.current.rows.filter((row) =>
      safeSyncDirection(row.status)
    );
    if (!rows.length) return;
    batchRunning.current = true;
    setSyncing(true);
    setSyncProgress({ completed: 0, total: rows.length });
    const failures: string[] = [];
    let completed = 0;
    try {
      for (const row of rows) {
        try {
          // The folder and project are captured once for the entire batch.
          await performTransfer(
            folder,
            row,
            safeSyncDirection(row.status)!,
            false
          );
          completed++;
          setSyncProgress({ completed, total: rows.length });
        } catch (error) {
          failures.push(
            `${row.path}: ${error instanceof Error ? error.message : "동기화 실패"}`
          );
        }
      }
      const latest = await loadCloudFolder(folder.workspaceId);
      await refresh(latest?.id === folder.id ? latest : folder);
      controller.notify(
        `${completed}개 파일을 동기화했습니다. 충돌과 삭제 항목은 별도로 확인해 주세요.`
      );
      if (failures.length) throw new Error(failures.join("\n"));
    } finally {
      batchRunning.current = false;
      setSyncing(false);
    }
  };

  refreshRef.current = () => refresh();
  useEffect(() => {
    const check = () => {
      if (document.visibilityState !== "hidden" && viewRef.current.permission)
        void refreshRef.current().catch(controller.report);
    };
    const interval = setInterval(check, 10000);
    window.addEventListener("focus", check);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", check);
    };
  }, [controller]);
  const connectedFolderId = view.folder?.id;
  useEffect(() => {
    if (connectedFolderId && view.permission)
      void refreshRef.current().catch(controller.report);
  }, [controller, connectedFolderId, view.permission]);

  return {
    ...view,
    supported,
    connect,
    reconnect,
    refresh,
    transfer,
    syncSafe,
    syncing,
    syncProgress,
  };
}

export type CloudFolderHook = ReturnType<typeof useCloudFolder>;
