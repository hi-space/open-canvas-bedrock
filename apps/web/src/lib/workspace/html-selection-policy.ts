import type { HtmlRegion } from "./html";

/**
 * Candidates run from the clicked element to its outer editable ancestors.
 * Explicit choices in the region picker bypass this policy.
 */
export function chooseDefaultHtmlRegion(
  candidates: HtmlRegion[]
): HtmlRegion | undefined {
  // Start with the precise element the author clicked. The explicit parent
  // control widens the selection when the author wants to change a layout.
  return candidates[0];
}
