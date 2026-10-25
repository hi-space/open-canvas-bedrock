"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import {
  Decoration,
  EditorView,
  WidgetType,
  type ViewUpdate,
} from "@codemirror/view";
import {
  applyEditorChanges,
  editorOffsetToSource,
  sourceOffsetToEditor,
} from "@/lib/workspace/review";
import type { ReviewFocus, TextSelection } from "@/lib/workspace/types";

interface Props {
  content: string;
  onChange: (content: string) => void;
  onSelection: (selection: TextSelection) => void;
  reviewFocus?: ReviewFocus;
}

class ReviewMarker extends WidgetType {
  constructor(
    readonly number: number,
    readonly empty: boolean
  ) {
    super();
  }
  eq(other: ReviewMarker) {
    return this.number === other.number && this.empty === other.empty;
  }
  toDOM() {
    const marker = document.createElement("span");
    marker.className = "cm-review-label";
    marker.textContent = `변경 ${String(this.number).padStart(2, "0")}${this.empty ? " · 위치" : ""}`;
    return marker;
  }
}

function changedSource(content: string, update: ViewUpdate): string {
  if (update.state.doc.toString() === content.replace(/\r\n/g, "\n"))
    return content;
  const changes: { from: number; to: number; insert: string }[] = [];
  update.changes.iterChanges((from, to, _fromB, _toB, inserted) => {
    changes.push({ from, to, insert: inserted.toString() });
  });
  return applyEditorChanges(content, changes);
}

export default function MarkdownEditor({
  content,
  onChange,
  onSelection,
  reviewFocus,
}: Props) {
  const [view, setView] = useState<EditorView>();
  const revealedRequest = useRef<number | undefined>(undefined);
  const focusExtension = useMemo(() => {
    if (!reviewFocus) return [];
    const from = sourceOffsetToEditor(content, reviewFocus.from);
    const to = sourceOffsetToEditor(content, reviewFocus.to);
    return EditorView.decorations.of((editor) => {
      if (to > editor.state.doc.length) return Decoration.none;
      const firstLine = editor.state.doc.lineAt(from);
      const ranges = [
        Decoration.widget({
          widget: new ReviewMarker(reviewFocus.number, from === to),
          side: -1,
        }).range(from === to ? from : firstLine.from),
      ];
      if (from < to)
        ranges.push(
          Decoration.mark({ class: "cm-review-mark" }).range(from, to)
        );
      const lastLine = editor.state.doc.lineAt(Math.max(from, to - 1)).number;
      for (let number = firstLine.number; number <= lastLine; number++)
        ranges.push(
          Decoration.line({
            attributes: {
              class: "cm-review-line",
              "data-review-source": reviewFocus.changeId,
            },
          }).range(editor.state.doc.line(number).from)
        );
      return Decoration.set(ranges, true);
    });
  }, [content, reviewFocus]);

  useEffect(() => {
    if (!reviewFocus) {
      revealedRequest.current = undefined;
      return;
    }
    if (!view || revealedRequest.current === reviewFocus.request) return;
    revealedRequest.current = reviewFocus.request;
    view.dispatch({
      effects: EditorView.scrollIntoView(
        sourceOffsetToEditor(content, reviewFocus.from),
        { y: "center" }
      ),
    });
  }, [content, reviewFocus, view]);

  const extensions = useMemo(
    () => [
      markdown(),
      EditorView.lineWrapping,
      EditorView.contentAttributes.of({
        "aria-label": "문서 Markdown 편집기",
        "aria-multiline": "true",
        spellcheck: "true",
      }),
      EditorView.theme({
        "&": {
          background: "transparent",
          color: "#343a35",
          minHeight: "480px",
          fontSize: "15px",
        },
        "&.cm-focused": { outline: "none" },
        ".cm-content": {
          padding: "28px 0 100px",
          lineHeight: "1.9",
          fontFamily:
            "'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
        },
        ".cm-line": { padding: "0 24px 0 12px" },
        ".cm-gutters": {
          background: "transparent",
          color: "#93988f",
          border: "none",
          paddingLeft: "12px",
        },
        ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
          background: "#cfe6d9 !important",
        },
        ".cm-cursor": { borderLeftColor: "#2d6347" },
        ".cm-review-line": {
          backgroundColor: "#fff8e8",
          boxShadow: "inset 3px 0 #b47a28",
        },
        ".cm-review-mark": {
          backgroundColor: "#f9e1a9",
          borderRadius: "2px",
        },
        ".cm-review-label": {
          display: "inline-block",
          padding: "0 6px",
          marginRight: "7px",
          borderRadius: "4px",
          backgroundColor: "#89591c",
          color: "#fff",
          fontSize: "11px",
          fontFamily: "sans-serif",
          lineHeight: "1.8",
          verticalAlign: "1px",
        },
      }),
      focusExtension,
    ],
    [focusExtension]
  );

  return (
    <CodeMirror
      value={content.replace(/\r\n/g, "\n")}
      extensions={extensions}
      onCreateEditor={setView}
      basicSetup={{
        foldGutter: false,
        highlightActiveLine: false,
        highlightActiveLineGutter: false,
        autocompletion: false,
      }}
      onChange={(_value, update) => {
        const next = changedSource(content, update);
        if (next !== content) onChange(next);
      }}
      onUpdate={(update) => {
        if (!update.selectionSet && !update.docChanged && !update.focusChanged)
          return;
        if (!update.view.hasFocus) return;
        const source = update.docChanged
          ? changedSource(content, update)
          : content;
        const range = update.state.selection.main;
        const from = editorOffsetToSource(source, range.from);
        const to = editorOffsetToSource(source, range.to);
        onSelection({ from, to, text: source.slice(from, to) });
      }}
    />
  );
}
