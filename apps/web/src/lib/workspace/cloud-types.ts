import type {
  DocumentRevision,
  ReviewChange,
  SourceReference,
  TextSelection,
} from "./types";

export interface CloudWorkspace {
  id: string;
  name: string;
  createdAt: number;
  updatedAt: number;
}

export interface CloudFileSummary {
  path: string;
  name: string;
  version: string;
  bytes: number;
  updatedAt: number;
}

export interface CloudFile extends CloudFileSummary {
  content: string;
}

export interface CloudMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  jobId?: string;
}

/** Deep research: research the request, then propose a new document written for this genre. */
export type ResearchGenre = "paper" | "blog" | "linkedin";

export interface CloudJob {
  id: string;
  kind?: "research";
  status: "queued" | "running" | "completed" | "failed";
  createdAt: number;
  updatedAt: number;
  message?: string;
  error?: string;
  proposalIds: string[];
}

export interface CloudProposalSummary {
  id: string;
  jobId: string;
  path: string;
  explanation: string;
  createdAt: number;
  status: "pending" | "accepted" | "rejected" | "partial";
  pendingCount: number;
}

export interface CloudProposal extends Omit<
  CloudProposalSummary,
  "pendingCount"
> {
  kind: "ai";
  instruction: string;
  baseContent: string;
  proposedContent: string;
  baseVersion: string | null;
  appliedVersion: string | null;
  changes: ReviewChange[];
}

export interface CloudWorkspaceDetail {
  workspace: CloudWorkspace;
  files: CloudFileSummary[];
  messages: CloudMessage[];
  proposals: CloudProposalSummary[];
  jobs: CloudJob[];
  sources: SourceReference[];
}

export interface CloudChatRequest {
  message: string;
  requestId: string;
  activePath?: string;
  activeVersion?: string;
  selection?: TextSelection;
  model?: string;
  researchGenre?: ResearchGenre;
  outputFormat?: "html";
}

export interface WorkspaceService {
  list(): Promise<{
    workspaces: CloudWorkspace[];
    storage: "cloud" | "local";
  }>;
  create(name: string): Promise<CloudWorkspace>;
  detail(id: string): Promise<CloudWorkspaceDetail>;
  file(id: string, path: string): Promise<CloudFile>;
  save(
    id: string,
    input: { path: string; content: string; baseVersion: string | null }
  ): Promise<CloudFile>;
  history(id: string, path: string): Promise<{ revisions: DocumentRevision[] }>;
  source(id: string, source: SourceReference): Promise<SourceReference>;
  removeSource(id: string, sourceId: string): Promise<{ ok: boolean }>;
  chat(id: string, request: CloudChatRequest): Promise<{ job: CloudJob }>;
  job(id: string, jobId: string): Promise<CloudJob>;
  proposal(id: string, proposalId: string): Promise<CloudProposal>;
  decide(
    id: string,
    proposalId: string,
    decisions: Record<string, "accepted" | "rejected">
  ): Promise<{ proposal: CloudProposal; file: CloudFile | null }>;
}
