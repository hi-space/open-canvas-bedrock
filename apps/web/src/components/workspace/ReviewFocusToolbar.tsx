import { useEffect, useRef } from "react";
import { LocateFixed, X } from "lucide-react";
import type { ReviewFocus } from "@/lib/workspace/types";
import styles from "./workspace.module.css";

export function ReviewFocusToolbar({
  focus,
  onReview,
  onClear,
}: {
  focus: ReviewFocus;
  onReview: () => void;
  onClear: () => void;
}) {
  const toolbar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (window.matchMedia("(max-width: 899px)").matches)
      toolbar.current?.focus({ preventScroll: true });
  }, [focus.request]);

  return (
    <div
      ref={toolbar}
      tabIndex={-1}
      className={styles.reviewFocusToolbar}
      aria-label="본문 수정 위치"
    >
      <output>
        <LocateFixed size={15} aria-hidden="true" />
        변경 {String(focus.number).padStart(2, "0")} 위치
      </output>
      <button type="button" onClick={onReview}>
        수정안 보기
      </button>
      <button type="button" onClick={onClear} aria-label="본문 강조 해제">
        <X size={15} />
      </button>
    </div>
  );
}
