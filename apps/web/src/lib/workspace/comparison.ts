import DiffMatchPatch from "diff-match-patch";
import type { ReviewProposal } from "./types";

export interface ComparisonRange {
  from: number;
  to: number;
}

function appendRange(
  ranges: ComparisonRange[],
  content: string,
  from: number,
  to: number
) {
  // Diff offsets use UTF-16; a highlight must include the whole emoji.
  if (
    /[\uDC00-\uDFFF]/.test(content[from] ?? "") &&
    /[\uD800-\uDBFF]/.test(content[from - 1] ?? "")
  )
    from--;
  if (
    /[\uDC00-\uDFFF]/.test(content[to] ?? "") &&
    /[\uD800-\uDBFF]/.test(content[to - 1] ?? "")
  )
    to++;
  const previous = ranges.at(-1);
  if (previous && previous.to >= from) previous.to = Math.max(previous.to, to);
  else ranges.push({ from, to });
}

export function comparisonRanges(before: string, after: string) {
  const engine = new DiffMatchPatch();
  const parts = engine.diff_main(before, after);
  engine.diff_cleanupSemantic(parts);
  const ranges = {
    before: [] as ComparisonRange[],
    after: [] as ComparisonRange[],
  };
  let beforeOffset = 0;
  let afterOffset = 0;
  for (const [operation, text] of parts) {
    if (operation === -1)
      appendRange(
        ranges.before,
        before,
        beforeOffset,
        beforeOffset + text.length
      );
    if (operation === 1)
      appendRange(ranges.after, after, afterOffset, afterOffset + text.length);
    if (operation !== 1) beforeOffset += text.length;
    if (operation !== -1) afterOffset += text.length;
  }
  return ranges;
}

/** Select the right-hand document while individual changes are reviewed. */
export function proposalComparisonContent(proposal: ReviewProposal): string {
  // Preserve the proposal snapshot; review decisions have their own status.
  return proposal.proposedContent;
}
