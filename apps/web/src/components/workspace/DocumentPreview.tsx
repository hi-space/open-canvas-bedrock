"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUpRight, TextSelect } from "lucide-react";
import { referenceUrl } from "@/lib/workspace/sources";
import { mapRenderedSelection } from "@/lib/workspace/selection";
import type { ReviewFocus, TextSelection } from "@/lib/workspace/types";
import styles from "./workspace.module.css";

interface PositionNode {
  position?: { start: { offset?: number }; end: { offset?: number } };
}

function attributes(node: PositionNode | undefined, sourceOffset: number) {
  return {
    "data-source-start":
      node?.position?.start.offset === undefined
        ? undefined
        : node.position.start.offset + sourceOffset,
    "data-source-end":
      node?.position?.end.offset === undefined
        ? undefined
        : node.position.end.offset + sourceOffset,
  };
}

export function DocumentPreview({
  content,
  onSelection,
  reviewFocus,
  onSourceUnavailable,
}: {
  content: string;
  onSelection: (selection: TextSelection | undefined) => void;
  reviewFocus?: ReviewFocus;
  onSourceUnavailable: () => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const revealedRequest = useRef<number | undefined>(undefined);
  const [hint, setHint] = useState(false);
  const sourceOffset = content.startsWith("\uFEFF") ? 1 : 0;

  // Markdown components can remount on a parent render. Reapply the visual
  // annotations, but scroll only in response to an explicit location request.
  useEffect(() => {
    if (!root.current || !reviewFocus) {
      revealedRequest.current = undefined;
      return;
    }
    const blocks = Array.from(
      root.current.querySelectorAll<HTMLElement>("[data-source-start]")
    );
    const matches = blocks.filter((block) => {
      const from = Number(block.dataset.sourceStart);
      const to = Number(block.dataset.sourceEnd);
      return reviewFocus.from === reviewFocus.to
        ? from <= reviewFocus.from && to >= reviewFocus.from
        : from < reviewFocus.to && to > reviewFocus.from;
    });
    // Prefer paragraphs/cells over their enclosing lists, quotes, or tables.
    const targets = matches.filter(
      (block) =>
        !matches.some((other) => other !== block && block.contains(other))
    );
    if (!targets.length) {
      // Definitions and skipped HTML have source positions but no reading block.
      // A nonempty change must be shown in the source, not on a nearby paragraph.
      if (reviewFocus.from < reviewFocus.to) {
        onSourceUnavailable();
        return;
      }
      const next = blocks.find(
        (block) => Number(block.dataset.sourceStart) >= reviewFocus.from
      );
      targets.push(next ?? blocks.at(-1) ?? root.current);
    }
    targets.forEach((block) => {
      block.classList.add(styles.reviewSourceHighlight);
      block.dataset.reviewSource = reviewFocus.changeId;
    });
    const anchor = targets[0];
    anchor.dataset.reviewLabel = `변경 ${String(reviewFocus.number).padStart(2, "0")}${reviewFocus.from === reviewFocus.to ? " · 추가·삭제 위치" : ""}`;
    let frame: number | undefined;
    if (revealedRequest.current !== reviewFocus.request) {
      frame = requestAnimationFrame(() => {
        revealedRequest.current = reviewFocus.request;
        anchor.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "instant"
            : "smooth",
          block: "center",
          inline: "nearest",
        });
      });
    }
    return () => {
      if (frame !== undefined) cancelAnimationFrame(frame);
      targets.forEach((block) => {
        block.classList.remove(styles.reviewSourceHighlight);
        delete block.dataset.reviewSource;
        delete block.dataset.reviewLabel;
      });
    };
  });

  const captureSelection = useCallback(() => {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !root.current) return;
    const range = selection.getRangeAt(0);
    const selected = range.toString();
    if (
      !selected.trim() ||
      !root.current.contains(range.commonAncestorContainer)
    )
      return;
    const element =
      range.startContainer instanceof Element
        ? range.startContainer
        : range.startContainer.parentElement;
    const block = element?.closest<HTMLElement>("[data-source-start]");
    if (!block || !block.contains(range.endContainer)) {
      onSelection(undefined);
      setHint(true);
      return;
    }
    const from = Number(block.dataset.sourceStart);
    const to = Number(block.dataset.sourceEnd);
    if (!Number.isFinite(from) || !Number.isFinite(to)) return;
    const prefix = range.cloneRange();
    prefix.selectNodeContents(block);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = prefix.toString().length;
    const mapped = mapRenderedSelection(
      content,
      { from, to, text: block.textContent ?? "" },
      start,
      start + selected.length
    );
    if (!mapped) {
      onSelection(undefined);
      setHint(true);
      return;
    }
    onSelection(mapped);
    setHint(false);
  }, [content, onSelection]);

  useEffect(() => {
    const element = root.current;
    if (!element) return;
    // Observe native selection; the reading surface remains a document, not a button.
    element.addEventListener("mouseup", captureSelection);
    element.addEventListener("keyup", captureSelection);
    return () => {
      element.removeEventListener("mouseup", captureSelection);
      element.removeEventListener("keyup", captureSelection);
    };
  }, [captureSelection]);

  const selectParagraph = (node?: PositionNode) => {
    const from = node?.position?.start.offset;
    const to = node?.position?.end.offset;
    if (from === undefined || to === undefined) return;
    onSelection({
      from: from + sourceOffset,
      to: to + sourceOffset,
      text: content.slice(from + sourceOffset, to + sourceOffset),
    });
    setHint(false);
  };

  return (
    <div
      ref={root}
      role="document"
      aria-label="문서 읽기"
      className={styles.prose}
    >
      {hint && (
        <div className={styles.selectionHint} aria-live="polite">
          여러 문단이나 서식을 걸쳐 선택할 때는 Markdown 편집에서 선택해 주세요.
          <button
            type="button"
            onClick={() => setHint(false)}
            aria-label="선택 안내 닫기"
          >
            닫기
          </button>
        </div>
      )}
      {content.trim() ? (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          skipHtml
          components={{
            p: ({ node, children }) => (
              <div className={styles.paragraph}>
                <p {...attributes(node, sourceOffset)}>{children}</p>
                <button
                  type="button"
                  className={styles.paragraphAction}
                  onClick={() => selectParagraph(node)}
                  title="이 문단 선택"
                  aria-label="이 문단을 AI 교정 대상으로 선택"
                >
                  <TextSelect size={15} />
                </button>
              </div>
            ),
            h1: ({ node, children }) => (
              <h1 {...attributes(node, sourceOffset)}>{children}</h1>
            ),
            h2: ({ node, children }) => (
              <h2 {...attributes(node, sourceOffset)}>{children}</h2>
            ),
            h3: ({ node, children }) => (
              <h3 {...attributes(node, sourceOffset)}>{children}</h3>
            ),
            h4: ({ node, children }) => (
              <h4 {...attributes(node, sourceOffset)}>{children}</h4>
            ),
            h5: ({ node, children }) => (
              <h5 {...attributes(node, sourceOffset)}>{children}</h5>
            ),
            h6: ({ node, children }) => (
              <h6 {...attributes(node, sourceOffset)}>{children}</h6>
            ),
            li: ({ node, children }) => (
              <li {...attributes(node, sourceOffset)}>{children}</li>
            ),
            blockquote: ({ node, children }) => (
              <blockquote {...attributes(node, sourceOffset)}>
                {children}
              </blockquote>
            ),
            pre: ({ node, children }) => (
              <pre {...attributes(node, sourceOffset)}>{children}</pre>
            ),
            table: ({ node, children }) => (
              <table {...attributes(node, sourceOffset)}>{children}</table>
            ),
            tr: ({ node, children }) => (
              <tr {...attributes(node, sourceOffset)}>{children}</tr>
            ),
            hr: ({ node }) => <hr {...attributes(node, sourceOffset)} />,
            a: ({ href, title, children }) => {
              if (href?.startsWith("#"))
                return (
                  <a href={href} title={title}>
                    {children}
                  </a>
                );
              const safeUrl = href && referenceUrl(href);
              if (!safeUrl) return <span title={href}>{children}</span>;
              const numeric = /^\d+$/.test(String(children));
              return (
                <a
                  href={safeUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={title || safeUrl}
                  className={numeric ? styles.citation : undefined}
                  aria-label={
                    numeric
                      ? `출처 ${String(children)} 새 탭에서 열기`
                      : undefined
                  }
                  data-source-link="true"
                >
                  {children}
                  {!numeric && <ArrowUpRight size={11} aria-hidden="true" />}
                </a>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
      ) : (
        <div className={styles.emptyDocument}>
          <span className={styles.eyebrow}>A SPACE FOR YOUR NEXT IDEA</span>
          <h1>
            어떤 이야기를
            <br />
            시작할까요?
          </h1>
          <p>
            Markdown 편집에서 생각을 적어보세요.
            <br />
            오른쪽에서 AI에게 초안 작성을 부탁할 수도 있습니다.
          </p>
        </div>
      )}
    </div>
  );
}
