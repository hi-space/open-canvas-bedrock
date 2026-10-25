import DiffMatchPatch from "diff-match-patch";
import type {
  ChangeDecision,
  ReviewChange,
  ReviewLocation,
  ReviewProposal,
  TextSelection,
} from "./types";

function buildChanges(before: string, after: string): ReviewChange[] {
  const engine = new DiffMatchPatch();
  const diffs = engine.diff_main(before, after);
  engine.diff_cleanupSemantic(diffs);
  const changes: ReviewChange[] = [];
  let offset = 0;
  let current: ReviewChange | undefined;

  const finish = () => {
    if (!current) return;
    // diff-match-patch uses UTF-16. Include both halves of a changed emoji.
    if (
      current.from > 0 &&
      /[\uDC00-\uDFFF]/.test(before[current.from] ?? "") &&
      /[\uD800-\uDBFF]/.test(before[current.from - 1])
    ) {
      current.from--;
      current.before = before[current.from] + current.before;
      current.after = before[current.from] + current.after;
    }
    if (
      /[\uD800-\uDBFF]/.test(before[current.to - 1] ?? "") &&
      /[\uDC00-\uDFFF]/.test(before[current.to] ?? "")
    ) {
      current.before += before[current.to];
      current.after += before[current.to];
      current.to++;
    }
    changes.push(current);
    current = undefined;
  };

  diffs.forEach(([operation, text], index) => {
    if (operation === 0) {
      // Keep nearby edits together, but let separate paragraphs be reviewed alone.
      if (
        current &&
        index < diffs.length - 1 &&
        text.length <= 24 &&
        !/\n\s*\n/.test(text)
      ) {
        current.before += text;
        current.after += text;
        current.to += text.length;
      } else {
        finish();
      }
      offset += text.length;
      return;
    }
    current ??= {
      id: crypto.randomUUID(),
      from: offset,
      to: offset,
      before: "",
      after: "",
      decision: "pending",
    };
    if (operation === -1) {
      current.before += text;
      current.to += text.length;
      offset += text.length;
    } else {
      current.after += text;
    }
  });
  finish();
  return changes;
}

export function createProposal(
  baseContent: string,
  replacement: string,
  options: {
    selection?: TextSelection;
    kind?: ReviewProposal["kind"];
    instruction?: string;
    explanation?: string;
  } = {}
): ReviewProposal {
  const { selection } = options;
  if (
    selection &&
    (!Number.isInteger(selection.from) ||
      !Number.isInteger(selection.to) ||
      selection.from < 0 ||
      selection.to <= selection.from ||
      selection.to > baseContent.length ||
      baseContent.slice(selection.from, selection.to) !== selection.text)
  ) {
    throw new Error("선택한 내용이 달라졌습니다. 문장을 다시 선택해 주세요.");
  }
  const proposedContent = selection
    ? baseContent.slice(0, selection.from) +
      replacement +
      baseContent.slice(selection.to)
    : replacement;
  return {
    id: crypto.randomUUID(),
    kind: options.kind ?? "ai",
    instruction: options.instruction ?? "",
    explanation: options.explanation ?? "",
    baseContent,
    proposedContent,
    changes: selection
      ? buildChanges(selection.text, replacement).map((change) => ({
          ...change,
          from: change.from + selection.from,
          to: change.to + selection.from,
        }))
      : buildChanges(baseContent, proposedContent),
    createdAt: Date.now(),
  };
}

export function reviewedContent(proposal: ReviewProposal): string {
  let result = "";
  let cursor = 0;
  for (const change of proposal.changes) {
    result += proposal.baseContent.slice(cursor, change.from);
    result += change.decision === "accepted" ? change.after : change.before;
    cursor = change.to;
  }
  return result + proposal.baseContent.slice(cursor);
}

export function reviewLocations(
  content: string,
  proposal: ReviewProposal | undefined
): ReviewLocation[] {
  if (!proposal || reviewedContent(proposal) !== content) return [];
  let offset = 0;
  return proposal.changes.map((change, index) => {
    const from = change.from + offset;
    const text = change.decision === "accepted" ? change.after : change.before;
    offset += text.length - change.before.length;
    return {
      changeId: change.id,
      number: index + 1,
      from,
      to: from + text.length,
    };
  });
}

export function decideChanges(
  content: string,
  proposal: ReviewProposal,
  changeId: string | "all",
  decision: Exclude<ChangeDecision, "pending">
): { content: string; proposal: ReviewProposal } {
  if (decision === "accepted" && content !== reviewedContent(proposal)) {
    throw new Error(
      "검토 중 문서가 변경되었습니다. 현재 내용으로 수정을 다시 요청해 주세요."
    );
  }
  if (
    changeId !== "all" &&
    !proposal.changes.some((change) => change.id === changeId)
  ) {
    throw new Error("해당 변경을 찾을 수 없습니다.");
  }
  const updated: ReviewProposal = {
    ...proposal,
    changes: proposal.changes.map((change) =>
      change.decision === "pending" &&
      (changeId === "all" || change.id === changeId)
        ? { ...change, decision }
        : change
    ),
  };
  return {
    content: decision === "accepted" ? reviewedContent(updated) : content,
    proposal: updated,
  };
}

export function editorOffsetToSource(content: string, offset: number): number {
  let sourceOffset = 0;
  let editorOffset = 0;
  while (sourceOffset < content.length && editorOffset < offset) {
    if (content[sourceOffset] === "\r" && content[sourceOffset + 1] === "\n") {
      sourceOffset++;
    }
    sourceOffset++;
    editorOffset++;
  }
  return sourceOffset;
}

export function sourceOffsetToEditor(content: string, offset: number): number {
  return content.slice(0, offset).replace(/\r\n/g, "\n").length;
}

export function applyEditorChanges(
  content: string,
  changes: { from: number; to: number; insert: string }[]
): string {
  const newline = content.includes("\r\n") ? "\r\n" : "\n";
  let result = content;
  for (const change of [...changes].sort((a, b) => b.from - a.from)) {
    const from = editorOffsetToSource(content, change.from);
    const to = editorOffsetToSource(content, change.to);
    result =
      result.slice(0, from) +
      change.insert.replace(/\r?\n/g, newline) +
      result.slice(to);
  }
  return result;
}
