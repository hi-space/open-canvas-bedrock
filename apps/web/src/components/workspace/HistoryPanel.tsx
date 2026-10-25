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
