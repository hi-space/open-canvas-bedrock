import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Check,
  FolderSync,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import type { CloudFolderHook, CloudSyncRow } from "@/hooks/useCloudFolder";
import type { CloudWorkspaceController } from "@/lib/workspace/cloud-state";
import type { SyncStatus } from "@/lib/workspace/cloud-sync";
import styles from "./workspace.module.css";
import cloud from "./cloud.module.css";

const labels: Record<SyncStatus, string> = {
  synced: "동일한 내용",
  upload: "로컬에 새 변경",
  download: "클라우드에 새 변경",
  conflict: "양쪽 내용 비교 필요",
  "local-deleted": "로컬 파일 없음 · 복원 가능",
  "remote-deleted": "클라우드 파일 없음 · 복원 가능",
  absent: "양쪽 파일 없음",
};

function SyncFile({
  row,
  folder,
  controller,
}: {
  row: CloudSyncRow;
  folder: CloudFolderHook;
  controller: CloudWorkspaceController;
}) {
  const [expanded, setExpanded] = useState(false);
  const [remote, setRemote] = useState<string>();
  const [error, setError] = useState<string>();
  const remoteVersion = row.remote?.version;
  useEffect(() => {
    if (!expanded || !remoteVersion || !folder.workspaceId) return;
    let cancelled = false;
    setRemote(undefined);
    setError(undefined);
    void controller.api
      .file(folder.workspaceId, row.path)
      .then((file) => {
        if (!cancelled) {
          if (file.version !== remoteVersion)
            setError("클라우드가 변경되었습니다. 다시 비교해 주세요.");
          else setRemote(file.content);
        }
      })
      .catch((failure: unknown) => {
        if (!cancelled)
          setError(
            failure instanceof Error
              ? failure.message
              : "파일을 읽지 못했습니다."
          );
      });
    return () => {
      cancelled = true;
    };
  }, [controller, expanded, folder.workspaceId, row.path, remoteVersion]);
  const busy = !!folder.busyPath || folder.scanning || folder.syncing;
  return (
    <article
      className={`${cloud.syncFile} ${row.status === "conflict" ? cloud.syncConflict : ""}`}
    >
      <div>
        <strong>{row.path}</strong>
        <span>{labels[row.status]}</span>
      </div>
      {row.status === "synced" ? (
        <p className={cloud.syncDone}>
          <Check size={14} /> 마지막 비교에서 내용이 같습니다.
        </p>
      ) : (
        <>
          <button
            className={styles.textButton}
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "비교 닫기" : "내용 비교"}
          </button>
          {expanded && (
            <div className={cloud.syncComparison}>
              <label>
                로컬 파일<pre>{row.localContent ?? "(파일 없음)"}</pre>
              </label>
              <label>
                클라우드 파일
                <pre>
                  {row.remote ? (remote ?? "불러오는 중…") : "(파일 없음)"}
                </pre>
              </label>
              {error && (
                <p role="alert" className={styles.fieldError}>
                  {error}
                </p>
              )}
            </div>
          )}
          {(row.status !== "conflict" || expanded) && (
            <div className={cloud.syncActions}>
              {row.localContent !== null && (
                <button
                  className={styles.secondaryButton}
                  disabled={busy || !!error}
                  onClick={() => {
                    void folder
                      .transfer(row, "upload")
                      .catch(controller.report);
                  }}
                >
                  <ArrowUpFromLine size={13} />
                  {row.status === "remote-deleted"
                    ? "클라우드에 복원"
                    : "로컬 내용 업로드"}
                </button>
              )}
              {row.remote && (
                <button
                  className={styles.secondaryButton}
                  disabled={busy || !!error}
                  onClick={() => {
                    void folder
                      .transfer(row, "download")
                      .catch(controller.report);
                  }}
                >
                  <ArrowDownToLine size={13} />
                  {row.status === "local-deleted"
                    ? "로컬 파일 복원"
                    : "클라우드 내용 다운로드"}
                </button>
              )}
            </div>
          )}
          {row.status === "conflict" && (
            <p className={styles.fieldHint}>
              선택한 내용으로 반대쪽 파일을 저장합니다. 비교 이후 변경이
              발견되면 중단합니다.
            </p>
          )}
          {folder.busyPath === row.path && (
            <p aria-live="polite">
              <LoaderCircle size={13} className={styles.spin} /> 파일을 저장하는
              중…
            </p>
          )}
        </>
      )}
    </article>
  );
}

export function CloudFolderPanel({
  folder,
  controller,
  onImport,
}: {
  folder: CloudFolderHook;
  controller: CloudWorkspaceController;
  onImport: () => void;
}) {
  const safeCount = folder.rows.filter(
    (row) => row.status === "upload" || row.status === "download"
  ).length;
  const conflictCount = folder.rows.filter(
    (row) => row.status === "conflict" || row.status.endsWith("-deleted")
  ).length;
  return (
    <div className={cloud.folderPanel}>
      <div className={styles.panelIntro}>
        <FolderSync size={23} />
        <h3>내 폴더와 함께 쓰세요.</h3>
        <p>
          로컬·클라우드의 변경을 자동으로 확인합니다. 한쪽에서만 바뀐 파일은 한
          번에 맞추고, 양쪽이 바뀐 파일은 내용을 비교해 주세요.
        </p>
      </div>
      {!folder.supported && (
        <p className={styles.warningBox}>
          폴더 연결을 지원하지 않는 브라우저입니다. 파일 가져오기와 문서
          다운로드를 사용할 수 있어요.
        </p>
      )}
      <div className={cloud.syncActions}>
        {folder.supported ? (
          <button
            className={styles.acceptButton}
            disabled={folder.scanning || !!folder.busyPath || folder.syncing}
            onClick={() => {
              void (
                folder.folder && !folder.permission
                  ? folder.reconnect()
                  : folder.connect()
              ).catch(controller.report);
            }}
          >
            {folder.folder && !folder.permission
              ? "폴더 접근 다시 허용"
              : folder.folder
                ? "다른 폴더 연결"
                : "폴더 연결"}
          </button>
        ) : (
          <button className={styles.acceptButton} onClick={onImport}>
            파일 가져오기
          </button>
        )}
        {folder.folder && folder.permission && (
          <button
            className={styles.secondaryButton}
            disabled={folder.scanning || !!folder.busyPath || folder.syncing}
            onClick={() => {
              void folder.refresh().catch(controller.report);
            }}
          >
            <RefreshCw
              size={14}
              className={folder.scanning ? styles.spin : undefined}
            />
            {folder.scanning ? "비교 중…" : "변경 비교"}
          </button>
        )}
      </div>
      {folder.folder && folder.permission && (
        <div className={cloud.batchSync}>
          <button
            className={styles.acceptButton}
            disabled={
              !safeCount ||
              folder.scanning ||
              !!folder.busyPath ||
              folder.syncing
            }
            onClick={() => {
              void folder.syncSafe().catch(controller.report);
            }}
          >
            {folder.syncing ? (
              <LoaderCircle className={styles.spin} size={15} />
            ) : (
              <FolderSync size={15} />
            )}
            {folder.syncing
              ? `${folder.syncProgress.completed}/${folder.syncProgress.total}개 동기화 중…`
              : `안전한 변경 모두 반영 (${safeCount})`}
          </button>
          <small>
            {safeCount}개 동기화 가능 · {conflictCount}개 직접 확인
          </small>
        </div>
      )}
      {folder.folder && (
        <p className={cloud.connectedFolder}>
          <span className={styles.statusDot} /> {folder.folder.name}
          <small>이 프로젝트에 연결됨</small>
        </p>
      )}
      <p className={styles.fieldHint}>
        폴더 연결만으로 파일을 업로드하지 않습니다. 삭제는 반대쪽에 자동으로
        반영하지 않습니다. Markdown·TXT·HTML, 파일당 20만 자·2 MiB까지
        지원합니다.
      </p>
      {!!folder.skipped.length && (
        <details className={styles.warningBox}>
          <summary>읽지 못한 항목 {folder.skipped.length}개</summary>
          <p>읽지 못한 파일은 원본을 확인한 뒤 다시 비교해 주세요.</p>
          <ul>
            {folder.skipped.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </details>
      )}
      <div className={cloud.syncFiles}>
        {[...folder.rows]
          .sort(
            (a, b) =>
              Number(a.status === "synced") - Number(b.status === "synced")
          )
          .map((row) => (
            <SyncFile
              key={`${folder.folder?.id}/${row.path}`}
              row={row}
              folder={folder}
              controller={controller}
            />
          ))}
      </div>
      {folder.folder && !folder.scanning && !folder.rows.length && (
        <p className={styles.emptyHint}>
          변경 비교를 누르면 프로젝트 파일과 로컬 파일을 함께 확인할 수
          있습니다.
        </p>
      )}
    </div>
  );
}
