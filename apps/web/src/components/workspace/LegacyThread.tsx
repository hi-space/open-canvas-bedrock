import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, History, LoaderCircle, X } from "lucide-react";
import type { Artifact } from "@/shared/types";
import { getArtifactContent } from "@/shared/utils/artifacts";
import { downloadMarkdown } from "@/lib/workspace/files";
import { referenceUrl } from "@/lib/workspace/sources";
import type { CloudWorkspaceController } from "@/lib/workspace/cloud-state";
import styles from "./workspace.module.css";
import cloud from "./cloud.module.css";

interface LegacyData {
  values?: {
    messages?: {
      id?: string;
      role?: string;
      type?: string;
      content?: string | { type?: string; text?: string }[];
    }[];
    artifact?: Artifact;
  };
  metadata?: { title?: string };
}

export function LegacyThread({
  threadId,
  controller,
  workspaceId,
}: {
  threadId: string;
  controller: CloudWorkspaceController;
  workspaceId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<LegacyData>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [filename, setFilename] = useState("이전 대화 문서.md");
  const [attempt, setAttempt] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  useEffect(() => {
    if (!open || data) return;
    const request = new AbortController();
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const response = await fetch(
          `/api/threads/${encodeURIComponent(threadId)}`,
          {
            signal: request.signal,
            credentials: "same-origin",
            cache: "no-store",
          }
        );
        const result = await response.json().catch(() => undefined);
        if (!response.ok || !result?.values)
          throw new Error(result?.detail || "이전 대화를 읽지 못했습니다.");
        setData(result as LegacyData);
      } catch (failure) {
        if (!request.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "이전 대화를 읽지 못했습니다."
          );
      } finally {
        if (!request.signal.aborted) setLoading(false);
      }
    })();
    return () => request.abort();
  }, [attempt, data, open, threadId]);

  const artifact = data?.values?.artifact;
  const current =
    Array.isArray(artifact?.contents) && artifact.contents.length
      ? getArtifactContent(artifact)
      : undefined;
  const content =
    current?.type === "text"
      ? current.fullMarkdown
      : current?.type === "code"
        ? current.code
        : "";
  const messages = (data?.values?.messages ?? []).filter((message) =>
    ["human", "user", "ai", "assistant"].includes(
      message.type ?? message.role ?? ""
    )
  );
  const text = (message: (typeof messages)[number]) =>
    typeof message.content === "string"
      ? message.content
      : (message.content ?? [])
          .filter(
            (block) =>
              typeof block.text === "string" &&
              (!block.type ||
                ["text", "input_text", "output_text"].includes(block.type))
          )
          .map((block) => block.text)
          .join("\n");
  return (
    <>
      <div className={cloud.legacyBanner}>
        <History size={15} />
        <span>이전 대화 링크로 들어오셨네요.</span>
        <button className={styles.textButton} onClick={() => setOpen(true)}>
          이전 대화 열기
        </button>
      </div>
      <dialog
        ref={dialog}
        className={`${cloud.modal} ${cloud.legacyModal}`}
        aria-labelledby="legacy-thread-title"
        onCancel={() => setOpen(false)}
        onClose={() => setOpen(false)}
      >
        <header>
          <div>
            <span className={cloud.eyebrow}>PREVIOUS CONVERSATION</span>
            <h2 id="legacy-thread-title">
              {data?.metadata?.title || "이전 대화"}
            </h2>
          </div>
          <button
            className={styles.iconButton}
            onClick={() => setOpen(false)}
            aria-label="이전 대화 닫기"
          >
            <X size={20} />
          </button>
        </header>
        <p>
          기존 대화와 문서를 읽고, 현재 프로젝트에서 이어서 작성할 수 있습니다.
        </p>
        {loading && (
          <p aria-live="polite">
            <LoaderCircle className={styles.spin} size={17} /> 이전 대화를
            불러오는 중…
          </p>
        )}
        {error && (
          <div role="alert" className={styles.warningBox}>
            {error}
            <button
              className={styles.textButton}
              onClick={() => setAttempt((value) => value + 1)}
            >
              다시 시도
            </button>
          </div>
        )}
        <div className={cloud.legacyContent}>
          {messages.map((message, index) => (
            <article key={message.id ?? index} className={cloud.legacyMessage}>
              <strong>
                {["human", "user"].includes(message.type ?? message.role ?? "")
                  ? "나"
                  : "Open Canvas"}
              </strong>
              <p>{text(message)}</p>
            </article>
          ))}
          {current && (
            <article className={cloud.legacyArtifact}>
              <h3>{current.title || "이전 문서"}</h3>
              {current.type === "code" ? (
                <pre>{content}</pre>
              ) : (
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
                    img: ({ alt }) => <span>{alt}</span>,
                  }}
                >
                  {content}
                </ReactMarkdown>
              )}
            </article>
          )}
        </div>
        {data && (
          <div className={cloud.legacyActions}>
            <button
              className={styles.secondaryButton}
              onClick={() =>
                downloadMarkdown(
                  "이전 대화.md",
                  messages
                    .map(
                      (message) =>
                        `## ${["human", "user"].includes(message.type ?? message.role ?? "") ? "나" : "Open Canvas"}\n\n${text(message)}`
                    )
                    .join("\n\n") +
                    (current ? `\n\n# ${current.title}\n\n${content}` : "")
                )
              }
            >
              <Download size={14} /> 대화 다운로드
            </button>
            {current && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!workspaceId) return;
                  setImporting(true);
                  void controller
                    .createFile(workspaceId, filename.trim(), content)
                    .then(() => {
                      controller.notify("이전 문서를 프로젝트에 가져왔습니다.");
                      setOpen(false);
                    })
                    .catch((failure: unknown) =>
                      setError(
                        failure instanceof Error
                          ? failure.message
                          : "가져오기를 완료하지 못했습니다."
                      )
                    )
                    .finally(() => setImporting(false));
                }}
              >
                <label>
                  가져올 파일 이름
                  <input
                    value={filename}
                    onChange={(event) => setFilename(event.target.value)}
                    required
                  />
                </label>
                <button
                  className={styles.acceptButton}
                  disabled={!workspaceId || importing}
                >
                  {importing ? "가져오는 중…" : "프로젝트에 문서로 가져오기"}
                </button>
                {!workspaceId && (
                  <small>프로젝트를 먼저 만든 뒤 가져올 수 있습니다.</small>
                )}
              </form>
            )}
          </div>
        )}
      </dialog>
    </>
  );
}
