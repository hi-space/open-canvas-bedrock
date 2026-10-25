import { useCallback, useMemo, useState } from "react";
import { reviewLocations } from "@/lib/workspace/review";
import type { ReviewFocus, ReviewProposal } from "@/lib/workspace/types";

export function useReviewFocus(
  documentId: string | undefined,
  content: string,
  proposal: ReviewProposal | undefined
) {
  const [active, setActive] = useState<{
    documentId: string;
    proposalId: string;
    changeId: string;
    request: number;
    readingRequested?: boolean;
  }>();
  const locations = useMemo(
    () => reviewLocations(content, proposal),
    [content, proposal]
  );
  const focus = useMemo<ReviewFocus | undefined>(() => {
    if (
      !active ||
      active.documentId !== documentId ||
      active.proposalId !== proposal?.id
    )
      return undefined;
    const location = locations.find(
      (item) => item.changeId === active.changeId
    );
    return location && { ...location, request: active.request };
  }, [active, documentId, locations, proposal?.id]);

  const locate = (changeId: string) => {
    if (
      !documentId ||
      !proposal ||
      !locations.some((item) => item.changeId === changeId)
    )
      return;
    setActive((previous) => ({
      documentId,
      proposalId: proposal.id,
      changeId,
      request: (previous?.request ?? 0) + 1,
    }));
  };

  const clear = useCallback(() => setActive(undefined), []);
  const requestReading = useCallback(
    () =>
      setActive((current) => current && { ...current, readingRequested: true }),
    []
  );
  return {
    focus,
    locate,
    clear,
    readingRequested: !!focus && !!active?.readingRequested,
    requestReading,
  };
}
