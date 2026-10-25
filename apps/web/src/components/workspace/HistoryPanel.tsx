import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Columns2,
  History,
  RotateCcw,
} from "lucide-react";
import type { WorkspaceDocument } from "@/lib/workspace/types";
import { DocumentComparison } from "./DocumentComparison";
import styles from "./workspace.module.css";

export function HistoryPanel({
  document,
  onRestore,
  cloud = false,
}: {
  document: WorkspaceDocument;
  onRestore: (content: string) => void;
  cloud?: boolean;
}) {
  const [expanded, setExpanded] = useState<string>();
  const correction = document.correction;
  return (
    <div className={styles.historyPanel}>
      <div className={styles.panelIntro}>
        <History size={21} strokeWidth={1.5} />
        <h3>생각이 바뀌어도 괜찮아요.</h3>
        <p>
          {cloud
            ? "승인과 저장 시점의 파일 이력입니다. 복원한 내용은 편집기로 열리며, 저장 버튼을 눌러 반영할 수 있습니다."
            : "승인과 저장 시점의 최근 30개 버전을 보관합니다. 복원한 버전도 초안으로 열립니다."}
        </p>
      </div>
      {correction && (
        <section
          className={styles.correctionCopy}
          aria-label="보관한 교정 기록"
        >
          <strong>교정 당시의 두 문서를 보관했어요.</strong>
          <span className={styles.correctionPath}>{correction.sourcePath}</span>
          <time dateTime={new Date(correction.createdAt).toISOString()}>
            {new Intl.DateTimeFormat("ko-KR", {
              year: "numeric",
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            }).format(correction.createdAt)}
          </time>
          <p>
            이후에 편집한 내용과 별도로, 저장 당시의 원문과 전체 교정본을
            비교합니다.
          </p>
          <DocumentComparison
            key={`${document.id}/${correction.proposalId}`}
            name={document.name}
            path={document.path}
            before={{
              content: correction.baseContent,
              label: "교정 당시 원문",
              detail: correction.sourcePath,
            }}
            after={{
              content: correction.proposedContent,
              label: "저장한 교정본",
              detail: correction.path,
            }}
            description="교정 당시 원문과 저장한 전체 교정본입니다. 이후 편집이나 승인·거절은 이 비교 기록을 바꾸지 않습니다."
            trigger={
              <button type="button" className={styles.secondaryButton}>
                <Columns2 size={15} aria-hidden="true" /> 교정 전후 비교
              </button>
            }
          />
        </section>
      )}
      <ol className={styles.historyList}>
        {[...document.revisions].reverse().map((revision) => {
          const current = revision.content === document.content;
          return (
            <li key={revision.id}>
              <div className={styles.historyDot} />
              <div className={styles.historyEntry}>
                <strong>
                  {revision.label}
                  {current && <span>현재 내용</span>}
                </strong>
                <time dateTime={new Date(revision.createdAt).toISOString()}>
                  {new Intl.DateTimeFormat("ko-KR", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  }).format(revision.createdAt)}
                </time>
                <div className={styles.historyActions}>
                  {!current && (
                    <DocumentComparison
                      key={`${document.id}/${revision.id}`}
                      name={document.name}
                      path={document.path}
                      before={{
                        content: revision.content,
                        label: "이전 버전",
                        detail: new Intl.DateTimeFormat("ko-KR", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        }).format(revision.createdAt),
                      }}
                      after={{ content: document.content, label: "현재 문서" }}
                      description="선택한 저장 이력과 현재 문서를 비교합니다. 현재 문서에는 아직 저장하지 않은 편집도 포함됩니다."
                      trigger={
                        <button type="button" className={styles.textButton}>
                          <Columns2 size={13} aria-hidden="true" /> 나란히 비교
                        </button>
                      }
                    />
                  )}
                  <button
                    className={styles.textButton}
                    onClick={() =>
                      setExpanded(
                        expanded === revision.id ? undefined : revision.id
                      )
                    }
                  >
                    {expanded === revision.id ? (
                      <ChevronUp size={13} />
                    ) : (
                      <ChevronDown size={13} />
                    )}{" "}
                    내용 보기
                  </button>
                  {!current && (
                    <button
                      className={styles.textButton}
                      onClick={() => onRestore(revision.content)}
                    >
                      <RotateCcw size={13} /> 복원
                    </button>
                  )}
                </div>
                {expanded === revision.id && (
                  <pre className={styles.historyPreview}>
                    {revision.content || "(빈 문서)"}
                  </pre>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
