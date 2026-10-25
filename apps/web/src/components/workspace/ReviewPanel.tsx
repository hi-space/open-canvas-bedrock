import { useMemo } from "react";
import DiffMatchPatch from "diff-match-patch";
import {
  Check,
  CheckCheck,
  CircleCheck,
  FileDiff,
  LoaderCircle,
  ShieldCheck,
  X,
} from "lucide-react";
import { reviewedContent } from "@/lib/workspace/review";
import type { ReviewChange, WorkspaceDocument } from "@/lib/workspace/types";
import styles from "./workspace.module.css";

function DiffText({
  before,
  after,
  side,
  prefix = "",
  suffix = "",
}: {
  before: string;
  after: string;
  side: "before" | "after";
  prefix?: string;
  suffix?: string;
}) {
  const parts = useMemo(() => {
    const engine = new DiffMatchPatch();
    const diff = engine.diff_main(before, after);
    engine.diff_cleanupSemantic(diff);
    return diff;
  }, [before, after]);
  return (
    <span>
      {prefix}
      {parts
        .filter(([operation]) =>
          side === "before" ? operation !== 1 : operation !== -1
        )
        .map(([operation, text], index) =>
          operation === 0 ? (
            <span key={index}>{text}</span>
          ) : side === "before" ? (
            <del key={index}>{text}</del>
          ) : (
            <ins key={index}>{text}</ins>
          )
        )}
      {!(side === "before" ? before : after) && !prefix && !suffix && (
        <em>{side === "before" ? "새로 추가" : "삭제됨"}</em>
      )}
      {suffix}
    </span>
  );
}

function ContextualDiff({
  base,
  change,
  side,
}: {
  base: string;
  change: ReviewChange;
  side: "before" | "after";
}) {
  const lineStart = base.lastIndexOf("\n", change.from - 1) + 1;
  const lineEnd = base.indexOf("\n", change.to);
  const prefix = Array.from(base.slice(lineStart, change.from))
    .slice(-70)
    .join("");
  const suffix = Array.from(
    base.slice(change.to, lineEnd < 0 ? base.length : lineEnd)
  )
    .slice(0, 70)
    .join("");
  return (
    <DiffText
      before={change.before}
      after={change.after}
      side={side}
      prefix={prefix}
      suffix={suffix}
    />
  );
}

export function ReviewPanel({
  document,
  pending,
  onDecide,
  onDismiss,
  onCancel,
  deciding = false,
  acceptedLabel = "✓ 초안에 반영됨",
}: {
  document: WorkspaceDocument;
  pending: boolean;
  onDecide: (changeId: string, decision: "accepted" | "rejected") => void;
  onDismiss: () => void;
  onCancel: () => void;
  deciding?: boolean;
  acceptedLabel?: string;
}) {
  const proposal = document.proposal;
  const remaining =
    proposal?.changes.filter((change) => change.decision === "pending")
      .length ?? 0;
  const stale =
    proposal &&
    (reviewedContent(proposal) !== document.content ||
      (proposal.kind === "external" &&
        remaining > 0 &&
        document.external?.content !== proposal.proposedContent));

  if (pending)
    return (
      <div className={styles.reviewLoading} aria-live="polite">
        <LoaderCircle size={25} className={styles.spin} />
        <strong>문장을 다듬고 있어요</strong>
        <p>완성된 수정안을 이곳에 보여드릴게요.</p>
        <div className={styles.loadingLines}>
          <span />
          <span />
          <span />
        </div>
        <button className={styles.textButton} onClick={onCancel}>
          요청 취소
        </button>
      </div>
    );

  if (!proposal)
    return (
      <div className={styles.reviewEmpty}>
        <div className={styles.reviewEmptyIcon}>
          <FileDiff size={26} strokeWidth={1.3} />
        </div>
        <h3>
          수정은 제안으로,
          <br />
          결정은 내 손으로.
        </h3>
        <p>
          문장을 선택하거나 수정 방향을 알려주세요.
          <br />
          원문과 수정안을 비교하고 반영할 수 있어요.
        </p>
        <div className={styles.approvalNote}>
          <ShieldCheck size={14} /> 승인하기 전에는 본문이 바뀌지 않습니다.
        </div>
      </div>
    );

  const accepted = proposal.changes.filter(
    (change) => change.decision === "accepted"
  ).length;
  return (
    <div className={styles.reviewPanel}>
      <div className={styles.reviewHeading}>
        <span>
          {proposal.kind === "external" ? "외부 파일 변경" : "AI 수정 제안"}
        </span>
        <span className={styles.countBadge}>
          {remaining || proposal.changes.length}
        </span>
      </div>
      {proposal.explanation && (
        <p className={styles.explanation}>{proposal.explanation}</p>
      )}
      {!!stale && remaining > 0 && (
        <div className={styles.warningBox} role="alert">
          검토 중 원문이나 외부 파일이 변경되었습니다. 현재 내용으로 다시 요청해
          주세요.
          <button className={styles.textButton} onClick={onDismiss}>
            이 수정안 닫기
          </button>
        </div>
      )}
      {remaining > 0 ? (
        <div className={styles.reviewBulkActions}>
          <button
            className={styles.acceptButton}
            disabled={!!stale || deciding}
            onClick={() => onDecide("all", "accepted")}
          >
            <CheckCheck size={15} /> 모두 승인
          </button>
          <button
            className={styles.secondaryButton}
            disabled={deciding}
            onClick={() => onDecide("all", "rejected")}
          >
            모두 거절
          </button>
        </div>
      ) : (
        <div className={styles.reviewComplete}>
          <CircleCheck size={17} />
          <span>검토 완료 · {accepted}개 반영</span>
          <button onClick={onDismiss}>닫기</button>
        </div>
      )}
      <div className={styles.changeList}>
        {proposal.changes.map((change, index) => (
          <article
            key={change.id}
            className={`${styles.changeCard} ${change.decision !== "pending" ? styles.changeResolved : ""}`}
          >
            <div className={styles.changeHeader}>
              <span>변경 {String(index + 1).padStart(2, "0")}</span>
              <span>
                {proposal.baseContent.slice(0, change.from).split("\n").length}
                행
              </span>
            </div>
            <div className={styles.changeBefore}>
              <span className={styles.diffLabel}>수정 전</span>
              <div>
                <ContextualDiff
                  base={proposal.baseContent}
                  change={change}
                  side="before"
                />
              </div>
            </div>
            <div className={styles.changeAfter}>
              <span className={styles.diffLabel}>수정 후</span>
              <div>
                <ContextualDiff
                  base={proposal.baseContent}
                  change={change}
                  side="after"
                />
              </div>
            </div>
            <div className={styles.changeActions}>
              {change.decision === "pending" ? (
                <>
                  <button
                    className={styles.textButton}
                    disabled={deciding}
                    onClick={() => onDecide(change.id, "rejected")}
                    aria-label={`변경 ${index + 1} 거절`}
                  >
                    <X size={14} /> 거절
                  </button>
                  <button
                    className={styles.acceptButton}
                    disabled={!!stale || deciding}
                    onClick={() => onDecide(change.id, "accepted")}
                    aria-label={`변경 ${index + 1} 승인`}
                  >
                    <Check size={14} /> 승인
                  </button>
                </>
              ) : (
                <span>
                  {change.decision === "accepted"
                    ? acceptedLabel
                    : "거절한 변경"}
                </span>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
