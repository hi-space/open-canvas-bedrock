import { useState } from "react";
import {
  Check,
  Cloud,
  FilePlus2,
  FileText,
  FolderSync,
  Import,
  LoaderCircle,
  LogOut,
  PanelLeftClose,
  Plus,
  Search,
  Upload,
} from "lucide-react";
import type { CloudWorkspaceHook } from "@/hooks/useCloudWorkspace";
import type { CloudFolderHook } from "@/hooks/useCloudFolder";
import { isDirty } from "@/lib/workspace/cloud-state";
import styles from "./workspace.module.css";
import cloud from "./cloud.module.css";

export function CloudSidebar({
  workspace,
  folder,
  onImport,
  onNewProject,
  onNewFile,
  onSync,
  onClose,
  onSelect,
  authenticationEnabled,
}: {
  workspace: CloudWorkspaceHook;
  folder: CloudFolderHook;
  onImport: () => void;
  onNewProject: () => void;
  onNewFile: () => void;
  onSync: () => void;
  onClose: () => void;
  onSelect: (path: string) => void;
  authenticationEnabled: boolean;
}) {
  const [query, setQuery] = useState("");
  const { controller, state, project } = workspace;
  const files = [...(project?.files ?? [])]
    .filter((file) =>
      file.path.toLocaleLowerCase().includes(query.toLocaleLowerCase())
    )
    .sort((a, b) => a.path.localeCompare(b.path, "ko", { numeric: true }));
  return (
    <aside
      className={`${styles.sidebar} ${cloud.sidebar}`}
      aria-label="프로젝트와 파일"
    >
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
      <div className={cloud.projectPicker}>
        <label htmlFor="cloud-project">프로젝트</label>
        <div>
          <select
            id="cloud-project"
            value={state.activeId ?? ""}
            onChange={(event) => {
              void controller
                .selectWorkspace(event.target.value)
                .catch(controller.report);
            }}
          >
            {!state.workspaces.length && (
              <option value="">프로젝트를 만들어 주세요</option>
            )}
            {state.workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <button
            className={styles.iconButton}
            onClick={onNewProject}
            aria-label="새 프로젝트"
          >
            <Plus size={17} />
          </button>
        </div>
      </div>
      <div className={cloud.sidebarActions}>
        <button
          className={styles.newDocumentButton}
          disabled={!project || workspace.importing}
          onClick={onNewFile}
        >
          <FilePlus2 size={17} /> 새 문서
        </button>
        <button
          className={styles.iconButton}
          disabled={!project || workspace.importing}
          onClick={onImport}
          aria-label="파일 가져오기"
        >
          {workspace.importing ? (
            <LoaderCircle size={17} className={styles.spin} />
          ) : (
            <Upload size={17} />
          )}
        </button>
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
        프로젝트 파일 <span>{project?.files.length ?? 0}</span>
      </div>
      <nav className={styles.fileList} aria-label="파일 목록">
        {files.map((file) => {
          const draft = project?.documents[file.path];
          const dirty = isDirty(draft);
          const pending =
            project?.proposals
              .filter((proposal) => proposal.path === file.path)
              .reduce((sum, proposal) => sum + proposal.pendingCount, 0) ?? 0;
          return (
            <button
              key={file.path}
              className={`${styles.fileItem} ${project?.activePath === file.path ? styles.fileItemActive : ""}`}
              onClick={() => onSelect(file.path)}
              aria-current={
                project?.activePath === file.path ? "page" : undefined
              }
              title={file.path}
            >
              <FileText size={17} />
              <span className={styles.fileName}>
                <strong>{file.name}</strong>
                <small>
                  {draft?.remote
                    ? "클라우드 변경 확인"
                    : dirty
                      ? "저장할 변경 있음"
                      : pending
                        ? `검토할 변경 ${pending}개`
                        : file.path.includes("/")
                          ? file.path
                          : "프로젝트에 저장됨"}
                </small>
              </span>
              {pending ? (
                <span className={styles.countBadge}>{pending}</span>
              ) : dirty ? (
                <span className={styles.alertDot} />
              ) : (
                <Check size={12} />
              )}
            </button>
          );
        })}
        {!files.length && (
          <p className={styles.fileEmpty}>
            {query
              ? "일치하는 파일이 없습니다."
              : "문서를 만들거나 파일을 가져오세요."}
          </p>
        )}
      </nav>
      <div className={cloud.folderEntry}>
        <button onClick={onSync} disabled={!project}>
          <FolderSync size={18} />
          <span>
            <strong>{folder.folder?.name ?? "내 폴더와 연결"}</strong>
            <small>
              {folder.folder
                ? `변경 ${folder.rows.filter((row) => row.status !== "synced").length}개 · 로컬과 클라우드`
                : "로컬 파일과 함께 작업하세요"}
            </small>
          </span>
        </button>
      </div>
      {!!workspace.legacyDrafts.length && (
        <button
          className={cloud.legacyImport}
          disabled={!project || workspace.importing}
          onClick={() => {
            void workspace.importLegacy().catch(controller.report);
          }}
        >
          <Import size={15} />
          <span>
            브라우저 초안 가져오기{" "}
            <small>
              {workspace.legacyDrafts.length}개 · 직접 가져올 때만 업로드
            </small>
          </span>
        </button>
      )}
      <div className={styles.sidebarFooter}>
        <div className={styles.storageStatus}>
          <Cloud size={14} />
          <span>
            {state.storage === "cloud"
              ? "클라우드에 안전하게 보관"
              : "로컬 서버 작업 공간"}
          </span>
        </div>
        {workspace.persistence !== "saved" && (
          <small>
            {workspace.persistence === "saving"
              ? "편집 중인 초안 보관 중…"
              : "브라우저 초안 보관 실패 · 다운로드 가능"}
          </small>
        )}
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
