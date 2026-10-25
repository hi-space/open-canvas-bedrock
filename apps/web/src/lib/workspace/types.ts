export type ChangeDecision = "pending" | "accepted" | "rejected";

export interface TextSelection {
  from: number;
  to: number;
  text: string;
  nodeId?: string;
  label?: string;
  previewText?: string;
  sourceIds?: string[];
}

export interface ReviewChange {
  id: string;
  from: number;
  to: number;
  before: string;
  after: string;
  decision: ChangeDecision;
}

export interface ReviewProposal {
  id: string;
  kind: "ai" | "external";
  instruction: string;
  explanation: string;
  baseContent: string;
  proposedContent: string;
  changes: ReviewChange[];
  createdAt: number;
}

export interface ReviewLocation {
  changeId: string;
  number: number;
  from: number;
  to: number;
}

export interface ReviewFocus extends ReviewLocation {
  request: number;
}

export interface SourceReference {
  id: string;
  title: string;
  url: string;
  excerpt?: string;
}

export interface DocumentRevision {
  id: string;
  content: string;
  label: string;
  createdAt: number;
}

export interface DiskSnapshot {
  content: string;
  modifiedAt: number;
}

export interface LocalFileHandle {
  kind: "file";
  name: string;
  getFile(): Promise<File>;
  createWritable(): Promise<{
    write(data: string): Promise<void>;
    close(): Promise<void>;
    abort(): Promise<void>;
  }>;
  queryPermission?(options: {
    mode: "read" | "readwrite";
  }): Promise<PermissionState>;
  requestPermission?(options: {
    mode: "read" | "readwrite";
  }): Promise<PermissionState>;
}

export interface LocalDirectoryHandle {
  kind: "directory";
  name: string;
  values(): AsyncIterableIterator<LocalFileHandle | LocalDirectoryHandle>;
  getFileHandle(
    name: string,
    options?: { create?: boolean }
  ): Promise<LocalFileHandle>;
  queryPermission?(options: {
    mode: "read" | "readwrite";
  }): Promise<PermissionState>;
  requestPermission?(options: {
    mode: "read" | "readwrite";
  }): Promise<PermissionState>;
  isSameEntry?(other: LocalDirectoryHandle): Promise<boolean>;
}

export interface WorkspaceDocument {
  id: string;
  name: string;
  path: string;
  folderId?: string;
  folderName?: string;
  content: string;
  disk?: DiskSnapshot;
  external?: DiskSnapshot;
  missing?: boolean;
  fileHandle?: LocalFileHandle;
  sources: SourceReference[];
  revisions: DocumentRevision[];
  proposal?: ReviewProposal;
  updatedAt: number;
}

export interface WorkspaceFolder {
  id: string;
  name: string;
  handle: LocalDirectoryHandle;
}

export interface WorkspaceState {
  version: 1;
  documents: WorkspaceDocument[];
  activeDocumentId: string | null;
  folder?: WorkspaceFolder;
}

export type EditingAction = "proofread" | "clarify" | "shorten" | "custom";

export interface WritingRequest {
  document: string;
  selectedText?: string;
  instruction: string;
  model?: string;
  sources: SourceReference[];
}

export interface WritingResponse {
  replacement: string;
  explanation: string;
}
