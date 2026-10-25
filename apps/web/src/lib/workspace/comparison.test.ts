import { describe, expect, it } from "vitest";
import { comparisonRanges } from "./comparison";

describe("document comparison ranges", () => {
  it("locates a replacement in each version's own source", () => {
    expect(comparisonRanges("Hello old world", "Hello new world")).toEqual({
      before: [{ from: 6, to: 9 }],
      after: [{ from: 6, to: 9 }],
    });
  });

  it("leaves the opposite side unmarked for additions and deletions", () => {
    expect(comparisonRanges("", "새 문서")).toEqual({
      before: [],
      after: [{ from: 0, to: 4 }],
    });
    expect(comparisonRanges("이전 문서", "")).toEqual({
      before: [{ from: 0, to: 5 }],
      after: [],
    });
    expect(comparisonRanges("같은 문서", "같은 문서")).toEqual({
      before: [],
      after: [],
    });
  });

  it("keeps a changed emoji intact instead of marking half a surrogate pair", () => {
    expect(comparisonRanges("a😀z", "a😁z")).toEqual({
      before: [{ from: 1, to: 3 }],
      after: [{ from: 1, to: 3 }],
    });
  });

  it("uses unnormalized offsets for BOM and CRLF documents", () => {
    expect(
      comparisonRanges("\uFEFF# 문서\r\n\r\nold", "\uFEFF# 문서\r\n\r\nnew")
    ).toEqual({
      before: [{ from: 9, to: 12 }],
      after: [{ from: 9, to: 12 }],
    });
  });

  it("marks the changed occurrence when paragraphs repeat", () => {
    expect(
      comparisonRanges(
        "first\n\nsame paragraph\n\nsame paragraph",
        "first\n\nsame paragraph\n\nnew paragraph"
      )
    ).toEqual({
      before: [{ from: 23, to: 27 }],
      after: [{ from: 23, to: 26 }],
    });
  });
});
