import type {
  DiskSnapshot,
  DocumentRevision,
  LocalFileHandle,
  WorkspaceDocument,
} from "./types";
import { decideChanges } from "./review";
import { validateProposalReferences } from "./sources";

const MAX_REVISIONS = 30;

function revision(content: string, label: string): DocumentRevision {
  return { id: crypto.randomUUID(), content, label, createdAt: Date.now() };
}

export function createDocument(name: string, content = ""): WorkspaceDocument {
  return {
    id: crypto.randomUUID(),
    name,
    path: name,
    content,
    sources: [],
    revisions: [revision(content, "처음 연 문서")],
    updatedAt: Date.now(),
  };
}

export function receiveDiskSnapshot(
  document: WorkspaceDocument,
  snapshot: DiskSnapshot
): WorkspaceDocument {
  if (snapshot.content === document.content) {
    if (
      snapshot.content === document.disk?.content &&
      !document.external &&
      !document.missing
    )
      return document;
    return { ...document, disk: snapshot, external: undefined, missing: false };
  }
  if (snapshot.content === document.disk?.content) {
    return document.external || document.missing
      ? { ...document, external: undefined, missing: false }
      : document;
  }
  if (snapshot.content === document.external?.content && !document.missing)
    return document;
  return { ...document, external: snapshot, missing: false };
}

export function reviseDocument(
  document: WorkspaceDocument,
  content: string,
  label: string
): WorkspaceDocument {
  if (
    content === document.content &&
    document.revisions.at(-1)?.content === content
  ) {
    return document;
  }
  const revisions = [...document.revisions];
  if (revisions.at(-1)?.content !== document.content) {
    revisions.push(revision(document.content, "수정 전 초안"));
  }
  if (content !== document.content) revisions.push(revision(content, label));
  return {
    ...document,
    content,
    revisions: revisions.slice(-MAX_REVISIONS),
    updatedAt: Date.now(),
  };
}

export function decideDocumentChanges(
  document: WorkspaceDocument,
  changeId: string,
  decision: "accepted" | "rejected"
): WorkspaceDocument {
  const proposal = document.proposal;
  if (!proposal) return document;
  if (
    decision === "accepted" &&
    proposal.kind === "external" &&
    document.external?.content !== proposal.proposedContent
  ) {
    throw new Error(
      "외부 파일이 다시 변경되었습니다. 최신 변경을 다시 열어 검토해 주세요."
    );
  }
  const result = decideChanges(document.content, proposal, changeId, decision);
  if (decision === "accepted" && proposal.kind === "ai") {
    validateProposalReferences(
      proposal.baseContent,
      result.content,
      document.sources
    );
  }
  const next = {
    ...(decision === "accepted"
      ? reviseDocument(
          document,
          result.content,
          proposal.kind === "ai" ? "AI 수정 승인" : "외부 변경 반영"
        )
      : document),
    proposal: result.proposal,
  };
  if (
    proposal.kind === "external" &&
    document.external?.content === proposal.proposedContent &&
    result.proposal.changes.every((change) => change.decision !== "pending")
  ) {
    return { ...next, disk: document.external, external: undefined };
  }
  return next;
}

export function bindDocumentFile(
  document: WorkspaceDocument,
  handle: LocalFileHandle,
  snapshot: DiskSnapshot,
  newBinding: boolean
): WorkspaceDocument {
  return {
    ...reviseDocument(document, document.content, "파일 저장"),
    fileHandle: handle,
    name: handle.name,
    path: newBinding ? handle.name : document.path,
    folderId: newBinding ? undefined : document.folderId,
    folderName: newBinding ? undefined : document.folderName,
    disk: snapshot,
    external: undefined,
    missing: false,
  };
}
