import type { EditingAction } from "./types";

/**
 * Defines the author's preferred editing voice. Keep facts, meaning, source
 * links, and the document's language intact; custom requests can refine tone.
 */
export function editingInstruction(
  action: EditingAction,
  customInstruction = ""
): string {
  // Preserve the author's voice unless their custom instruction asks for a change.
  const instructions: Record<EditingAction, string> = {
    proofread:
      "맞춤법, 띄어쓰기, 문법만 최소한으로 교정해 주세요. 원래 문체를 유지해 주세요.",
    clarify:
      "의미와 문체를 유지하면서 읽기 쉽고 명확한 문장으로 다듬어 주세요.",
    shorten:
      "핵심 주장, 사실, 출처를 유지하면서 중복 표현을 줄여 간결하게 다듬어 주세요.",
    custom: customInstruction.trim(),
  };
  return instructions[action];
}
