import type { SourceReference } from "./types";
import type {
  CloudChatRequest,
  CloudFile,
  CloudJob,
  CloudProposal,
  CloudWorkspace,
  CloudWorkspaceDetail,
  WorkspaceService,
} from "./cloud-types";
import type { CorrectionRecord, DocumentRevision } from "./types";

export class WorkspaceApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "WorkspaceApiError";
  }
}

async function request<T>(
  path = "",
  method = "GET",
  body?: unknown
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`/api/workspaces${path}`, {
      method,
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
      ...(body === undefined
        ? {}
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
    const data = await response.json().catch(() => undefined);
    if (!response.ok || !data) {
      throw new WorkspaceApiError(
        response.status,
        typeof data?.detail === "string"
          ? data.detail
          : response.status === 401 || response.redirected
            ? "로그인이 필요합니다. 다시 로그인한 뒤 작업을 이어가 주세요."
            : "작업 공간에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof WorkspaceApiError) throw error;
    throw new WorkspaceApiError(
      0,
      "서버 응답을 확인하지 못했습니다. 요청을 다시 확인해 주세요. 초안은 유지됩니다."
    );
  } finally {
    clearTimeout(timer);
  }
}

const segment = encodeURIComponent;

export const workspaceApi: WorkspaceService = {
  list: () =>
    request<{ workspaces: CloudWorkspace[]; storage: "cloud" | "local" }>(),
  create: (name) => request<CloudWorkspace>("", "POST", { name }),
  detail: (id) => request<CloudWorkspaceDetail>(`/${segment(id)}`),
  file: (id, path) =>
    request<CloudFile>(`/${segment(id)}/files?path=${segment(path)}`),
  save: (id, input) =>
    request<CloudFile>(`/${segment(id)}/files`, "PUT", input),
  history: (id, path) =>
    request<{
      revisions: DocumentRevision[];
      correction?: CorrectionRecord | null;
    }>(`/${segment(id)}/history?path=${segment(path)}`),
  source: (id, source) =>
    request<SourceReference>(`/${segment(id)}/sources`, "POST", source),
  readSource: (id, sourceId) =>
    request<SourceReference>(`/${segment(id)}/sources/${segment(sourceId)}`),
  removeSource: (id, sourceId) =>
    request<{ ok: boolean }>(
      `/${segment(id)}/sources/${segment(sourceId)}`,
      "DELETE"
    ),
  chat: (id, input: CloudChatRequest) =>
    request<{ job: CloudJob }>(`/${segment(id)}/chat`, "POST", input),
  job: (id, jobId) =>
    request<CloudJob>(`/${segment(id)}/jobs/${segment(jobId)}`),
  proposal: (id, proposalId) =>
    request<CloudProposal>(`/${segment(id)}/proposals/${segment(proposalId)}`),
  decide: (id, proposalId, decisions) =>
    request<{ proposal: CloudProposal; file: CloudFile | null }>(
      `/${segment(id)}/proposals/${segment(proposalId)}/decisions`,
      "POST",
      { decisions }
    ),
  copy: (id, proposalId) =>
    request<{ proposal: CloudProposal; file: CloudFile }>(
      `/${segment(id)}/proposals/${segment(proposalId)}/copy`,
      "POST"
    ),
};
