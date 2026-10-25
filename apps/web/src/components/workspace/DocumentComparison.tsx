"use client";

import {
  Fragment,
  useMemo,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Columns2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Element, Root } from "hast";
import {
  comparisonRanges,
  type ComparisonRange,
} from "../../lib/workspace/comparison";
import { isHtmlFile } from "../../lib/workspace/files";
import { referenceUrl } from "../../lib/workspace/sources";
import { HtmlPreview } from "./HtmlPreview";
import workspace from "./workspace.module.css";
import styles from "./comparison.module.css";

interface ComparisonVersion {
  content: string;
  label: string;
  detail?: string;
}

interface DocumentComparisonProps {
  name: string;
  path: string;
  before: ComparisonVersion;
  after: ComparisonVersion;
  description: string;
  trigger: ReactElement;
  controls?: ReactNode;
}

const blockTags = new Set([
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "li",
  "pre",
  "td",
  "th",
  "hr",
  "img",
  "blockquote",
  "table",
]);

function highlightChanges({
  ranges,
  sourceOffset,
  side,
}: {
  ranges: ComparisonRange[];
  sourceOffset: number;
  side: "before" | "after";
}) {
  return (tree: Root) => {
    const mark = (node: Root | Element): number => {
      const start = node.position?.start.offset;
      const end = node.position?.end.offset;
      let changed = 0;
      if (start !== undefined && end !== undefined) {
        const from = start + sourceOffset;
        const to = end + sourceOffset;
        // Ranges are sorted: skip earlier changes without scanning them per block.
        let low = 0;
        let high = ranges.length;
        while (low < high) {
          const middle = (low + high) >>> 1;
          if (ranges[middle].to <= from) low = middle + 1;
          else high = middle;
        }
        for (
          let index = low;
          index < ranges.length && ranges[index].from < to;
          index++
        ) {
          changed +=
            Math.min(to, ranges[index].to) - Math.max(from, ranges[index].from);
        }
        if (!changed) return 0;
      }
      const covered = node.children.reduce(
        (total, child) => total + (child.type === "element" ? mark(child) : 0),
        0
      );
      // Prefer the smallest blocks, but keep markers/formatting outside their
      // children visible (list numbers, quote prefixes, table alignment, etc.).
      if (
        node.type === "element" &&
        blockTags.has(node.tagName) &&
        changed > covered
      ) {
        node.properties["data-comparison-change"] = side;
        return changed;
      }
      return covered;
    };
    mark(tree);
  };
}

function MarkdownVersion({
  content,
  label,
  ranges,
  side,
}: ComparisonVersion & {
  ranges: ComparisonRange[];
  side: "before" | "after";
}) {
  return (
    <div
      role="document"
      aria-label={label.endsWith("문서") ? label : `${label} 문서`}
      className={`${workspace.prose} ${styles.markdown}`}
    >
      {content.trim() ? (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[
            [
              highlightChanges,
              {
                ranges,
                sourceOffset: content.startsWith("\uFEFF") ? 1 : 0,
                side,
              },
            ],
          ]}
          skipHtml
          components={{
            a: ({ href, children }) => {
              const url = href && referenceUrl(href);
              return url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ) : (
                <span>{children}</span>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
      ) : (
        <p className={styles.empty}>내용이 없습니다.</p>
      )}
    </div>
  );
}

function SourceVersion({
  content,
  label,
  ranges,
  side,
}: ComparisonVersion & {
  ranges: ComparisonRange[];
  side: "before" | "after";
}) {
  let cursor = 0;
  const parts = ranges.map(({ from, to }) => {
    const unchanged = content.slice(cursor, from);
    cursor = to;
    return (
      <Fragment key={`${from}/${to}`}>
        {unchanged}
        {side === "before" ? (
          <del>{content.slice(from, to)}</del>
        ) : (
          <ins>{content.slice(from, to)}</ins>
        )}
      </Fragment>
    );
  });
  return (
    <pre className={styles.source} aria-label={`${label} 원문`}>
      <code>
        {parts}
        {content.slice(cursor)}
      </code>
    </pre>
  );
}

function ComparisonBody({
  path,
  before,
  after,
  controls,
}: Pick<DocumentComparisonProps, "path" | "before" | "after" | "controls">) {
  const [view, setView] = useState<"document" | "source">("document");
  const html = isHtmlFile(path);
  const ranges = useMemo(
    () => comparisonRanges(before.content, after.content),
    [before.content, after.content]
  );
  const identical = before.content === after.content;
  return (
    <>
      <div className={styles.toolbar}>
        <fieldset className={styles.viewToggle} aria-label="비교 표시 방식">
          <button
            type="button"
            aria-pressed={view === "document"}
            onClick={() => setView("document")}
          >
            문서 보기
          </button>
          <button
            type="button"
            aria-pressed={view === "source"}
            onClick={() => setView("source")}
          >
            원문 비교
          </button>
        </fieldset>
        <div className={styles.legend}>
          {identical ? (
            <output>두 버전의 내용이 같습니다.</output>
          ) : html && view === "document" ? (
            <span>HTML 화면 비교 · 원문에서 변경 확인</span>
          ) : (
            <>
              <span className={styles.removed}>삭제·수정</span>
              <span className={styles.added}>추가·수정</span>
              {view === "document" && <span>변경된 문단 강조</span>}
            </>
          )}
        </div>
      </div>
      <div className={`${styles.body} ${controls ? styles.withControls : ""}`}>
        <div className={styles.panes}>
          {(["before", "after"] as const).map((side) => {
            const version = side === "before" ? before : after;
            return (
              <section
                key={side}
                className={styles.pane}
                aria-label={`${version.label} 비교 영역`}
              >
                <header className={styles.paneHeader} data-side={side}>
                  <span className={styles.versionLabel}>{version.label}</span>
                  {version.detail && (
                    <span title={version.detail}>{version.detail}</span>
                  )}
                  <small>
                    {version.content.length.toLocaleString("ko-KR")}자
                  </small>
                </header>
                <section
                  className={styles.scroll}
                  // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Scroll panes need focus for Arrow/PageDown navigation.
                  tabIndex={0}
                  aria-label={`${version.label} 스크롤`}
                >
                  {view === "source" ? (
                    <SourceVersion
                      {...version}
                      ranges={ranges[side]}
                      side={side}
                    />
                  ) : html ? (
                    <div
                      className={styles.html}
                      aria-label={
                        version.label.endsWith("문서")
                          ? version.label
                          : `${version.label} 문서`
                      }
                    >
                      {version.content.trim() ? (
                        <HtmlPreview
                          content={version.content}
                          title={`${version.label} HTML`}
                        />
                      ) : (
                        <p className={styles.empty}>내용이 없습니다.</p>
                      )}
                    </div>
                  ) : (
                    <MarkdownVersion
                      {...version}
                      ranges={ranges[side]}
                      side={side}
                    />
                  )}
                </section>
              </section>
            );
          })}
        </div>
        {controls && (
          <aside className={styles.controls} aria-label="비교 중 수정안 검토">
            <h3>수정안 검토</h3>
            {controls}
          </aside>
        )}
      </div>
    </>
  );
}

export function DocumentComparison({
  name,
  description,
  trigger,
  ...body
}: DocumentComparisonProps) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content className={styles.dialog}>
          <header className={styles.header}>
            <Columns2 size={24} strokeWidth={1.5} aria-hidden="true" />
            <div className={styles.identity}>
              <Dialog.Title className={styles.title}>
                {name} <span>버전 비교</span>
              </Dialog.Title>
              <Dialog.Description className={styles.description}>
                {description}
              </Dialog.Description>
            </div>
            <Dialog.Close className={styles.close} aria-label="비교 닫기">
              <X size={18} aria-hidden="true" /> 닫기
            </Dialog.Close>
          </header>
          <ComparisonBody {...body} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
