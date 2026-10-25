"use client";

import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { EditorView, type ViewUpdate } from "@codemirror/view";
import {
  applyEditorChanges,
  editorOffsetToSource,
} from "@/lib/workspace/review";
import type { TextSelection } from "@/lib/workspace/types";

interface Props {
  content: string;
  onChange: (content: string) => void;
  onSelection: (selection: TextSelection) => void;
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
}: Props) {
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
      }),
    ],
    []
  );

  return (
    <CodeMirror
      value={content.replace(/\r\n/g, "\n")}
      extensions={extensions}
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
