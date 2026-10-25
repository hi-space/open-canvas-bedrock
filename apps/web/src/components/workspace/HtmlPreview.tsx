"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { CornerLeftUp, MousePointer2, X } from "lucide-react";
import {
  createHtmlPreview,
  htmlRegions,
  selectionForHtmlMessage,
  type HtmlRegion,
} from "../../lib/workspace/html";
import { chooseDefaultHtmlRegion } from "../../lib/workspace/html-selection-policy";
import { resolveHtmlResearchImages } from "../../lib/workspace/html-assets";
import type { TextSelection } from "../../lib/workspace/types";
import styles from "./html.module.css";

export interface HtmlPreviewProps {
  content: string;
  onSelection?: (selection: TextSelection | undefined) => void;
  selection?: TextSelection;
  title?: string;
  compact?: boolean;
  fill?: boolean;
}

interface PreviewSession {
  content: string;
  interactive: boolean;
  token: string;
  source?: string;
  error?: string;
  missing?: number;
}

export function HtmlPreview({
  content,
  onSelection,
  selection,
  title = "HTML 문서 미리보기",
  compact = false,
  fill = false,
}: HtmlPreviewProps) {
  const frame = useRef<HTMLIFrameElement>(null);
  const pickerId = useId();
  const hintId = useId();
  const interactive = !!onSelection && !compact;
  const regions = useMemo(() => htmlRegions(content), [content]);
  const regionMap = useMemo(
    () => new Map(regions.map((region) => [region.nodeId, region])),
    [regions]
  );
  const selected = selection?.nodeId
    ? regionMap.get(selection.nodeId)
    : undefined;
  const currentSelection =
    selected &&
    selected.from === selection?.from &&
    selected.to === selection.to &&
    selected.text === selection.text
      ? selected
      : undefined;
  const parent = currentSelection?.parentId
    ? regionMap.get(currentSelection.parentId)
    : undefined;
  const [preview, setPreview] = useState<PreviewSession>();
  const [imageRetry, setImageRetry] = useState(0);
  const currentPreview =
    preview?.content === content && preview.interactive === interactive
      ? preview
      : undefined;

  // DOMPurify needs the browser's window. Keep server rendering deterministic.
  useEffect(() => {
    const token = window.crypto.randomUUID();
    const controller = new AbortController();
    try {
      setPreview({
        content,
        interactive,
        token,
        source: createHtmlPreview(content, token, interactive),
      });
      void resolveHtmlResearchImages(content, controller.signal)
        .then((resolved) => {
          if (controller.signal.aborted) return;
          setPreview({
            content,
            interactive,
            token,
            source: createHtmlPreview(resolved.content, token, interactive),
            missing: resolved.missing.length,
          });
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setPreview((current) =>
            current?.token === token ? { ...current, missing: 1 } : current
          );
        });
    } catch {
      setPreview({
        content,
        interactive,
        token,
        error:
          "HTML 미리보기를 준비하지 못했어요. 소스에서 내용을 확인해 주세요.",
      });
    }
    return () => controller.abort();
  }, [content, interactive, imageRetry]);

  const chooseRegion = useCallback(
    (region?: HtmlRegion) => {
      if (!interactive) return;
      if (!region) {
        onSelection?.(undefined);
        return;
      }
      const { from, to, text, nodeId, label, previewText, sourceIds } = region;
      onSelection?.({
        from,
        to,
        text,
        nodeId,
        label,
        previewText,
        sourceIds,
      });
    },
    [interactive, onSelection]
  );

  const syncHighlight = useCallback(() => {
    if (!interactive || !currentPreview?.source) return;
    // An opaque sandbox origin requires "*"; the bridge checks source + token.
    frame.current?.contentWindow?.postMessage(
      {
        type: "oc-html-highlight",
        token: currentPreview.token,
        nodeId: currentSelection?.nodeId ?? null,
      },
      "*"
    );
  }, [interactive, currentPreview, currentSelection?.nodeId]);

  useEffect(syncHighlight, [syncHighlight]);

  useEffect(() => {
    if (!interactive || !currentPreview?.source) return;
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return;
      const resolved = selectionForHtmlMessage(
        event.data,
        currentPreview.token,
        content
      );
      if (!resolved?.nodeId) return;
      const candidates: HtmlRegion[] = [];
      let region = regionMap.get(resolved.nodeId);
      while (region) {
        candidates.push(region);
        region = region.parentId ? regionMap.get(region.parentId) : undefined;
      }
      const choice = chooseDefaultHtmlRegion(candidates);
      if (choice && candidates.includes(choice)) chooseRegion(choice);
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [content, currentPreview, interactive, regionMap, chooseRegion]);

  return (
    <section
      className={`${styles.preview} ${compact ? styles.compact : ""} ${fill && !compact ? styles.fill : ""}`}
      aria-label={title}
    >
      {interactive && (
        <div className={styles.controls}>
          <div className={styles.pickerHeading}>
            <label htmlFor={pickerId}>영역 선택</label>
            <span>{regions.length}개 영역</span>
          </div>
          <div className={styles.pickerRow}>
            <select
              id={pickerId}
              value={currentSelection?.nodeId ?? ""}
              aria-describedby={hintId}
              disabled={!regions.length}
              onChange={(event) =>
                chooseRegion(regionMap.get(event.currentTarget.value))
              }
            >
              <option value="">선택한 영역 없음</option>
              {regions.map((region, index) => (
                <option key={region.nodeId} value={region.nodeId}>
                  {index + 1}. {region.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              aria-label="상위 영역 선택"
              title={parent ? parent.label : "상위 영역이 없어요"}
              disabled={!parent}
              onClick={() => chooseRegion(parent)}
            >
              <CornerLeftUp size={15} aria-hidden="true" />
              <span>상위 영역</span>
            </button>
            <button
              type="button"
              aria-label="선택 해제"
              disabled={!currentSelection}
              onClick={() => chooseRegion()}
            >
              <X size={15} aria-hidden="true" />
              <span>해제</span>
            </button>
          </div>
          <output
            id={hintId}
            className={`${styles.selection} ${currentSelection ? styles.hasSelection : ""}`}
            aria-live="polite"
            aria-atomic="true"
          >
            <MousePointer2 size={13} aria-hidden="true" />
            {currentSelection ? (
              <span>
                <span className={styles.selectionCaption}>선택한 영역</span>
                <strong>{currentSelection.label}</strong>
              </span>
            ) : (
              <span>
                {regions.length
                  ? "미리보기의 요소를 누르거나 목록에서 영역을 선택하세요."
                  : "HTML 소스를 저장하면 편집할 영역을 선택할 수 있어요."}
              </span>
            )}
          </output>
        </div>
      )}
      {!!currentPreview?.missing && (
        <output className={styles.imageNotice}>
          <span>
            그림 {currentPreview.missing}개를 불러오지 못했어요. 본문은 계속
            읽을 수 있습니다.
          </span>
          <button
            type="button"
            onClick={() => setImageRetry((value) => value + 1)}
          >
            그림 다시 불러오기
          </button>
        </output>
      )}
      <div className={styles.frameShell}>
        {currentPreview?.source ? (
          <iframe
            key={currentPreview.token}
            ref={frame}
            className={styles.frame}
            title={title}
            srcDoc={currentPreview.source}
            sandbox={interactive ? "allow-scripts" : ""}
            referrerPolicy="no-referrer"
            onLoad={syncHighlight}
          />
        ) : (
          <div
            className={styles.placeholder}
            role={currentPreview?.error ? "alert" : "status"}
          >
            {currentPreview?.error ?? "HTML 미리보기를 준비하고 있어요."}
          </div>
        )}
      </div>
    </section>
  );
}

export default HtmlPreview;
