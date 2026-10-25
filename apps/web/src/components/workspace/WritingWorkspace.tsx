"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertCircle,
  ArrowDownToLine,
  BookOpen,
  Check,
  ChevronRight,
  Code2,
  FileText,
  FolderOpen,
  LoaderCircle,
  PanelLeft,
  PanelRight,
  Save,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { useWritingWorkspace } from "@/hooks/useWritingWorkspace";
import { downloadMarkdown } from "@/lib/workspace/files";
import { editingInstruction } from "@/lib/workspace/review-policy";
import { DEFAULT_MODEL_NAME } from "@/shared/models";
import type { TextSelection } from "@/lib/workspace/types";
import { DocumentPreview } from "./DocumentPreview";
import { FileSidebar } from "./FileSidebar";
import { WritingInspector, type InspectorTab } from "./WritingInspector";
import styles from "./workspace.module.css";

const MarkdownEditor = dynamic(() => import("./MarkdownEditor"), {
  ssr: false,
  loading: () => <div className={styles.editorLoading}>편집기를 여는 중…</div>,
});

export function WritingWorkspace({
  authenticationEnabled = false,
}: {
  authenticationEnabled?: boolean;
}) {
  const workspace = useWritingWorkspace();
  const document = workspace.activeDocument;
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [selection, setSelection] = useState<TextSelection>();
  const [tab, setTab] = useState<InspectorTab>("review");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [filename, setFilename] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const [model, setModel] = useState(DEFAULT_MODEL_NAME);
  const [models, setModels] = useState([
    { name: DEFAULT_MODEL_NAME, label: "Claude Opus 5.5" },
  ]);
  const [modelUnavailable, setModelUnavailable] = useState(false);
  const modelController = useRef<AbortController | undefined>(undefined);
  const firstCatalog = useRef(true);
  const previousDocumentId = useRef<string | undefined>(undefined);
  const { notice, setNotice, saveDocument } = workspace;

  const loadModels = useCallback(async () => {
    modelController.current?.abort();
    const controller = new AbortController();
    modelController.current = controller;
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch("/api/models/list", {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Model catalog unavailable");
      const data = (await response.json()) as {
        models: { name: string; label: string }[];
        defaultModelName: string;
      };
      if (!Array.isArray(data.models) || !data.models.length)
        throw new Error("Empty model catalog");
      const catalog = data.models.filter(
        (item) =>
          typeof item?.name === "string" && typeof item.label === "string"
      );
      if (!catalog.length) throw new Error("Invalid model catalog");
      setModels(catalog);
      const initial = firstCatalog.current;
      setModel((previous) =>
        !initial && catalog.some((item) => item.name === previous)
          ? previous
          : (catalog.find((item) => item.name === data.defaultModelName)
              ?.name ?? catalog[0].name)
      );
      firstCatalog.current = false;
      setModelUnavailable(false);
    } catch {
      if (modelController.current === controller) setModelUnavailable(true);
    } finally {
      clearTimeout(timeout);
    }
  }, []);

  useEffect(() => {
    setInspectorOpen(window.matchMedia("(min-width: 900px)").matches);
    void loadModels();
    return () => modelController.current?.abort();
  }, [loadModels]);

  useEffect(() => {
    if (previousDocumentId.current === document?.id) return;
    previousDocumentId.current = document?.id;
    setSelection(undefined);
    setFilename(document?.name ?? "");
    if (document && !document.content) setMode("edit");
    scrollArea.current?.scrollTo({ top: 0 });
  }, [document]);

  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(undefined), 8000);
    return () => clearTimeout(timeout);
  }, [notice, setNotice]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (document) void saveDocument(document.id, event.shiftKey);
      }
      if (
        event.key === "Escape" &&
        window.matchMedia("(max-width: 899px)").matches
      ) {
        setSidebarOpen(false);
        setInspectorOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [document, saveDocument]);

  const select = (selected: TextSelection | undefined) => {
    setSelection(selected);
    if (selected?.text.trim()) {
      setInspectorOpen(true);
      if (tab === "history") setTab("review");
    }
  };
  const openInspector = (nextTab: InspectorTab) => {
    setTab(nextTab);
    setInspectorOpen(true);
    setSidebarOpen(false);
  };
  const selected = selection?.text.trim() ? selection : undefined;
  const diskDirty = document && document.content !== document.disk?.content;
  const status = document?.external
    ? "외부 변경 확인 필요"
    : document?.missing
      ? "원본 파일 없음"
      : document?.fileHandle
        ? diskDirty
          ? "저장할 변경 있음"
          : "파일과 동기화됨"
        : "브라우저 초안";
  const importDialog = () => fileInput.current?.click();

  if (!workspace.ready)
    return (
      <div className={styles.bootScreen}>
        <div className={styles.brandMark}>
          <span />
          <span />
          <span />
        </div>
        <p>글쓰기 작업실을 여는 중입니다.</p>
      </div>
    );

  return (
    <div
      className={`${styles.workspace} ${sidebarOpen ? styles.sidebarOpen : ""} ${inspectorOpen ? styles.inspectorOpen : styles.inspectorClosed}`}
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
        void workspace.importFiles(Array.from(event.dataTransfer.files));
      }}
    >
      <input
        ref={fileInput}
        type="file"
        accept=".md,.markdown,.txt,text/plain,text/markdown"
        multiple
        hidden
        data-testid="file-import"
        aria-label="Markdown 파일 가져오기"
        onChange={(event) => {
          void workspace.importFiles(Array.from(event.target.files ?? []));
          event.target.value = "";
          setSidebarOpen(false);
        }}
      />
      {(sidebarOpen || inspectorOpen) && (
        <button
          className={styles.backdrop}
          aria-label="열린 패널 닫기"
          onClick={() => {
            setSidebarOpen(false);
            setInspectorOpen(false);
          }}
        />
      )}
      <FileSidebar
        authenticationEnabled={authenticationEnabled}
        workspace={{
          ...workspace,
          newDocument: () => {
            workspace.newDocument();
            setSidebarOpen(false);
          },
        }}
        onImport={importDialog}
        onClose={() => setSidebarOpen(false)}
        onSelect={(id) => {
          workspace.selectDocument(id);
          setSidebarOpen(false);
        }}
      />
      <main className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.breadcrumb}>
            <button
              className={`${styles.iconButton} ${styles.sidebarToggle}`}
              onClick={() => {
                setSidebarOpen(!sidebarOpen);
                setInspectorOpen(false);
              }}
              aria-label="파일 목록 열기"
            >
              <PanelLeft size={18} />
            </button>
            <span>글쓰기 작업실</span>
            <ChevronRight size={13} />
            <strong>{document?.name ?? "새로운 이야기"}</strong>
          </div>
          <div className={styles.topbarActions}>
            <span className={styles.privateBadge}>
              <span className={styles.statusDot} /> 나의 작업 공간
            </span>
            <button
              className={styles.iconButton}
              onClick={() => {
                setInspectorOpen(!inspectorOpen);
                setSidebarOpen(false);
              }}
              aria-label={inspectorOpen ? "검토 도구 숨기기" : "검토 도구 열기"}
              aria-expanded={inspectorOpen}
            >
              <PanelRight size={18} />
            </button>
          </div>
        </header>

        {workspace.error && (
          <div className={styles.errorBanner} role="alert">
            <AlertCircle size={17} />
            <span>{workspace.error}</span>
            <button
              className={styles.iconButton}
              onClick={() => workspace.setError(undefined)}
              aria-label="오류 안내 닫기"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {document ? (
          <>
            <div className={styles.documentToolbar}>
              <div className={styles.documentIdentity}>
                <div className={styles.documentIcon}>
                  <FileText size={20} strokeWidth={1.5} />
                </div>
                <div>
                  {document.fileHandle ? (
                    <strong title={document.path}>{document.name}</strong>
                  ) : (
                    <input
                      className={styles.filenameInput}
                      value={filename}
                      aria-label="문서 파일 이름"
                      onChange={(event) => setFilename(event.target.value)}
                      onBlur={() =>
                        workspace.renameDocument(document.id, filename)
                      }
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.currentTarget.blur();
                      }}
                    />
                  )}
                  <span
                    className={
                      document.external
                        ? styles.statusWarning
                        : styles.documentStatus
                    }
                  >
                    {document.external ? (
                      <AlertCircle size={11} />
                    ) : document.fileHandle && !diskDirty ? (
                      <Check size={11} />
                    ) : (
                      <span className={styles.draftDot} />
                    )}
                    {status}
                  </span>
                </div>
              </div>
              <div className={styles.documentActions}>
                <fieldset
                  className={styles.viewToggle}
                  aria-label="문서 보기 방식"
                >
                  <button
                    aria-pressed={mode === "read"}
                    onClick={() => setMode("read")}
                  >
                    <BookOpen size={14} />
                    <span>읽기</span>
                  </button>
                  <button
                    aria-pressed={mode === "edit"}
                    onClick={() => setMode("edit")}
                  >
                    <Code2 size={14} />
                    <span>Markdown 편집</span>
                  </button>
                </fieldset>
                <button
                  className={styles.iconButton}
                  onClick={() =>
                    downloadMarkdown(document.name, document.content)
                  }
                  aria-label="Markdown 다운로드"
                  title="Markdown 다운로드"
                >
                  <ArrowDownToLine size={17} />
                </button>
                <button
                  className={styles.saveButton}
                  disabled={!!workspace.savingId}
                  onClick={() => void workspace.saveDocument(document.id)}
                >
                  {workspace.savingId === document.id ? (
                    <LoaderCircle size={15} className={styles.spin} />
                  ) : (
                    <Save size={15} />
                  )}
                  <span>
                    {workspace.savingId === document.id
                      ? "저장 중"
                      : "파일 저장"}
                  </span>
                </button>
              </div>
            </div>
            {document.external && (
              <div className={styles.externalBanner} aria-live="polite">
                <div>
                  <FolderOpen size={17} />
                  <span>
                    <strong>파일이 다른 곳에서 변경되었어요.</strong> 현재
                    초안과 비교해 보세요.
                  </span>
                </div>
                <button
                  className={styles.textButton}
                  onClick={() => workspace.keepDraft(document.id)}
                >
                  현재 초안 유지
                </button>
                <button
                  className={styles.secondaryButton}
                  onClick={() => {
                    workspace.reviewExternal(document.id);
                    openInspector("review");
                  }}
                >
                  변경 비교
                </button>
              </div>
            )}
            {document.missing && (
              <div className={styles.externalBanner}>
                <span>
                  원본 파일이 이동되거나 삭제되었습니다. 초안은 보관되어
                  있습니다.
                </span>
                <button
                  className={styles.secondaryButton}
                  onClick={() => void workspace.saveDocument(document.id, true)}
                >
                  다른 이름으로 저장
                </button>
              </div>
            )}
            <div className={styles.documentStage}>
              <div ref={scrollArea} className={styles.documentScroll}>
                <div
                  className={`${styles.paper} ${mode === "edit" ? styles.paperEditor : ""}`}
                >
                  <div className={styles.paperEyebrow}>
                    <span>
                      {mode === "read"
                        ? "YOUR WORDS, THOUGHTFULLY CRAFTED"
                        : "MARKDOWN SOURCE"}
                    </span>
                    <span>.md</span>
                  </div>
                  {mode === "read" ? (
                    <DocumentPreview
                      content={document.content}
                      onSelection={select}
                    />
                  ) : (
                    <MarkdownEditor
                      key={document.id}
                      content={document.content}
                      onChange={(content) =>
                        workspace.updateContent(document.id, content)
                      }
                      onSelection={select}
                    />
                  )}
                </div>
                <p className={styles.pageHint}>
                  {mode === "read"
                    ? "문장을 선택하면, 그 부분만 함께 다듬을 수 있어요."
                    : "원본 Markdown 서식과 줄바꿈을 그대로 보존합니다."}
                </p>
              </div>
              {selected && (
                <div
                  className={styles.selectionToolbar}
                  aria-label="선택 영역 작업"
                >
                  <span>{selected.text.length}자 선택</span>
                  <button
                    disabled={!!workspace.request}
                    onClick={() => {
                      openInspector("review");
                      void workspace.propose(
                        document.id,
                        editingInstruction("proofread"),
                        selected,
                        model
                      );
                    }}
                  >
                    <Sparkles size={14} /> 교정
                  </button>
                  <button onClick={() => openInspector("sources")}>
                    <BookOpen size={14} /> 출처 연결
                  </button>
                  <button
                    onClick={() => setSelection(undefined)}
                    aria-label="선택 영역 해제"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
            </div>
            <footer className={styles.documentFooter}>
              <span>
                Markdown <i /> UTF-8{" "}
                {document.content.includes("\r\n") ? "· CRLF" : ""}
              </span>
              <span>
                {document.content.length.toLocaleString("ko-KR")}자{" "}
                {selected && `· ${selected.text.length}자 선택`}
              </span>
              <button onClick={() => openInspector("review")}>
                <Sparkles size={12} /> AI와 다듬기
              </button>
            </footer>
          </>
        ) : (
          <div className={styles.noDocument}>
            <FileText size={40} strokeWidth={1} />
            <h1>새로운 이야기를 시작하세요.</h1>
            <p>내 문서를 열거나 빈 페이지에서 시작할 수 있습니다.</p>
            <div>
              <button
                className={styles.acceptButton}
                onClick={workspace.newDocument}
              >
                새 문서
              </button>
              <button className={styles.secondaryButton} onClick={importDialog}>
                <Upload size={15} /> 파일 가져오기
              </button>
            </div>
          </div>
        )}
      </main>
      {document && (
        <WritingInspector
          key={document.id}
          document={document}
          workspace={workspace}
          selection={selection}
          onClearSelection={() => setSelection(undefined)}
          tab={tab}
          setTab={setTab}
          onClose={() => setInspectorOpen(false)}
          models={models}
          model={model}
          onModelChange={setModel}
          modelUnavailable={modelUnavailable}
          onRetryModels={() => void loadModels()}
        />
      )}
      {notice && (
        <output className={styles.toast}>
          <Check size={16} />
          <span>{notice}</span>
          <button onClick={() => setNotice(undefined)} aria-label="알림 닫기">
            <X size={15} />
          </button>
        </output>
      )}
      {dragging && (
        <div className={styles.dropOverlay}>
          <Upload size={36} />
          <strong>파일을 놓고 이어서 쓰세요.</strong>
          <span>Markdown · TXT</span>
        </div>
      )}
    </div>
  );
}
