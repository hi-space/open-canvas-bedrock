import { describe, expect, it } from "vitest";
import {
  applyEditorChanges,
  createProposal,
  decideChanges,
  editorOffsetToSource,
  reviewLocations,
  reviewedContent,
  sourceOffsetToEditor,
} from "./review";
import type { ReviewProposal } from "./types";

describe("precise review", () => {
  it("changes only the selected occurrence, keeping Korean and emoji offsets", () => {
    const original = "😀 같은 문장.\n\n같은 문장.";
    const proposal = createProposal(original, "다듬은 문장.", {
      selection: { from: 11, to: 17, text: "같은 문장." },
    });
    expect(reviewedContent(proposal)).toBe(original);
    const result = decideChanges(original, proposal, "all", "accepted");
    expect(result.content).toBe("😀 같은 문장.\n\n다듬은 문장.");
    expect(
      proposal.changes.every((change) => change.decision === "pending")
    ).toBe(true);
  });

  it("rejects selection coordinates that no longer match the captured text", () => {
    expect(() =>
      createProposal("새로운 내용", "수정", {
        selection: { from: 0, to: 3, text: "이전 " },
      })
    ).toThrow(/선택/);
  });

  it("accepts changes in reverse order without moving their original locations", () => {
    const original =
      "First old sentence.\n\nThis paragraph stays completely unchanged.\n\nLast old sentence.";
    const proposal = createProposal(
      original,
      "First new sentence.\n\nThis paragraph stays completely unchanged.\n\nLast new sentence."
    );
    expect(proposal.changes).toHaveLength(2);
    const last = decideChanges(
      original,
      proposal,
      proposal.changes[1].id,
      "accepted"
    );
    expect(last.content).toBe(
      "First old sentence.\n\nThis paragraph stays completely unchanged.\n\nLast new sentence."
    );
    const first = decideChanges(
      last.content,
      last.proposal,
      proposal.changes[0].id,
      "accepted"
    );
    expect(first.content).toBe(
      "First new sentence.\n\nThis paragraph stays completely unchanged.\n\nLast new sentence."
    );
  });

  it("keeps rejected content and permits the other change", () => {
    const original =
      "alpha\n\nAn unchanged paragraph with enough surrounding context.\n\nomega";
    const proposal = createProposal(
      original,
      "FIRST\n\nAn unchanged paragraph with enough surrounding context.\n\nLAST"
    );
    const rejected = decideChanges(
      original,
      proposal,
      proposal.changes[0].id,
      "rejected"
    );
    const result = decideChanges(
      rejected.content,
      rejected.proposal,
      "all",
      "accepted"
    );
    expect(result.content).toBe(
      "alpha\n\nAn unchanged paragraph with enough surrounding context.\n\nLAST"
    );
  });

  it("refuses stale approvals, but allows dismissing a stale proposal", () => {
    const proposal = createProposal("old", "new");
    expect(() =>
      decideChanges("edited by me", proposal, "all", "accepted")
    ).toThrow(/문서가 변경/);
    expect(
      decideChanges("edited by me", proposal, "all", "rejected").content
    ).toBe("edited by me");
  });

  it("supports empty-document generation and complete deletion", () => {
    const generated = createProposal("", "# 새 글");
    expect(decideChanges("", generated, "all", "accepted").content).toBe(
      "# 새 글"
    );
    const deleted = createProposal("# 새 글", "");
    expect(decideChanges("# 새 글", deleted, "all", "accepted").content).toBe(
      ""
    );
  });

  it("does not split emoji surrogate pairs in review cards", () => {
    const proposal = createProposal("기분 😀", "기분 😁");
    expect(proposal.changes[0].before).toBe("😀");
    expect(proposal.changes[0].after).toBe("😁");
  });

  it("keeps all source links unchanged outside an edited selection", () => {
    const original =
      "첫 문장.\n\n근거 [1](https://example.org/article?a=1&b=2).\n";
    const proposal = createProposal(original, "고친 문장.", {
      selection: { from: 0, to: 5, text: "첫 문장." },
    });
    expect(decideChanges(original, proposal, "all", "accepted").content).toBe(
      "고친 문장.\n\n근거 [1](https://example.org/article?a=1&b=2).\n"
    );
  });

  it("keeps diff hunks inside the selected occurrence even when identical text repeats", () => {
    const proposal = createProposal("foo\nfoo", "", {
      selection: { from: 0, to: 4, text: "foo\n" },
    });
    expect(proposal.changes[0].from).toBe(0);
    expect(proposal.changes[0].to).toBe(4);
    expect(proposal.changes[0].before).toBe("foo\n");
    expect(decideChanges("foo\nfoo", proposal, "all", "accepted").content).toBe(
      "foo"
    );
  });
});

describe("lossless source editing", () => {
  it("maps editor positions back to CRLF source positions", () => {
    expect(editorOffsetToSource("one\r\ntwo\r\nthree", 4)).toBe(5);
    expect(editorOffsetToSource("one\r\ntwo\r\nthree", 8)).toBe(10);
  });

  it("maps review positions into the editor without losing BOM or emoji offsets", () => {
    const source = "\uFEFF😀\r\n같은 문장\r\n같은 문장";
    expect(sourceOffsetToEditor(source, 12)).toBe(10);
    expect(sourceOffsetToEditor(source, source.length)).toBe(15);
  });

  it("preserves BOM, mixed existing line endings, and untouched Markdown", () => {
    const source =
      "\uFEFF# Title\r\n\r\nold\n[ref](<https://example.org/a>)\r\n";
    expect(
      applyEditorChanges(source, [{ from: 10, to: 13, insert: "new" }])
    ).toBe("\uFEFF# Title\r\n\r\nnew\n[ref](<https://example.org/a>)\r\n");
  });

  it("uses the file's newline style for inserted lines", () => {
    expect(
      applyEditorChanges("one\r\ntwo", [
        { from: 4, to: 7, insert: "new\nline" },
      ])
    ).toBe("one\r\nnew\r\nline");
  });
});

describe("review locations in the current document", () => {
  const proposal: ReviewProposal = {
    id: "review",
    kind: "ai",
    instruction: "",
    explanation: "",
    baseContent: "old\n\nsame\n\nsame",
    proposedContent: "longer text\n\nsame\n\nnew",
    changes: [
      {
        id: "first",
        from: 0,
        to: 3,
        before: "old",
        after: "longer text",
        decision: "pending",
      },
      {
        id: "last",
        from: 11,
        to: 15,
        before: "same",
        after: "new",
        decision: "pending",
      },
    ],
    createdAt: 0,
  };

  it("points to the requested occurrence when identical text is repeated", () => {
    expect(reviewLocations(proposal.baseContent, proposal)).toEqual([
      { changeId: "first", number: 1, from: 0, to: 3 },
      { changeId: "last", number: 2, from: 11, to: 15 },
    ]);
  });

  it("moves later locations after an earlier change is accepted", () => {
    const accepted = decideChanges(
      proposal.baseContent,
      proposal,
      "first",
      "accepted"
    );
    expect(reviewLocations(accepted.content, accepted.proposal)).toEqual([
      { changeId: "first", number: 1, from: 0, to: 11 },
      { changeId: "last", number: 2, from: 19, to: 23 },
    ]);
  });

  it("keeps locations aligned when accepting out of order and rejecting changes", () => {
    const accepted = decideChanges(
      proposal.baseContent,
      proposal,
      "last",
      "accepted"
    );
    const rejected = decideChanges(
      accepted.content,
      accepted.proposal,
      "first",
      "rejected"
    );
    expect(reviewLocations(rejected.content, rejected.proposal)).toEqual([
      { changeId: "first", number: 1, from: 0, to: 3 },
      { changeId: "last", number: 2, from: 11, to: 14 },
    ]);
  });

  it("retains a zero-width anchor for new content and accepted deletions", () => {
    const insertion = createProposal("", "새 문서");
    expect(reviewLocations("", insertion)).toEqual([
      { changeId: insertion.changes[0].id, number: 1, from: 0, to: 0 },
    ]);
    const deletion = createProposal("지울 문장", "");
    const accepted = decideChanges("지울 문장", deletion, "all", "accepted");
    expect(reviewLocations(accepted.content, accepted.proposal)).toEqual([
      { changeId: deletion.changes[0].id, number: 1, from: 0, to: 0 },
    ]);
  });

  it("does not point at unrelated content after a manual edit", () => {
    expect(reviewLocations("manually edited", proposal)).toEqual([]);
    expect(reviewLocations(proposal.baseContent, undefined)).toEqual([]);
  });
});
