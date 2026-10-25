import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlignLeft,
  ArrowUp,
  BookOpen,
  ChevronRight,
  FileDiff,
  FileText,
  FolderSync,
  History,
  LoaderCircle,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  SpellCheck,
  WandSparkles,
  X,
} from "lucide-react";
import type { CloudWorkspaceHook } from "@/hooks/useCloudWorkspace";
import type { CloudFolderHook } from "@/hooks/useCloudFolder";
import type { useWorkspaceModels } from "@/hooks/useWorkspaceModels";
import type { CloudProjectState } from "@/lib/workspace/cloud-state";
import type { CloudProposal, ResearchGenre } from "@/lib/workspace/cloud-types";
import { editingInstruction } from "@/lib/workspace/review-policy";
import { ownsComposerDraft } from "@/lib/workspace/cloud-intent";
import { referenceUrl } from "@/lib/workspace/sources";
import { isHtmlFile } from "@/lib/workspace/files";
import type {
  EditingAction,
  TextSelection,
  WorkspaceDocument,
} from "@/lib/workspace/types";
import { ReviewPanel } from "./ReviewPanel";
import { SourcesPanel } from "./SourcesPanel";
import { HistoryPanel } from "./HistoryPanel";
import { CloudFolderPanel } from "./CloudFolderPanel";
import styles from "./workspace.module.css";
import cloud from "./cloud.module.css";

export type CloudInspectorTab =
  "chat" | "review" | "sources" | "history" | "sync";

export function workspaceDocument(
  project: CloudProjectState,
  path?: string,
  proposal?: CloudProposal
): WorkspaceDocument {
  const draft = path ? project.documents[path] : undefined;
  return {
    id: `${project.workspace.id}/${path ?? ""}`,
    name: draft?.file.name ?? path?.split("/").at(-1) ?? project.workspace.name,
    path: path ?? "",
    content: draft?.content ?? proposal?.baseContent ?? "",
    sources: project.sources,
    revisions: path ? (project.revisions[path] ?? []) : [],
    correction: path ? project.corrections[path] : undefined,
    proposal,
    updatedAt: draft?.file.updatedAt ?? project.workspace.updatedAt,
  };
}

const tabs = [
  { id: "chat", label: "대화", icon: MessageSquare },
  { id: "review", label: "검토", icon: FileDiff },
  { id: "sources", label: "출처", icon: BookOpen },
  { id: "history", label: "이력", icon: History },
] as const;

export function CloudInspector({
  workspace,
  folder,
  tab,
  setTab,
  selection,
  onClearSelection,
  onClose,
  onImport,
  onRestore,
  catalog,
  activeChangeId,
  onLocateChange,
}: {
  workspace: CloudWorkspaceHook;
  folder: CloudFolderHook;
  tab: CloudInspectorTab;
  setTab: (tab: CloudInspectorTab) => void;
  selection?: TextSelection;
  onClearSelection: (expected?: TextSelection | null) => void;
  onClose: () => void;
  onImport: () => void;
  onRestore: (content: string) => void;
  catalog: ReturnType<typeof useWorkspaceModels>;
  activeChangeId?: string;
  onLocateChange: (changeId: string) => void;
}) {
  const { project, controller } = workspace;
  const [composerDrafts, setComposerDrafts] = useState<
    Record<string, { text: string; revision: number }>
  >({});
  // Deep research applies to composer messages only, never to quick editing actions.
  const [creationMode, setCreationMode] = useState<ResearchGenre | "html" | "">(
    ""
  );
  const transcript = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const selected = selection?.text.trim() ? selection : undefined;
  const id = project?.workspace.id;
  const composerDraft = id ? composerDrafts[id] : undefined;
  const message = composerDraft?.text ?? "";
  const setMessage = (text: string) => {
    if (!id) return;
    setComposerDrafts((current) => ({
      ...current,
      [id]: { text, revision: (current[id]?.revision ?? 0) + 1 },
    }));
  };
  const path = project?.activePath;
  const htmlDocument = !!path && isHtmlFile(path);
  const document = project ? workspaceDocument(project, path) : undefined;
  const proposal = project?.reviewId
    ? project.proposalDetails[project.reviewId]
    : undefined;
  const pendingCount =
    project?.proposals.reduce((sum, item) => sum + item.pendingCount, 0) ?? 0;
  const activeVersion = path
    ? project?.documents[path]?.file.version
    : undefined;
  const agentBusy =
    project?.submitting ||
    project?.jobs.some(
      (job) => job.status === "queued" || job.status === "running"
    );

  useEffect(() => {
    following.current = true;
  }, [id]);
  useEffect(() => {
    setCreationMode("");
  }, [id, path]);
  useEffect(() => {
    if (selected) setCreationMode("");
  }, [selected]);
  useEffect(() => {
    if (following.current && transcript.current)
      transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [id, project?.messages.length, tab]);
  useEffect(() => {
    if (tab === "history" && id && path && activeVersion)
      void controller.loadHistory(id, path).catch(controller.report);
  }, [activeVersion, controller, id, path, tab]);

  const send = async (instruction: string, consumeDraft = false) => {
    const submitted = {
      workspaceId: id,
      revision: composerDraft?.revision ?? 0,
    };
    const research =
      consumeDraft && creationMode && creationMode !== "html"
        ? creationMode
        : undefined;
    const htmlGeneration = consumeDraft && creationMode === "html";
    try {
      await controller.send(instruction, {
        selection: research || htmlGeneration ? undefined : selected,
        model: catalog.model,
        researchGenre: research,
        outputFormat: htmlGeneration ? "html" : undefined,
      });
      if (consumeDraft && id)
        setComposerDrafts((current) => {
          if (
            !ownsComposerDraft(submitted, {
              workspaceId: id,
              revision: current[id]?.revision ?? 0,
            })
          )
            return current;
          return {
            ...current,
            [id]: { text: "", revision: submitted.revision + 1 },
          };
        });
      onClearSelection(selection ?? null);
      following.current = true;
    } catch (error) {
      controller.report(error);
    }
  };
  const quick = (action: EditingAction) => {
    setTab("chat");
    void send(editingInstruction(action));
  };
  const openProposal = (proposalId: string) => {
    if (!id) return;
    setTab("review");
    onClearSelection();
    void controller.openProposal(id, proposalId).catch(controller.report);
  };

  return (
    <aside
      className={`${styles.inspector} ${cloud.inspector}`}
      aria-label="대화와 문서 도구"
    >
      <div className={`${styles.inspectorHeader} ${cloud.inspectorHeader}`}>
        {tab === "sync" ? (
          <strong className={cloud.syncTitle}>
            <FolderSync size={17} /> 폴더 동기화
          </strong>
        ) : (
          <div
            className={`${styles.inspectorTabs} ${cloud.tabs}`}
            role="tablist"
            aria-label="작업 공간 도구"
          >
            {tabs.map((item, index) => (
              <button
                key={item.id}
                id={`cloud-tab-${item.id}`}
                role="tab"
                tabIndex={tab === item.id ? 0 : -1}
                aria-selected={tab === item.id}
                aria-controls={`cloud-panel-${item.id}`}
                onClick={() => setTab(item.id)}
                onKeyDown={(event) => {
                  if (
                    !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                      event.key
                    )
                  )
                    return;
                  event.preventDefault();
                  const next =
                    event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? tabs.length - 1
                        : (index +
                            (event.key === "ArrowRight" ? 1 : -1) +
                            tabs.length) %
                          tabs.length;
                  setTab(tabs[next].id);
                  event.currentTarget.parentElement
                    ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
                    [next]?.focus();
                }}
              >
                <item.icon size={14} />
                {item.label}
                {item.id === "review" && pendingCount > 0 && (
                  <span>{pendingCount}</span>
                )}
              </button>
            ))}
          </div>
        )}
        <button
          className={styles.iconButton}
          onClick={onClose}
          aria-label="도구 패널 닫기"
        >
          <X size={17} />
        </button>
      </div>
      <div
        className={`${styles.inspectorBody} ${cloud.inspectorBody}`}
        id={`cloud-panel-${tab}`}
        role={tab === "sync" ? undefined : "tabpanel"}
        aria-labelledby={tab === "sync" ? undefined : `cloud-tab-${tab}`}
      >
        {tab === "sync" ? (
          <CloudFolderPanel
            folder={folder}
            controller={controller}
            onImport={onImport}
          />
        ) : !project ? (
          <div className={styles.reviewEmpty}>
            <Sparkles size={26} />
            <h3>
              함께 생각하고,
              <br />
              함께 다듬어요.
            </h3>
            <p>
              프로젝트를 만들면 파일을 읽고
              <br />새 글과 수정안을 제안할 수 있어요.
            </p>
          </div>
        ) : tab === "chat" ? (
          <div className={cloud.chatPane}>
            <div
              ref={transcript}
              className={cloud.transcript}
              aria-label="프로젝트 대화"
              onScroll={(event) => {
                const element = event.currentTarget;
                following.current =
                  element.scrollHeight -
                    element.scrollTop -
                    element.clientHeight <
                  80;
              }}
            >
              {!project.messages.length && (
                <div className={cloud.chatWelcome}>
                  <span className={cloud.agentMark}>
                    <Sparkles size={22} strokeWidth={1.5} />
                  </span>
                  <h3>
                    글의 다음을,
                    <br />
                    함께 생각해 볼까요?
                  </h3>
                  <p>
                    프로젝트의 파일을 읽고, 필요한 자료를 살펴보고, 여러 문서의
                    수정을 제안할 수 있어요.
                  </p>
                  <button
                    onClick={() =>
                      setMessage(
                        "이 프로젝트의 문서들을 읽고 주요 내용과 다음에 보완할 점을 정리해 주세요."
                      )
                    }
                  >
                    프로젝트 문서 살펴보기 <ChevronRight size={13} />
                  </button>
                  <button
                    onClick={() =>
                      setMessage("새 문서 초안을 제안해 주세요. 주제는 ")
                    }
                  >
                    새 글 함께 시작하기 <ChevronRight size={13} />
                  </button>
                </div>
              )}
              {project.messages.map((item) => (
                <article
                  key={item.id}
                  className={`${cloud.message} ${item.role === "user" ? cloud.userMessage : cloud.agentMessage}`}
                >
                  <div className={cloud.messageLabel}>
                    {item.role === "user" ? (
                      "나"
                    ) : (
                      <>
                        <Sparkles size={12} /> Open Canvas
                      </>
                    )}
                    <time dateTime={new Date(item.createdAt).toISOString()}>
                      {new Intl.DateTimeFormat("ko-KR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      }).format(item.createdAt)}
                    </time>
                  </div>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      a: ({ href, children }) =>
                        referenceUrl(href ?? "") ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {children}
                          </a>
                        ) : (
                          <span>{children}</span>
                        ),
                      img: ({ alt }) => <span>{alt || "이미지"}</span>,
                    }}
                  >
                    {item.content}
                  </ReactMarkdown>
                </article>
              ))}
              {[...project.jobs]
                .sort((a, b) => a.createdAt - b.createdAt)
                .slice(-5)
                .map((job) => (
                  <div
                    key={job.id}
                    className={`${cloud.job} ${job.status === "failed" ? cloud.failedJob : ""}`}
                    aria-live="polite"
                  >
                    {job.status === "running" || job.status === "queued" ? (
                      <>
                        <LoaderCircle size={14} className={styles.spin} />
                        <span>
                          {job.status === "queued"
                            ? "순서를 기다리는 중…"
                            : job.kind === "research" && job.message
                              ? job.message
                              : "문서와 자료를 살펴보고 있어요…"}
                          <small>
                            다른 파일을 보거나 화면을 닫아도 작업은 이어집니다.
                          </small>
                        </span>
                      </>
                    ) : job.status === "failed" ? (
                      <div>
                        <strong>요청을 완료하지 못했습니다.</strong>
                        <p>{job.error || "잠시 후 다시 요청해 주세요."}</p>
                        <button
                          className={styles.textButton}
                          disabled={project.submitting}
                          onClick={() => {
                            const original = project.messages.find(
                              (item) =>
                                item.role === "user" && item.jobId === job.id
                            );
                            if (original) setMessage(original.content);
                          }}
                        >
                          메시지를 다시 준비
                        </button>
                      </div>
                    ) : job.proposalIds.length ? (
                      <button onClick={() => openProposal(job.proposalIds[0])}>
                        <FileDiff size={15} /> 검토할 수정안{" "}
                        {job.proposalIds.length}개 <ChevronRight size={14} />
                      </button>
                    ) : (
                      <span>
                        <CheckIcon /> 요청 완료
                      </span>
                    )}
                  </div>
                ))}
              {project.uncertainRequest && (
                <div className={styles.warningBox}>
                  <p>
                    메시지 접수 여부를 확인하지 못했습니다. 같은 요청 번호로
                    확인할 수 있어요.
                  </p>
                  <button
                    className={styles.secondaryButton}
                    disabled={project.submitting}
                    onClick={() => {
                      void controller
                        .retryRequest(project.workspace.id)
                        .catch(controller.report);
                    }}
                  >
                    요청 접수 다시 확인
                  </button>
                </div>
              )}
            </div>
            <div className={`${styles.aiComposer} ${cloud.composer}`}>
              <div className={styles.scopeLabel}>
                <span className={styles.statusDot} />
                {selected
                  ? selected.nodeId
                    ? "선택한 HTML 영역"
                    : "선택한 문장"
                  : (path ?? "프로젝트 전체")}
                <span>
                  {selected
                    ? selected.nodeId
                      ? (selected.label ?? "영역")
                      : `${selected.text.length}자`
                    : `${project.files.length}개 파일`}
                </span>
              </div>
              {selected && (
                <div className={styles.selectedPassage}>
                  <p>{selected.previewText ?? selected.text}</p>
                  <button
                    className={styles.iconButton}
                    onClick={() => onClearSelection()}
                    aria-label="선택 해제"
                  >
                    <X size={14} />
                  </button>
                </div>
              )}
              <div className={styles.quickActions}>
                <button
                  disabled={agentBusy || !document?.content.trim()}
                  onClick={() => quick("proofread")}
                >
                  <SpellCheck size={14} /> 교정
                </button>
                <button
                  disabled={agentBusy || !document?.content.trim()}
                  onClick={() => quick("clarify")}
                >
                  <WandSparkles size={14} /> 명확하게
                </button>
                <button
                  disabled={agentBusy || !document?.content.trim()}
                  onClick={() => quick("shorten")}
                >
                  <AlignLeft size={14} /> 간결하게
                </button>
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void send(message, true);
                }}
              >
                <label htmlFor="cloud-chat-message">무엇을 함께 할까요?</label>
                <div className={styles.promptInput}>
                  <textarea
                    id="cloud-chat-message"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    placeholder={
                      creationMode === "html"
                        ? "추가한 출처와 프로젝트 파일로 어떤 HTML 페이지를 만들까요?"
                        : creationMode
                          ? "조사할 주제와 관점을 적어 주세요. 결과는 새 문서 수정안으로 제안됩니다."
                          : selected?.nodeId
                            ? "예: 이 표를 카드 세 개로 바꾸고, 설명을 더 간결하게 해줘."
                            : "글을 다듬거나, 파일을 비교하거나, 새 초안을 부탁해 보세요."
                    }
                    rows={3}
                    maxLength={4000}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        (event.ctrlKey || event.metaKey) &&
                        message.trim() &&
                        !agentBusy
                      ) {
                        event.preventDefault();
                        void send(message, true);
                      }
                    }}
                  />
                  <button
                    type="submit"
                    disabled={
                      agentBusy || !message.trim() || !!project.uncertainRequest
                    }
                    aria-label="메시지 보내기"
                  >
                    {project.submitting ? (
                      <LoaderCircle size={17} className={styles.spin} />
                    ) : (
                      <ArrowUp size={17} />
                    )}
                  </button>
                </div>
              </form>
              <div className={`${styles.modelRow} ${cloud.modelRow}`}>
                <Sparkles size={12} aria-hidden="true" />
                <label className={styles.modelLabel}>
                  <span className={styles.srOnly}>AI 모델</span>
                  <select
                    aria-label="AI 모델"
                    value={catalog.model}
                    onChange={(event) => catalog.setModel(event.target.value)}
                    disabled={project.submitting}
                  >
                    {catalog.models.map((model) => (
                      <option key={model.name} value={model.name}>
                        {model.label}
                      </option>
                    ))}
                  </select>
                </label>
                <BookOpen size={12} aria-hidden="true" />
                <label className={styles.modelLabel}>
                  <span className={styles.srOnly}>작성 방식</span>
                  <select
                    aria-label="작성 방식"
                    value={creationMode}
                    onChange={(event) => {
                      if (event.target.value) onClearSelection();
                      setCreationMode(
                        event.target.value as ResearchGenre | "html" | ""
                      );
                    }}
                    disabled={project.submitting}
                    title="추가한 자료로 HTML을 만들거나, 웹을 조사해 새 문서를 작성합니다."
                  >
                    <option value="">일반 대화</option>
                    <option value="html">HTML 페이지 만들기</option>
                    <option value="paper">딥 리서치: 논문</option>
                    <option value="blog">딥 리서치: 블로그</option>
                    <option value="linkedin">딥 리서치: LinkedIn</option>
                  </select>
                </label>
              </div>
              {creationMode === "html" && (
                <p className={cloud.htmlGenerationHint}>
                  프로젝트 파일과 추가한 출처를 참고해 새 페이지를 제안합니다.
                  미리보기를 확인한 뒤 승인할 수 있어요.
                </p>
              )}
              {catalog.unavailable && (
                <button
                  className={styles.modelRetry}
                  onClick={() => {
                    void catalog.load();
                  }}
                >
                  모델 목록 연결 확인 · 다시 시도
                </button>
              )}
            </div>
          </div>
        ) : tab === "review" ? (
          <div>
            {!!project.proposals.length && (
              <div className={cloud.proposalList}>
                <p>검토할 파일을 선택하세요</p>
                {[...project.proposals]
                  .sort((a, b) => b.createdAt - a.createdAt)
                  .map((item) => (
                    <button
                      key={item.id}
                      className={
                        project.reviewId === item.id
                          ? cloud.selectedProposal
                          : ""
                      }
                      onClick={() => openProposal(item.id)}
                      aria-pressed={project.reviewId === item.id}
                    >
                      <FileText size={16} />
                      <span>
                        <strong>{item.path}</strong>
                        <small>
                          {item.pendingCount
                            ? `검토할 변경 ${item.pendingCount}개`
                            : item.status === "accepted"
                              ? "모두 승인됨"
                              : item.status === "rejected"
                                ? "모두 거절됨"
                                : "검토 완료"}
                        </small>
                      </span>
                      <ChevronRight size={14} />
                    </button>
                  ))}
              </div>
            )}
            {project.reviewId && !proposal ? (
              <p className={styles.editorLoading}>수정안을 여는 중…</p>
            ) : (
              <ReviewPanel
                document={workspaceDocument(
                  project,
                  proposal?.path ?? path,
                  proposal
                )}
                pending={false}
                deciding={!!proposal && project.deciding.includes(proposal.id)}
                savingCopy={!!proposal && project.copying.includes(proposal.id)}
                savedCopyPath={proposal?.savedCopy?.path}
                onSaveCopy={
                  proposal && proposal.baseVersion !== null
                    ? () => {
                        void controller
                          .saveProposalCopy(project.workspace.id, proposal.id)
                          .catch(controller.report);
                      }
                    : undefined
                }
                onOpenCopy={
                  proposal?.savedCopy
                    ? () => {
                        setTab("history");
                        onClearSelection();
                        void controller
                          .openFile(
                            project.workspace.id,
                            proposal.savedCopy!.path
                          )
                          .catch(controller.report);
                      }
                    : undefined
                }
                acceptedLabel="✓ 파일에 저장됨"
                activeChangeId={activeChangeId}
                onLocateChange={
                  proposal?.path === path ? onLocateChange : undefined
                }
                onCancel={() => undefined}
                onDismiss={() =>
                  controller.dismissProposal(project.workspace.id)
                }
                onDecide={(changeId, decision) => {
                  if (proposal)
                    void controller
                      .decide(
                        project.workspace.id,
                        proposal.id,
                        changeId,
                        decision
                      )
                      .then(() => onClearSelection(selection ?? null))
                      .catch(controller.report);
                }}
              />
            )}
          </div>
        ) : tab === "sources" && document ? (
          <SourcesPanel
            key={`${id}/${path}`}
            document={document}
            hasSelection={!!selected}
            selection={selected}
            html={htmlDocument}
            onAdd={(source) => {
              void controller
                .addSource(project.workspace.id, source)
                .catch(controller.report);
            }}
            onRemove={(sourceId) => {
              void controller
                .removeSource(project.workspace.id, sourceId)
                .catch(controller.report);
            }}
            onCite={(source) => {
              try {
                if (!path || !project.documents[path])
                  throw new Error("인용을 넣을 문서를 먼저 열어 주세요.");
                controller.cite(project.workspace.id, path, source, selection);
                onClearSelection();
              } catch (error) {
                controller.report(error);
              }
            }}
          />
        ) : tab === "history" && document ? (
          project.documents[path ?? ""] ? (
            <HistoryPanel
              key={`${id}/${path}`}
              document={document}
              cloud
              onRestore={onRestore}
            />
          ) : (
            <p className={styles.emptyHint}>
              파일을 열면 저장 이력을 볼 수 있습니다.
            </p>
          )
        ) : null}
      </div>
      <div className={`${styles.inspectorFooter} ${cloud.inspectorFooter}`}>
        {tab === "sync" ? (
          <button className={styles.textButton} onClick={() => setTab("chat")}>
            <MessageSquare size={13} /> 대화로 돌아가기
          </button>
        ) : (
          <>
            <ShieldCheck size={13} /> 승인한 변경만 파일에 반영합니다.
          </>
        )}
      </div>
    </aside>
  );
}

function CheckIcon() {
  return <span className={styles.statusDot} aria-hidden="true" />;
}
