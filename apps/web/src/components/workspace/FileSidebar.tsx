import { useState } from "react";
import {
  Check,
  FilePlus2,
  FileText,
  FolderOpen,
  Import,
  LoaderCircle,
  LogOut,
  PanelLeftClose,
  RefreshCw,
  Search,
} from "lucide-react";
import type { WritingWorkspaceController } from "@/hooks/useWritingWorkspace";
import styles from "./workspace.module.css";

export function FileSidebar({
  workspace,
  onImport,
  onClose,
  onSelect,
  authenticationEnabled = false,
}: {
  workspace: WritingWorkspaceController;
  onImport: () => void;
  onClose: () => void;
  onSelect: (id: string) => void;
  authenticationEnabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const documents = workspace.state.documents.filter((document) =>
    `${document.name} ${document.path}`
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase())
  );

  return (
    <aside className={styles.sidebar} aria-label="문서 파일">
      <div className={styles.sidebarBrand}>
        <div className={styles.brandMark}>
          <span />
          <span />
          <span />
        </div>
        <div>
          <strong>
            open canvas<span>.</span>
          </strong>
          <small>생각을 다듬는 작업실</small>
        </div>
        <button
          className={`${styles.iconButton} ${styles.mobileOnly}`}
          onClick={onClose}
          aria-label="파일 목록 닫기"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      <button
        className={styles.newDocumentButton}
        onClick={workspace.newDocument}
      >
        <FilePlus2 size={17} /> 새 문서 <span>＋</span>
      </button>

      <div className={styles.folderCard}>
        <div className={styles.folderCardTitle}>
          <FolderOpen size={17} />
          <span>{workspace.state.folder?.name ?? "내 파일과 함께 쓰기"}</span>
          {workspace.state.folder && (
            <button
              className={styles.iconButton}
              disabled={workspace.refreshing || !workspace.folderPermission}
              onClick={() => void workspace.refreshFolder(true)}
              aria-label="폴더 변경 사항 새로고침"
            >
              <RefreshCw
                size={14}
                className={workspace.refreshing ? styles.spin : undefined}
              />
            </button>
          )}
        </div>
        <p>
          {workspace.state.folder
            ? workspace.folderPermission
              ? "외부 변경을 자동으로 확인합니다."
              : "폴더 접근 권한을 다시 허용해 주세요."
            : "로컬 도구에서 쓰던 Markdown을\n이곳에서 이어서 다듬으세요."}
        </p>
        <div className={styles.folderActions}>
          <button
            onClick={() =>
              void (workspace.state.folder && !workspace.folderPermission
                ? workspace.reconnectFolder()
                : workspace.directorySupported
                  ? workspace.connectFolder()
                  : onImport())
            }
          >
            {workspace.state.folder && !workspace.folderPermission
              ? "다시 연결"
              : workspace.directorySupported
                ? "폴더 연결"
                : "파일 가져오기"}
          </button>
          {workspace.directorySupported && (
            <button onClick={onImport}>
              <Import size={13} /> 가져오기
            </button>
          )}
        </div>
      </div>

      <label className={styles.searchField}>
        <Search size={15} aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="파일 찾기"
          aria-label="파일 찾기"
        />
      </label>

      <div className={styles.sectionLabel}>
        문서 <span>{workspace.state.documents.length}</span>
      </div>
      <nav className={styles.fileList}>
        {documents.map((document) => {
          const active = document.id === workspace.state.activeDocumentId;
          const external = !!document.external;
          const dirty = document.content !== document.disk?.content;
          const pending =
            document.proposal?.changes.filter(
              (change) => change.decision === "pending"
            ).length ?? 0;
          return (
            <button
              key={document.id}
              className={`${styles.fileItem} ${active ? styles.fileItemActive : ""}`}
              onClick={() => onSelect(document.id)}
              aria-current={active ? "page" : undefined}
              title={`${document.folderName ? document.folderName + "/" : ""}${document.path}`}
            >
              <FileText size={17} />
              <span className={styles.fileName}>
                <strong>{document.name}</strong>
                <small>
                  {external
                    ? "외부 변경 발견"
                    : document.missing
                      ? "원본 파일 없음 · 초안 보관"
                      : pending
                        ? `검토할 변경 ${pending}개`
                        : document.fileHandle
                          ? dirty
                            ? "저장할 변경 있음"
                            : document.path
                          : "브라우저 초안"}
                </small>
              </span>
              {external ? (
                <span className={styles.alertDot} />
              ) : pending ? (
                <span className={styles.countBadge}>{pending}</span>
              ) : document.fileHandle && !dirty ? (
                <Check size={13} />
              ) : (
                <span className={styles.draftDot} />
              )}
            </button>
          );
        })}
        {!documents.length && (
          <p className={styles.fileEmpty}>일치하는 파일이 없습니다.</p>
        )}
      </nav>

      <div className={styles.sidebarFooter}>
        <div className={styles.storageStatus}>
          {workspace.persistence === "saving" ? (
            <LoaderCircle size={13} className={styles.spin} />
          ) : (
            <span
              className={
                workspace.persistence === "error"
                  ? styles.alertDot
                  : styles.statusDot
              }
            />
          )}
          <span>
            {workspace.persistence === "saved"
              ? "이 브라우저에 초안 보관 중"
              : workspace.persistence === "saving"
                ? "초안 보관 중…"
                : "초안 보관 실패 · 파일로 저장"}
          </span>
        </div>
        {authenticationEnabled && (
          <form method="post" action="/auth/logout">
            <button type="submit" className={styles.textButton}>
              로그아웃 <LogOut size={14} />
            </button>
          </form>
        )}
      </div>
    </aside>
  );
}
