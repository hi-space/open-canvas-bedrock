"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertCircle,
  ArrowDownToLine,
  BookOpen,
  Check,
  ChevronRight,
  Cloud,
  Code2,
  FileText,
  LoaderCircle,
  Maximize2,
  Minus,
  PanelLeft,
  PanelLeftClose,
  PanelRight,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useCloudWorkspace } from "@/hooks/useCloudWorkspace";
import { useCloudFolder } from "@/hooks/useCloudFolder";
import { useWorkspaceModels } from "@/hooks/useWorkspaceModels";
import { useReviewFocus } from "@/hooks/useReviewFocus";
import useLocalStorage from "@/hooks/useLocalStorage";
import { isDirty } from "@/lib/workspace/cloud-state";
import { ownsSelection } from "@/lib/workspace/cloud-intent";
import {
  downloadDocument,
  isDocumentFile,
  isHtmlFile,
} from "@/lib/workspace/files";
import { EMPTY_HTML_DOCUMENT } from "@/lib/workspace/html-template";
import { standaloneHtml } from "@/lib/workspace/html-assets";
import { editingInstruction } from "@/lib/workspace/review-policy";
import type { TextSelection } from "@/lib/workspace/types";
import { DocumentPreview } from "./DocumentPreview";
import { HtmlPreview } from "./HtmlPreview";
import { ReviewFocusToolbar } from "./ReviewFocusToolbar";
import { CloudSidebar } from "./CloudSidebar";
import {
  CloudInspector,
  workspaceDocument,
  type CloudInspectorTab,
} from "./CloudInspector";
import { LegacyThread } from "./LegacyThread";
import styles from "./workspace.module.css";
import cloud from "./cloud.module.css";

const MarkdownEditor = dynamic(() => import("./MarkdownEditor"), {
  ssr: false,
  loading: () => <div className={styles.editorLoading}>편집기를 여는 중…</div>,
});

function CreateItem({
  kind,
  onCreate,
  onClose,
}: {
  kind: "project" | "file";
  onCreate: (name: string) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState(kind === "file" ? "새 문서.md" : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <dialog
      ref={dialog}
      className={cloud.modal}
      onCancel={onClose}
      aria-labelledby="create-item-title"
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          void onCreate(name)
            .then(onClose)
            .catch((failure: unknown) => {
              setError(
                failure instanceof Error
                  ? failure.message
                  : "만들지 못했습니다."
              );
            })
            .finally(() => setBusy(false));
        }}
      >
        <header>
          <div>
            <span className={cloud.eyebrow}>
              {kind === "project" ? "A PLACE FOR YOUR IDEAS" : "A FRESH PAGE"}
            </span>
            <h2 id="create-item-title">
              {kind === "project" ? "새 프로젝트" : "새 문서"}
            </h2>
          </div>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onClose}
            aria-label="만들기 닫기"
          >
            <X size={19} />
          </button>
        </header>
        {kind === "file" && (
          <label>
            문서 형식
            <select
              value={isHtmlFile(name) ? "html" : "markdown"}
              onChange={(event) => {
                const extension =
                  event.target.value === "html" ? ".html" : ".md";
                setName(
                  (current) =>
                    current.replace(/\.(md|markdown|txt|html?)$/i, "") +
                    extension
                );
              }}
            >
              <option value="markdown">Markdown 문서</option>
              <option value="html">HTML 페이지</option>
            </select>
          </label>
        )}
        <label>
          {kind === "project" ? "프로젝트 이름" : "파일 경로"}
          <input
            ref={input}
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={kind === "project" ? 100 : 1024}
            placeholder={
              kind === "project"
                ? "예: 나의 기술 블로그"
                : "예: notes/article.md"
            }
          />
        </label>
        <p>
          {kind === "project"
            ? "관련 문서와 대화, 참고 자료를 함께 보관합니다."
            : "하위 폴더를 포함한 Markdown·TXT·HTML 경로를 사용할 수 있습니다."}
        </p>
        {error && (
          <p className={styles.fieldError} role="alert">
            {error}
          </p>
        )}
        <footer>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={onClose}
          >
            취소
          </button>
          <button
            className={styles.acceptButton}
            disabled={busy || !name.trim()}
          >
            {busy ? "만드는 중…" : "만들기"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}

export function CloudWorkspace({
  authenticationEnabled = false,
  legacyThreadId,
}: {
  authenticationEnabled?: boolean;
  legacyThreadId?: string;
}) {
  const workspace = useCloudWorkspace();
  const { state, project, controller } = workspace;
  const folder = useCloudFolder(controller, state.activeId);
  const catalog = useWorkspaceModels();
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [tab, setTab] = useState<CloudInspectorTab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [desktopLayout, setDesktopLayout] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [savedFontScale, setFontScale] = useLocalStorage(
    "open-canvas-markdown-font-scale",
    100
  );
  const fontScale = Number.isFinite(savedFontScale)
    ? Math.min(200, Math.max(75, savedFontScale))
    : 100;
  const [creating, setCreating] = useState<"project" | "file">();
  const [dragging, setDragging] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [selectionState, setSelectionState] = useState<{
    id: string;
    path: string;
    value: TextSelection;
  }>();
  const fileInput = useRef<HTMLInputElement>(null);
  const fileToggle = useRef<HTMLButtonElement>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const path = project?.activePath;
  const id = project?.workspace.id;
  const draft = path ? project?.documents[path] : undefined;
  const proposal = project?.reviewId
    ? project.proposalDetails[project.reviewId]
    : undefined;
  const virtualProposal =
    !draft && proposal?.path === path ? proposal : undefined;
  const document =
    project && (draft || virtualProposal)
      ? workspaceDocument(project, path, virtualProposal)
      : undefined;
  const review = useReviewFocus(
    document?.id,
    document?.content ?? "",
    proposal?.path === path ? proposal : undefined
  );
  const capturedSelection =
    selectionState && selectionState.id === id && selectionState.path === path
      ? selectionState.value
      : undefined;
  const selection =
    capturedSelection &&
    document?.content.slice(capturedSelection.from, capturedSelection.to) ===
      capturedSelection.text
      ? capturedSelection
      : undefined;
  const selected = selection?.text.trim() ? selection : undefined;
  const htmlDocument = !!path && isHtmlFile(path);
  const sidebarIsDrawer = htmlDocument || !desktopLayout;
  const sidebarVisible = sidebarIsDrawer ? sidebarOpen : !sidebarCollapsed;
  const htmlPreviewVisible =
    htmlDocument && (mode === "read" || !!virtualProposal);
  const htmlWide = !sidebarOpen && !inspectorOpen;
  const dirty = isDirty(draft);
  const saving = !!path && !!project?.saving.includes(path);
  const agentBusy =
    project?.submitting ||
    project?.jobs.some(
      (job) => job.status === "queued" || job.status === "running"
    );

  const download = async () => {
    if (!document || downloading) return;
    const name = document.name;
    const content = virtualProposal?.proposedContent ?? document.content;
    setDownloading(true);
    try {
      downloadDocument(
        name,
        htmlDocument ? await standaloneHtml(content) : content
      );
    } catch (error) {
      controller.report(error);
    } finally {
      setDownloading(false);
    }
  };

  useEffect(() => {
    setInspectorOpen(window.matchMedia("(min-width: 900px)").matches);
    const desktop = window.matchMedia("(min-width: 1100px)");
    const updateLayout = () => {
      setDesktopLayout(desktop.matches);
      setSidebarOpen(false);
    };
    updateLayout();
    desktop.addEventListener("change", updateLayout);
    return () => desktop.removeEventListener("change", updateLayout);
  }, []);
  useEffect(() => {
    scrollArea.current?.scrollTo({ top: 0 });
    review.clear();
    if (document && !document.content && draft) setMode("edit");
    // Only navigation should change the author's chosen reading mode.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, path]);
  useEffect(() => {
    if (!state.notice) return;
    const timer = setTimeout(() => controller.notify(undefined), 6500);
    return () => clearTimeout(timer);
  }, [controller, state.notice]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (id && path && draft)
          void controller.save(id, path).catch(controller.report);
      }
      if (
        event.key === "Escape" &&
        (window.matchMedia("(max-width: 1099px)").matches ||
          (htmlDocument && sidebarOpen))
      ) {
        setSidebarOpen(false);
        if (window.matchMedia("(max-width: 899px)").matches)
          setInspectorOpen(false);
        fileToggle.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [controller, draft, htmlDocument, id, path, sidebarOpen]);

  const openInspector = (next: CloudInspectorTab) => {
    setTab(next);
    setInspectorOpen(true);
    setSidebarOpen(false);
  };
  const select = (value: TextSelection | undefined) => {
    setSelectionState(value && id && path ? { id, path, value } : undefined);
    if (value?.text.trim()) review.clear();
  };
  const clearSelection = (expected?: TextSelection | null) => {
    if (expected === null) return;
    setSelectionState((current) => {
      if (!current) return current;
      const submitted = {
        workspaceId: id,
        path,
        selection: expected ?? current.value,
      };
      return ownsSelection(submitted, {
        workspaceId: current.id,
        path: current.path,
        selection: current.value,
      })
        ? undefined
        : current;
    });
  };
  const importDialog = () => fileInput.current?.click();
  const newFile = () => {
    setCreating("file");
    setSidebarOpen(false);
  };

  if (!state.ready)
    return (
      <div className={styles.bootScreen}>
        <div className={styles.brandMark}>
          <span />
          <span />
          <span />
        </div>
        <p>작업 공간을 여는 중입니다.</p>
      </div>
    );

  return (
    <div
      className={`${styles.workspace} ${cloud.layout} ${htmlDocument ? cloud.htmlLayout : ""} ${sidebarOpen ? `${styles.sidebarOpen} ${cloud.filesOpen}` : ""} ${sidebarCollapsed && !htmlDocument ? cloud.filesCollapsed : ""} ${inspectorOpen ? styles.inspectorOpen : `${styles.inspectorClosed} ${cloud.closed}`}`}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) {
          event.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void workspace
          .importFiles(Array.from(event.dataTransfer.files))
          .catch(controller.report);
      }}
    >
      <input
        ref={fileInput}
        type="file"
        accept=".md,.markdown,.txt,.html,.htm,text/plain,text/markdown,text/html"
        multiple
        hidden
        data-testid="file-import"
        aria-label="문서 파일 가져오기"
        onChange={(event) => {
          void workspace
            .importFiles(Array.from(event.target.files ?? []))
            .catch(controller.report);
          event.target.value = "";
          setSidebarOpen(false);
        }}
      />
      {(sidebarOpen || inspectorOpen) && (
        <button
          className={`${styles.backdrop} ${htmlDocument && sidebarOpen ? cloud.htmlFileBackdrop : ""}`}
          aria-label="열린 패널 닫기"
          onClick={() => {
            setSidebarOpen(false);
            if (
              !htmlDocument ||
              window.matchMedia("(max-width: 899px)").matches
            )
              setInspectorOpen(false);
            fileToggle.current?.focus();
          }}
        />
      )}
      <CloudSidebar
        workspace={workspace}
        folder={folder}
        onImport={importDialog}
        onNewProject={() => setCreating("project")}
        onNewFile={newFile}
        onSync={() => openInspector("sync")}
        onClose={() => {
          setSidebarOpen(false);
          fileToggle.current?.focus();
        }}
        focusFileSearch={htmlDocument && sidebarOpen}
        authenticationEnabled={authenticationEnabled}
        onSelect={(nextPath) => {
          if (id)
            void controller.openFile(id, nextPath).catch(controller.report);
          setSidebarOpen(false);
          if (
            isHtmlFile(nextPath) ||
            window.matchMedia("(max-width: 1099px)").matches
          )
            fileToggle.current?.focus();
        }}
      />
      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.breadcrumb}>
            <button
              ref={fileToggle}
              className={`${styles.iconButton} ${cloud.fileToggle}`}
              onClick={() => {
                if (!sidebarIsDrawer) {
                  setSidebarCollapsed((collapsed) => !collapsed);
                  return;
                }
                setSidebarOpen((open) => !open);
                if (window.matchMedia("(max-width: 899px)").matches)
                  setInspectorOpen(false);
              }}
              aria-label={
                sidebarVisible ? "파일 목록 숨기기" : "파일 목록 열기"
              }
              title={sidebarVisible ? "파일 목록 숨기기" : "파일 목록 열기"}
              aria-expanded={sidebarVisible}
              aria-controls="cloud-workspace-files"
            >
              {sidebarVisible ? (
                <PanelLeftClose size={18} />
              ) : (
                <PanelLeft size={18} />
              )}
            </button>
            <span>{project?.workspace.name ?? "글쓰기 작업실"}</span>
            <ChevronRight size={13} />
            <strong title={path}>{path ?? "새로운 이야기"}</strong>
          </div>
          <div className={styles.topbarActions}>
            <button
              className={styles.iconButton}
              aria-label="프로젝트 새로고침"
              onClick={() => {
                void controller
                  .reload()
                  .then(() => {
                    if (id && path && draft)
                      return controller.fetchFile(id, path);
                  })
                  .catch(controller.report);
              }}
            >
              <RefreshCw size={15} />
            </button>
            <button
              className={styles.iconButton}
              onClick={() => {
                setInspectorOpen(!inspectorOpen);
                setSidebarOpen(false);
              }}
              aria-label={inspectorOpen ? "대화 도구 숨기기" : "대화 도구 열기"}
              aria-expanded={inspectorOpen}
            >
              <PanelRight size={18} />
            </button>
          </div>
        </header>
        {state.error && (
          <div className={styles.errorBanner} role="alert">
            <AlertCircle size={17} />
            <span>{state.error}</span>
            <button
              className={styles.iconButton}
              onClick={controller.clearError}
              aria-label="오류 안내 닫기"
            >
              <X size={16} />
            </button>
          </div>
        )}
        {legacyThreadId && (
          <LegacyThread
            threadId={legacyThreadId}
            controller={controller}
            workspaceId={id}
          />
        )}
        {document ? (
          <>
            <div
              className={`${styles.documentToolbar} ${htmlDocument ? cloud.htmlToolbar : cloud.markdownToolbar}`}
            >
              <div
                className={`${styles.documentIdentity} ${htmlDocument ? cloud.htmlIdentity : ""}`}
              >
                <div className={styles.documentIcon}>
                  <FileText size={20} strokeWidth={1.5} />
                </div>
                <div className={cloud.fileIdentity}>
                  <strong title={path}>{document.name}</strong>
                  <span
                    className={
                      draft?.remote
                        ? styles.statusWarning
                        : styles.documentStatus
                    }
                  >
                    {dirty || draft?.remote ? (
                      <span className={styles.alertDot} />
                    ) : (
                      <Check size={11} />
                    )}
                    {draft?.remote
                      ? "클라우드 변경 확인 필요"
                      : virtualProposal
                        ? "새 파일 제안 · 승인 후 저장"
                        : saving
                          ? "클라우드에 저장 중…"
                          : dirty
                            ? "저장할 변경 있음"
                            : "프로젝트에 저장됨"}
                  </span>
                </div>
              </div>
              <div
                className={`${styles.documentActions} ${htmlDocument ? cloud.htmlActions : cloud.markdownActions}`}
              >
                <fieldset
                  className={styles.viewToggle}
                  aria-label="문서 보기 방식"
                >
                  <button
                    aria-pressed={mode === "read" || !!virtualProposal}
                    onClick={() => {
                      review.requestReading();
                      setMode("read");
                    }}
                  >
                    <BookOpen size={14} />
                    <span>{htmlDocument ? "미리보기" : "읽기"}</span>
                  </button>
                  <button
                    aria-pressed={mode === "edit" && !virtualProposal}
                    disabled={!!virtualProposal}
                    onClick={() => setMode("edit")}
                  >
                    <Code2 size={14} />
                    <span>{htmlDocument ? "HTML 코드" : "Markdown 편집"}</span>
                  </button>
                </fieldset>
                {!htmlDocument && mode === "read" && !virtualProposal && (
                  <fieldset
                    className={`${styles.viewToggle} ${cloud.fontSizeControl}`}
                    aria-label="마크다운 글자 크기"
                  >
                    <button
                      type="button"
                      onClick={() => setFontScale(Math.max(75, fontScale - 25))}
                      disabled={fontScale <= 75}
                      aria-label="글자 크기 줄이기"
                      title="글자 크기 줄이기"
                    >
                      <Minus size={14} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setFontScale(100)}
                      aria-label="글자 크기 기본값으로"
                      title="기본 크기로 되돌리기 (100%)"
                    >
                      <output aria-live="polite">{fontScale}%</output>
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setFontScale(Math.min(200, fontScale + 25))
                      }
                      disabled={fontScale >= 200}
                      aria-label="글자 크기 키우기"
                      title="글자 크기 키우기"
                    >
                      <Plus size={14} aria-hidden="true" />
                    </button>
                  </fieldset>
                )}
                {htmlDocument && (
                  <button
                    className={`${styles.secondaryButton} ${cloud.previewWidthToggle}`}
                    aria-pressed={htmlWide}
                    onClick={() => {
                      setSidebarOpen(false);
                      setInspectorOpen(htmlWide);
                    }}
                  >
                    {htmlWide ? (
                      <PanelRight size={15} />
                    ) : (
                      <Maximize2 size={15} />
                    )}
                    {htmlWide ? "대화 보기" : "넓게 보기"}
                  </button>
                )}
                <button
                  className={styles.iconButton}
                  onClick={() => void download()}
                  disabled={downloading}
                  aria-busy={downloading}
                  aria-label={
                    htmlDocument ? "HTML 다운로드" : "Markdown 다운로드"
                  }
                >
                  {downloading ? (
                    <LoaderCircle size={17} className={styles.spin} />
                  ) : (
                    <ArrowDownToLine size={17} />
                  )}
                </button>
                <button
                  className={styles.saveButton}
                  disabled={!draft || saving || !dirty || !!draft.remote}
                  aria-label="클라우드 저장"
                  onClick={() => {
                    if (id && path)
                      void controller.save(id, path).catch(controller.report);
                  }}
                >
                  {saving ? (
                    <LoaderCircle size={15} className={styles.spin} />
                  ) : (
                    <Save size={15} />
                  )}
                  <span>
                    {virtualProposal
                      ? "승인 대기"
                      : saving
                        ? "저장 중"
                        : dirty
                          ? "저장"
                          : "저장됨"}
                  </span>
                </button>
              </div>
            </div>
            {draft?.remote && id && path && (
              <div className={cloud.conflictBanner}>
                <p>
                  <AlertCircle size={16} />
                  <strong>클라우드 파일이 변경되었습니다.</strong> 편집 중인
                  초안은 그대로 보관했습니다.
                </p>
                <details>
                  <summary>두 버전 비교</summary>
                  <div className={cloud.syncComparison}>
                    <label>
                      내 초안<pre>{draft.content}</pre>
                    </label>
                    <label>
                      클라우드 최신 버전<pre>{draft.remote.content}</pre>
                    </label>
                  </div>
                </details>
                <div className={cloud.syncActions}>
                  <button
                    className={styles.secondaryButton}
                    onClick={() =>
                      downloadDocument(document.name, draft.content)
                    }
                  >
                    내 초안 다운로드
                  </button>
                  <button
                    className={styles.secondaryButton}
                    onClick={() => {
                      void controller
                        .resolveConflict(id, path, "cloud")
                        .catch(controller.report);
                    }}
                  >
                    클라우드 버전 열기
                  </button>
                  <button
                    className={styles.acceptButton}
                    onClick={() => {
                      void controller
                        .resolveConflict(id, path, "draft")
                        .catch(controller.report);
                    }}
                  >
                    내 초안으로 클라우드 저장
                  </button>
                </div>
              </div>
            )}
            {draft?.recovery !== undefined && (
              <div className={cloud.recoveryNote}>
                <span>이전에 편집하던 초안도 보관했습니다.</span>
                <button
                  className={styles.textButton}
                  onClick={() =>
                    downloadDocument(`복구-${document.name}`, draft.recovery!)
                  }
                >
                  보관한 초안 다운로드
                </button>
              </div>
            )}
            {!!draft?.recoveryCopies?.length && (
              <details className={cloud.recoveryNote}>
                <summary>
                  추가로 보관한 초안 {draft.recoveryCopies.length}개
                </summary>
                {draft.recoveryCopies.map((content, index) => (
                  <button
                    key={index}
                    className={styles.textButton}
                    onClick={() =>
                      downloadDocument(
                        `복구-${index + 2}-${document.name}`,
                        content
                      )
                    }
                  >
                    복구 사본 {index + 2} 다운로드
                  </button>
                ))}
              </details>
            )}
            <div
              className={`${styles.documentStage} ${htmlPreviewVisible ? cloud.htmlStage : ""}`}
            >
              <div
                ref={scrollArea}
                className={`${styles.documentScroll} ${htmlPreviewVisible ? cloud.htmlViewport : ""}`}
              >
                <div
                  className={`${htmlDocument ? cloud.htmlPaper : styles.paper} ${mode === "edit" && !virtualProposal ? styles.paperEditor : ""}`}
                >
                  <div
                    className={`${styles.paperEyebrow} ${htmlDocument ? cloud.htmlEyebrow : ""}`}
                  >
                    <span>
                      {htmlDocument
                        ? mode === "edit"
                          ? "HTML SOURCE"
                          : "HTML CANVAS"
                        : mode === "read" || virtualProposal
                          ? "YOUR WORDS, THOUGHTFULLY CRAFTED"
                          : "MARKDOWN SOURCE"}
                    </span>
                    <span>
                      {document.name.split(".").at(-1)?.toUpperCase()}
                    </span>
                  </div>
                  {virtualProposal && htmlDocument ? (
                    <>
                      <div className={cloud.htmlProposalNotice}>
                        <span>
                          새 HTML 제안 · 미리보기를 확인하고 검토 패널에서
                          승인하세요.
                        </span>
                        <button
                          className={styles.textButton}
                          onClick={() => openInspector("review")}
                        >
                          수정안 검토
                        </button>
                      </div>
                      <HtmlPreview
                        content={virtualProposal.proposedContent}
                        title="새 HTML 제안 미리보기"
                        fill
                      />
                    </>
                  ) : virtualProposal ? (
                    <div className={cloud.proposedFile}>
                      {review.focus && (
                        <p
                          className={styles.newContentAnchor}
                          data-review-source={review.focus.changeId}
                        >
                          변경 {String(review.focus.number).padStart(2, "0")} ·
                          새 내용이 들어갈 위치
                        </p>
                      )}
                      <FileText size={35} strokeWidth={1.2} />
                      <h2>새 문서가 제안되었어요.</h2>
                      <p>
                        오른쪽 검토 패널에서 내용을 확인하고 승인하면 프로젝트에
                        저장됩니다.
                      </p>
                      <button
                        className={styles.acceptButton}
                        onClick={() => openInspector("review")}
                      >
                        수정안 검토
                      </button>
                    </div>
                  ) : mode === "read" && htmlDocument ? (
                    <HtmlPreview
                      content={document.content}
                      onSelection={select}
                      selection={selection}
                      title={`${document.name} 미리보기`}
                      fill
                    />
                  ) : mode === "read" ? (
                    <DocumentPreview
                      content={document.content}
                      fontScale={fontScale / 100}
                      onSelection={select}
                      reviewFocus={review.focus}
                      onSourceUnavailable={() => {
                        if (review.readingRequested) review.clear();
                        else setMode("edit");
                      }}
                    />
                  ) : (
                    <MarkdownEditor
                      key={`${id}/${path}`}
                      content={document.content}
                      format={htmlDocument ? "html" : "markdown"}
                      onChange={(content) => {
                        if (id && path) controller.edit(id, path, content);
                      }}
                      onSelection={
                        htmlDocument ? () => select(undefined) : select
                      }
                      reviewFocus={review.focus}
                    />
                  )}
                </div>
                <p
                  className={`${styles.pageHint} ${htmlPreviewVisible ? cloud.htmlPageHint : ""}`}
                >
                  {virtualProposal
                    ? "검토 패널에서 승인하면 이 페이지를 편집할 수 있어요."
                    : mode === "read"
                      ? htmlDocument
                        ? "영역을 선택하면, 문구와 디자인을 함께 다듬을 수 있어요."
                        : "문장을 선택하면, 그 부분만 함께 다듬을 수 있어요."
                      : "편집한 내용은 저장 버튼으로 프로젝트에 반영합니다."}
                </p>
              </div>
              {selected && (
                <div
                  className={`${styles.selectionToolbar} ${selected.nodeId ? cloud.htmlSelectionToolbar : ""}`}
                  aria-label="선택 영역 작업"
                >
                  <span>
                    {selected.nodeId
                      ? "영역 선택"
                      : `${selected.text.length}자 선택`}
                  </span>
                  {selected.nodeId && (
                    <button onClick={() => openInspector("chat")}>
                      <Code2 size={14} /> 디자인 요청
                    </button>
                  )}
                  <button
                    disabled={agentBusy}
                    onClick={() => {
                      openInspector("chat");
                      void controller
                        .send(editingInstruction("proofread"), {
                          selection: selected,
                          model: catalog.model,
                        })
                        .then(() => clearSelection(selected))
                        .catch(controller.report);
                    }}
                  >
                    <Sparkles size={14} /> 교정
                  </button>
                  <button onClick={() => openInspector("sources")}>
                    <BookOpen size={14} /> 출처 연결
                  </button>
                  <button
                    onClick={() => setSelectionState(undefined)}
                    aria-label="선택 영역 해제"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
              {review.focus && (
                <ReviewFocusToolbar
                  focus={review.focus}
                  onReview={() => openInspector("review")}
                  onClear={review.clear}
                />
              )}
            </div>
            <footer
              className={`${styles.documentFooter} ${htmlPreviewVisible ? cloud.htmlFooter : ""}`}
            >
              <span>
                {htmlDocument ? "HTML" : "Markdown"} <i /> UTF-8{" "}
                {document.content.startsWith("\uFEFF") ? "· BOM " : ""}
                {document.content.includes("\r\n") ? "· CRLF" : ""}
              </span>
              <span>
                {(
                  virtualProposal?.proposedContent ?? document.content
                ).length.toLocaleString("ko-KR")}
                자 {selected && `· ${selected.text.length}자 선택`}
              </span>
              <button onClick={() => openInspector("chat")}>
                <Sparkles size={12} /> AI와 함께 쓰기
              </button>
            </footer>
          </>
        ) : state.activeId &&
          (!project ||
            (path &&
              project.files.some((file) => file.path === path) &&
              !draft)) ? (
          <div className={styles.bootScreen}>
            <LoaderCircle size={25} className={styles.spin} />
            <p>프로젝트를 여는 중…</p>
          </div>
        ) : (
          <div className={`${styles.noDocument} ${cloud.welcome}`}>
            <div className={cloud.welcomeMark}>
              <FileText size={35} strokeWidth={1} />
              <Sparkles size={18} />
            </div>
            <span className={cloud.eyebrow}>ROOM FOR YOUR NEXT IDEA</span>
            <h1>
              파일, 글, 대화를
              <br />
              한곳에서 이어가세요.
            </h1>
            <p>
              {project
                ? "문서를 열고, 생각을 나누고, 마음에 드는 수정만 반영하세요."
                : "프로젝트를 만들고 나만의 글쓰기 공간을 시작하세요."}
            </p>
            <div>
              <button
                className={styles.acceptButton}
                onClick={project ? newFile : () => setCreating("project")}
              >
                <Plus size={16} />
                {project ? "새 문서" : "첫 프로젝트 만들기"}
              </button>
              {project && (
                <button
                  className={styles.secondaryButton}
                  onClick={importDialog}
                >
                  <Upload size={15} />
                  파일 가져오기
                </button>
              )}
            </div>
            <div className={cloud.welcomeFeatures}>
              <span>
                <Cloud size={15} /> 프로젝트별 파일
              </span>
              <span>
                <Sparkles size={15} /> 이어지는 대화
              </span>
              <span>
                <Check size={15} /> 변경별 승인
              </span>
            </div>
          </div>
        )}
      </main>
      <CloudInspector
        workspace={workspace}
        folder={folder}
        tab={tab}
        setTab={setTab}
        selection={selection}
        onClearSelection={clearSelection}
        onClose={() => setInspectorOpen(false)}
        onImport={importDialog}
        catalog={catalog}
        activeChangeId={review.focus?.changeId}
        onLocateChange={(changeId) => {
          clearSelection();
          review.locate(changeId);
          if (htmlDocument) setMode("edit");
          if (window.matchMedia("(max-width: 899px)").matches)
            setInspectorOpen(false);
        }}
        onRestore={(content) => {
          if (id && path) {
            controller.edit(id, path, content);
            setMode("edit");
            setSelectionState(undefined);
            controller.notify(
              "이전 내용을 초안으로 열었습니다. 저장 버튼을 눌러 반영하세요."
            );
          }
        }}
      />
      {creating && (
        <CreateItem
          kind={creating}
          onClose={() => setCreating(undefined)}
          onCreate={async (name) => {
            if (creating === "project") await controller.createWorkspace(name);
            else if (id) {
              await controller.createFile(
                id,
                isDocumentFile(name.trim()) ? name.trim() : `${name.trim()}.md`,
                isHtmlFile(name.trim()) ? EMPTY_HTML_DOCUMENT : ""
              );
              setMode(isHtmlFile(name.trim()) ? "read" : "edit");
            }
          }}
        />
      )}
      {state.notice && (
        <output className={styles.toast}>
          <Check size={16} />
          <span>{state.notice}</span>
          <button
            onClick={() => controller.notify(undefined)}
            aria-label="알림 닫기"
          >
            <X size={15} />
          </button>
        </output>
      )}
      {dragging && (
        <div className={styles.dropOverlay}>
          <Upload size={36} />
          <strong>프로젝트에 파일을 가져오세요.</strong>
          <span>Markdown · TXT · HTML</span>
        </div>
      )}
    </div>
  );
}
