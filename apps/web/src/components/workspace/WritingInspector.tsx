import { useState } from "react";
import {
  AlignLeft,
  ArrowUp,
  BookOpen,
  ChevronDown,
  History,
  Sparkles,
  SpellCheck,
  WandSparkles,
  X,
} from "lucide-react";
import type { WritingWorkspaceController } from "@/hooks/useWritingWorkspace";
import { editingInstruction } from "@/lib/workspace/review-policy";
import type {
  EditingAction,
  TextSelection,
  WorkspaceDocument,
} from "@/lib/workspace/types";
import { ReviewPanel } from "./ReviewPanel";
import { SourcesPanel } from "./SourcesPanel";
import { HistoryPanel } from "./HistoryPanel";
import styles from "./workspace.module.css";

export type InspectorTab = "review" | "sources" | "history";

export function WritingInspector({
  document,
  workspace,
  selection,
  onClearSelection,
  tab,
  setTab,
  onClose,
  models,
  model,
  onModelChange,
  modelUnavailable,
  onRetryModels,
}: {
  document: WorkspaceDocument;
  workspace: WritingWorkspaceController;
  selection?: TextSelection;
  onClearSelection: () => void;
  tab: InspectorTab;
  setTab: (tab: InspectorTab) => void;
  onClose: () => void;
  models: { name: string; label: string }[];
  model: string;
  onModelChange: (model: string) => void;
  modelUnavailable: boolean;
  onRetryModels: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const busy = !!workspace.request;
  const thisRequest = workspace.request?.documentId === document.id;
  const currentSelection = thisRequest
    ? workspace.request?.selection
    : selection;
  const selected = currentSelection?.text.trim() ? currentSelection : undefined;
  const pendingChanges =
    document.proposal?.changes.filter((change) => change.decision === "pending")
      .length ?? 0;
  const run = (action: EditingAction) => {
    const prompt = editingInstruction(action, instruction);
    void workspace.propose(document.id, prompt, selected, model);
    setTab("review");
  };

  return (
    <aside className={styles.inspector} aria-label="문서 검토 도구">
      <div className={styles.inspectorHeader}>
        <div
          className={styles.inspectorTabs}
          role="tablist"
          aria-label="문서 도구"
        >
          <button
            role="tab"
            aria-selected={tab === "review"}
            aria-controls="writing-review-panel"
            onClick={() => setTab("review")}
          >
            <Sparkles size={14} /> AI 검토{" "}
            {pendingChanges > 0 && <span>{pendingChanges}</span>}
          </button>
          <button
            role="tab"
            aria-selected={tab === "sources"}
            aria-controls="writing-sources-panel"
            onClick={() => setTab("sources")}
          >
            <BookOpen size={14} /> 출처
          </button>
          <button
            role="tab"
            aria-selected={tab === "history"}
            aria-controls="writing-history-panel"
            onClick={() => setTab("history")}
          >
            <History size={14} /> 이력
          </button>
        </div>
        <button
          className={styles.iconButton}
          onClick={onClose}
          aria-label="검토 패널 닫기"
        >
          <X size={17} />
        </button>
      </div>
      <div
        className={styles.inspectorBody}
        id={`writing-${tab}-panel`}
        role="tabpanel"
      >
        {tab === "review" && (
          <>
            <div className={styles.aiComposer}>
              <div className={styles.scopeLabel}>
                <span className={styles.statusDot} />
                {selected ? "선택한 문장" : "문서 전체"}
                <span>
                  {selected
                    ? `${selected.text.length}자 선택`
                    : document.content.trim()
                      ? "전체 내용 다듬기"
                      : "새 초안 작성"}
                </span>
              </div>
              {selected && (
                <div className={styles.selectedPassage}>
                  <p>{selected.text}</p>
                  <button
                    className={styles.iconButton}
                    disabled={thisRequest}
                    onClick={onClearSelection}
                    aria-label="문장 선택 해제"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
              <div className={styles.quickActions}>
                <button
                  disabled={busy || !document.content.trim()}
                  onClick={() => run("proofread")}
                >
                  <SpellCheck size={14} /> 교정
                </button>
                <button
                  disabled={busy || !document.content.trim()}
                  onClick={() => run("clarify")}
                >
                  <WandSparkles size={14} /> 명확하게
                </button>
                <button
                  disabled={busy || !document.content.trim()}
                  onClick={() => run("shorten")}
                >
                  <AlignLeft size={14} /> 간결하게
                </button>
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  run("custom");
                }}
              >
                <label htmlFor="writing-instruction">
                  {document.content.trim()
                    ? "어떻게 다듬을까요?"
                    : "어떤 글을 작성할까요?"}
                </label>
                <div className={styles.promptInput}>
                  <textarea
                    id="writing-instruction"
                    value={instruction}
                    onChange={(event) => setInstruction(event.target.value)}
                    placeholder={
                      document.content.trim()
                        ? "예: 핵심이 더 잘 드러나도록, 자연스럽게…"
                        : "주제, 독자, 담고 싶은 내용을 알려주세요."
                    }
                    rows={3}
                    maxLength={4000}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        (event.metaKey || event.ctrlKey) &&
                        instruction.trim() &&
                        !busy
                      ) {
                        event.preventDefault();
                        run("custom");
                      }
                    }}
                  />
                  <button
                    type="submit"
                    disabled={busy || !instruction.trim()}
                    aria-label={
                      document.content.trim()
                        ? "AI 수정안 요청"
                        : "AI 초안 요청"
                    }
                  >
                    <ArrowUp size={17} />
                  </button>
                </div>
              </form>
              <div className={styles.modelRow}>
                <Sparkles size={12} aria-hidden="true" />
                <label className={styles.modelLabel}>
                  <span className={styles.srOnly}>AI 모델</span>
                  <select
                    value={model}
                    onChange={(event) => onModelChange(event.target.value)}
                    disabled={busy}
                  >
                    {models.map((option) => (
                      <option key={option.name} value={option.name}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={11} aria-hidden="true" />
                </label>
                <span>via Bedrock</span>
              </div>
              {modelUnavailable && (
                <button className={styles.modelRetry} onClick={onRetryModels}>
                  AI 서버 연결 확인 · 다시 시도
                </button>
              )}
              {busy && !thisRequest && (
                <p className={styles.fieldHint}>
                  다른 문서의 수정안을 만들고 있습니다.
                </p>
              )}
            </div>
            <ReviewPanel
              document={document}
              pending={thisRequest}
              onCancel={workspace.cancelRequest}
              onDecide={(id, decision) => {
                workspace.decide(document.id, id, decision);
                onClearSelection();
              }}
              onDismiss={() => workspace.dismissProposal(document.id)}
            />
          </>
        )}
        {tab === "sources" && (
          <SourcesPanel
            key={document.id}
            document={document}
            hasSelection={!!selected}
            onAdd={(source) => workspace.addSource(document.id, source)}
            onCite={(source) => {
              workspace.citeSource(document.id, source, selection);
              onClearSelection();
            }}
            onRemove={(id) => workspace.removeSource(document.id, id)}
          />
        )}
        {tab === "history" && (
          <HistoryPanel
            key={document.id}
            document={document}
            onRestore={(content) => {
              workspace.restoreRevision(document.id, content);
              onClearSelection();
            }}
          />
        )}
      </div>
      <div className={styles.inspectorFooter}>
        <span className={styles.statusDot} /> 작은 수정이 더 좋은 글을 만듭니다.
      </div>
    </aside>
  );
}
