import { describe, expect, it } from "vitest";
import { ownsComposerDraft, ownsSelection } from "./cloud-intent";

describe("asynchronous composer completion", () => {
  it("clears only the same project and unchanged composer revision", () => {
    const sent = { workspaceId: "a", revision: 4 };
    expect(ownsComposerDraft(sent, { workspaceId: "a", revision: 4 })).toBe(
      true
    );
    expect(ownsComposerDraft(sent, { workspaceId: "b", revision: 4 })).toBe(
      false
    );
    expect(ownsComposerDraft(sent, { workspaceId: "a", revision: 5 })).toBe(
      false
    );
  });

  it("does not clear a new selection, even if its text happens to match", () => {
    const first = { from: 0, to: 3, text: "abc" };
    const sent = { workspaceId: "a", path: "a.md", selection: first };
    expect(ownsSelection(sent, { ...sent })).toBe(true);
    expect(ownsSelection(sent, { ...sent, workspaceId: "b" })).toBe(false);
    expect(ownsSelection(sent, { ...sent, path: "b.md" })).toBe(false);
    expect(ownsSelection(sent, { ...sent, selection: { ...first } })).toBe(
      false
    );
    expect(ownsSelection({ ...sent, selection: undefined }, sent)).toBe(false);
  });
});
