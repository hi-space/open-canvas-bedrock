import type { TextSelection } from "./types";

export function ownsComposerDraft(
  submitted: { workspaceId?: string; revision: number },
  current: { workspaceId?: string; revision: number }
): boolean {
  return (
    !!submitted.workspaceId &&
    submitted.workspaceId === current.workspaceId &&
    submitted.revision === current.revision
  );
}

export function ownsSelection(
  submitted: { workspaceId?: string; path?: string; selection?: TextSelection },
  current: { workspaceId?: string; path?: string; selection?: TextSelection }
): boolean {
  return (
    !!submitted.selection &&
    submitted.workspaceId === current.workspaceId &&
    submitted.path === current.path &&
    submitted.selection === current.selection
  );
}
