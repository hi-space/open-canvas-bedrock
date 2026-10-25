import { workspaceApi, WorkspaceApiError } from "./cloud-api";
import { validateCloudFile } from "./cloud-sync";
import { insertCitation } from "./sources";
import { insertHtmlCitation } from "./html-source";
import { isHtmlFile } from "./files";
import { htmlRegions } from "./html";
import type {
  CloudChatRequest,
  CloudFile,
  CloudJob,
  CloudProposal,
  CloudProposalSummary,
  CloudWorkspace,
  CloudWorkspaceDetail,
  ResearchGenre,
  WorkspaceService,
} from "./cloud-types";
import type {
  CorrectionRecord,
  DocumentRevision,
  SourceReference,
  TextSelection,
} from "./types";

export interface CloudDraft {
  file: CloudFile;
  content: string;
  remote?: CloudFile;
  recovery?: string;
  recoveryCopies?: string[];
}

export interface CloudProjectState extends CloudWorkspaceDetail {
  documents: Record<string, CloudDraft>;
  proposalDetails: Record<string, CloudProposal>;
  revisions: Record<string, DocumentRevision[]>;
  corrections: Record<string, CorrectionRecord | undefined>;
  activePath?: string;
  reviewId?: string;
  submitting: boolean;
  saving: string[];
  deciding: string[];
  copying: string[];
  uncertainRequest?: CloudChatRequest;
}

export interface CloudState {
  ready: boolean;
  storage: "cloud" | "local";
  workspaces: CloudWorkspace[];
  activeId?: string;
  projects: Record<string, CloudProjectState>;
  error?: string;
  notice?: string;
}

export function isDirty(draft?: CloudDraft): boolean {
  return !!draft && draft.content !== draft.file.content;
}

function upsert<T>(items: T[], value: T, same: (a: T, b: T) => boolean): T[] {
  return [...items.filter((item) => !same(item, value)), value];
}

const byId = <T extends { id: string }>(a: T, b: T) => a.id === b.id;
const byPath = <T extends { path: string }>(a: T, b: T) => a.path === b.path;
const terminal = (job: CloudJob) =>
  job.status === "completed" || job.status === "failed";

function recoveryCopies(draft: CloudDraft, candidates: (string | undefined)[]) {
  const copies = [
    ...new Set(
      [...candidates, draft.recovery, ...(draft.recoveryCopies ?? [])].filter(
        (content): content is string =>
          typeof content === "string" && content !== draft.content
      )
    ),
  ];
  return {
    recovery: copies[0],
    recoveryCopies: copies.length > 1 ? copies.slice(1) : undefined,
  };
}

function summarize(proposal: CloudProposal): CloudProposalSummary {
  return {
    id: proposal.id,
    jobId: proposal.jobId,
    path: proposal.path,
    explanation: proposal.explanation,
    createdAt: proposal.createdAt,
    status: proposal.status,
    savedCopy: proposal.savedCopy,
    pendingCount: proposal.changes.filter(
      (change) => change.decision === "pending"
    ).length,
  };
}

/**
 * Every asynchronous operation captures a project and path before awaiting.
 * Server responses update that captured document; navigation is independent.
 */
export class CloudWorkspaceController {
  private state: CloudState = {
    ready: false,
    storage: "cloud",
    workspaces: [],
    projects: {},
  };
  private listeners = new Set<() => void>();
  private initial?: Promise<void>;
  private refreshGeneration = new Map<string, number>();
  private readGeneration = new Map<string, number>();
  private proposalGeneration = new Map<string, number>();
  private preferredPaths = new Map<string, string>();
  private lastRefresh = new Map<string, number>();
  private polling = false;

  constructor(readonly api: WorkspaceService = workspaceApi) {}

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private commit(next: Partial<CloudState>) {
    this.state = { ...this.state, ...next };
    for (const listener of this.listeners) listener();
  }
  private invalidateRefresh(id: string) {
    this.refreshGeneration.set(id, (this.refreshGeneration.get(id) ?? 0) + 1);
    this.lastRefresh.delete(id);
  }
  private project(
    id: string,
    update: (project: CloudProjectState) => CloudProjectState
  ) {
    const current = this.state.projects[id];
    if (current)
      this.commit({
        projects: { ...this.state.projects, [id]: update(current) },
      });
  }
  report = (error: unknown) => {
    this.commit({
      error:
        error instanceof Error ? error.message : "작업을 완료하지 못했습니다.",
    });
  };
  clearError = () => this.commit({ error: undefined });
  notify = (notice?: string) => this.commit({ notice });

  initialize(preferredId?: string, preferredPath?: string): Promise<void> {
    if (preferredId && preferredPath)
      this.preferredPaths.set(preferredId, preferredPath);
    this.initial ??= (async () => {
      try {
        const result = await this.api.list();
        this.commit(result);
        const id =
          result.workspaces.find((item) => item.id === preferredId)?.id ??
          result.workspaces[0]?.id;
        if (id) {
          await this.selectWorkspace(id);
          if (
            preferredPath &&
            id === preferredId &&
            this.state.projects[id]?.files.some(
              (file) => file.path === preferredPath
            )
          )
            await this.openFile(id, preferredPath);
        }
      } catch (error) {
        this.report(error);
      } finally {
        this.commit({ ready: true });
      }
    })();
    return this.initial;
  }

  async reload() {
    const result = await this.api.list();
    this.commit(result);
    const id = this.state.activeId ?? result.workspaces[0]?.id;
    if (id) await this.selectWorkspace(id, true);
  }

  async createWorkspace(name: string) {
    if (!name.trim()) throw new Error("프로젝트 이름을 입력해 주세요.");
    const workspace = await this.api.create(name.trim());
    this.commit({ workspaces: upsert(this.state.workspaces, workspace, byId) });
    await this.selectWorkspace(workspace.id);
    return workspace;
  }

  async selectWorkspace(id: string, reload = false) {
    this.commit({ activeId: id, error: undefined });
    if (!this.state.projects[id] || reload || this.state.ready)
      await this.refresh(id);
    const project = this.state.projects[id];
    if (project?.activePath && !project.documents[project.activePath])
      await this.openFile(id, project.activePath);
  }

  async refresh(id: string) {
    const generation = (this.refreshGeneration.get(id) ?? 0) + 1;
    this.refreshGeneration.set(id, generation);
    const detail = await this.api.detail(id);
    if (this.refreshGeneration.get(id) !== generation) return;
    const current = this.state.projects[id];
    const jobs = detail.jobs.map((incoming) => {
      const previous = current?.jobs.find((item) => item.id === incoming.id);
      return previous &&
        (previous.updatedAt > incoming.updatedAt ||
          (terminal(previous) && !terminal(incoming)))
        ? previous
        : incoming;
    });
    for (const previous of current?.jobs ?? [])
      if (!jobs.some((item) => item.id === previous.id)) jobs.push(previous);
    const project: CloudProjectState = {
      ...detail,
      jobs,
      documents: current?.documents ?? {},
      proposalDetails: current?.proposalDetails ?? {},
      revisions: current?.revisions ?? {},
      corrections: current?.corrections ?? {},
      activePath:
        current?.activePath ??
        detail.files.find((file) => file.path === this.preferredPaths.get(id))
          ?.path ??
        detail.files[0]?.path,
      reviewId: current?.reviewId,
      saving: current?.saving ?? [],
      deciding: current?.deciding ?? [],
      copying: current?.copying ?? [],
      submitting: current?.submitting ?? false,
      uncertainRequest: current?.uncertainRequest,
    };
    this.commit({
      projects: { ...this.state.projects, [id]: project },
      workspaces: upsert(this.state.workspaces, detail.workspace, byId),
    });
    this.lastRefresh.set(id, Date.now());
    if (
      project.activePath &&
      project.files.some((file) => file.path === project.activePath) &&
      !project.documents[project.activePath]
    )
      await this.fetchFile(id, project.activePath);
  }

  private receiveFile(id: string, file: CloudFile, savedContent?: string) {
    if (savedContent !== undefined) this.invalidateRefresh(id);
    this.readGeneration.set(
      `${id}/${file.path}`,
      (this.readGeneration.get(`${id}/${file.path}`) ?? 0) + 1
    );
    this.project(id, (project) => {
      const previous = project.documents[file.path];
      let draft: CloudDraft;
      if (previous && savedContent !== undefined) {
        draft = {
          file,
          content:
            previous.content === savedContent ? file.content : previous.content,
          recovery: previous.recovery,
          recoveryCopies: previous.recoveryCopies,
        };
      } else if (
        previous &&
        isDirty(previous) &&
        previous.file.version !== file.version
      ) {
        draft = { ...previous, remote: file };
      } else {
        draft = {
          file,
          content:
            previous && isDirty(previous) ? previous.content : file.content,
          recovery: previous?.recovery,
          recoveryCopies: previous?.recoveryCopies,
        };
      }
      return {
        ...project,
        files: upsert(project.files, file, byPath),
        documents: { ...project.documents, [file.path]: draft },
      };
    });
  }

  async fetchFile(id: string, path: string) {
    const key = `${id}/${path}`;
    const generation = (this.readGeneration.get(key) ?? 0) + 1;
    this.readGeneration.set(key, generation);
    const file = await this.api.file(id, path);
    if (this.readGeneration.get(key) === generation) this.receiveFile(id, file);
    return file;
  }

  async openFile(id: string, path: string) {
    this.project(id, (project) => ({ ...project, activePath: path }));
    const draft = this.state.projects[id]?.documents[path];
    if (!draft) await this.fetchFile(id, path);
    else if (!isDirty(draft)) void this.fetchFile(id, path).catch(this.report);
  }

  edit(id: string, path: string, content: string) {
    this.project(id, (project) => {
      const draft = project.documents[path];
      if (!draft) return project;
      return {
        ...project,
        documents: { ...project.documents, [path]: { ...draft, content } },
      };
    });
  }

  restoreDraft(id: string, path: string, stored: CloudDraft) {
    let recovered = false;
    this.project(id, (project) => {
      const current = project.documents[path];
      if (current && isDirty(current)) {
        recovered = current.content !== stored.content;
        return {
          ...project,
          documents: {
            ...project.documents,
            [path]: {
              ...current,
              ...recoveryCopies(current, [
                stored.content,
                stored.recovery,
                ...(stored.recoveryCopies ?? []),
              ]),
            },
          },
        };
      }
      const draft =
        current && current.file.version !== stored.file.version
          ? { ...stored, remote: current.file }
          : stored;
      return { ...project, documents: { ...project.documents, [path]: draft } };
    });
    if (recovered)
      this.notify("이전에 보관한 초안도 복구 사본으로 남겼습니다.");
  }

  async save(id: string, path: string): Promise<CloudFile> {
    const project = this.state.projects[id];
    const draft = project?.documents[path];
    if (!draft) throw new Error("문서를 먼저 열어 주세요.");
    if (project.saving.includes(path))
      throw new Error("문서를 저장하는 중입니다.");
    if (draft.remote)
      throw new Error(
        "클라우드 변경을 먼저 비교해 주세요. 내 초안은 유지됩니다."
      );
    if (!isDirty(draft)) return draft.file;
    validateCloudFile(path, draft.content);
    this.project(id, (current) => ({
      ...current,
      saving: [...current.saving, path],
    }));
    try {
      const file = await this.api.save(id, {
        path,
        content: draft.content,
        baseVersion: draft.file.version,
      });
      this.receiveFile(id, file, draft.content);
      this.notify(`${path} 저장 완료`);
      return file;
    } catch (error) {
      if (error instanceof WorkspaceApiError && error.status === 409)
        await this.fetchFile(id, path).catch(() => undefined);
      throw error;
    } finally {
      this.project(id, (current) => ({
        ...current,
        saving: current.saving.filter((item) => item !== path),
      }));
    }
  }

  async resolveConflict(id: string, path: string, choice: "cloud" | "draft") {
    const draft = this.state.projects[id]?.documents[path];
    if (!draft?.remote) return;
    this.project(id, (project) => ({
      ...project,
      documents: {
        ...project.documents,
        [path]: {
          file: draft.remote!,
          content: choice === "cloud" ? draft.remote!.content : draft.content,
          ...(choice === "cloud"
            ? recoveryCopies({ ...draft, content: draft.remote!.content }, [
                draft.content,
              ])
            : {
                recovery: draft.recovery,
                recoveryCopies: draft.recoveryCopies,
              }),
        },
      },
    }));
    if (choice === "draft") await this.save(id, path);
    this.clearError();
  }

  async putFile(
    id: string,
    path: string,
    content: string,
    baseVersion: string | null = null
  ) {
    validateCloudFile(path, content);
    const file = await this.api.save(id, { path, content, baseVersion });
    this.invalidateRefresh(id);
    this.receiveFile(id, file);
    return file;
  }

  async createFile(id: string, path: string, content = "") {
    const file = await this.putFile(id, path, content);
    this.project(id, (project) => ({ ...project, activePath: file.path }));
    return file;
  }

  async send(
    message: string,
    options: {
      selection?: TextSelection;
      model?: string;
      researchGenre?: ResearchGenre;
      outputFormat?: "html";
    } = {}
  ) {
    const id = this.state.activeId;
    const project = id && this.state.projects[id];
    if (!id || !project) throw new Error("프로젝트를 먼저 만들어 주세요.");
    if (!message.trim()) throw new Error("메시지를 입력해 주세요.");
    if (project.submitting) throw new Error("메시지를 보내는 중입니다.");
    if (project.jobs.some((job) => !terminal(job)))
      throw new Error(
        "이 프로젝트에서 에이전트가 작업 중입니다. 완료 후 다시 보내 주세요."
      );
    if (project.uncertainRequest)
      throw new Error("앞선 요청의 접수를 먼저 확인해 주세요.");
    if (options.outputFormat && (options.selection || options.researchGenre))
      throw new Error(
        "HTML 생성은 영역 수정이나 딥 리서치와 따로 요청해 주세요."
      );
    const path = project.activePath;
    const draft = path ? project.documents[path] : undefined;
    const content = draft?.content;
    if (
      options.selection &&
      (!draft ||
        content?.slice(options.selection.from, options.selection.to) !==
          options.selection.text)
    )
      throw new Error("선택한 문장이 달라졌습니다. 다시 선택해 주세요.");
    this.project(id, (current) => ({ ...current, submitting: true }));
    try {
      const file = draft && path ? await this.save(id, path) : undefined;
      // Editing during Save must never send the selection against new typing.
      const current = path
        ? this.state.projects[id]?.documents[path]
        : undefined;
      if (current && current.content !== (file?.content ?? content))
        throw new Error(
          "저장 중 문서가 변경되었습니다. 현재 내용으로 다시 보내 주세요."
        );
      let selection = options.selection;
      if (selection && file && isHtmlFile(file.path)) {
        const region = htmlRegions(file.content).find(
          (item) => item.nodeId === selection?.nodeId
        );
        if (!region)
          throw new Error(
            "HTML 미리보기에서 수정할 영역을 다시 선택해 주세요."
          );
        // A canonical save may add IDs before this node. Resolve its new range
        // only after confirming that no newer user typing is being replaced.
        const { from, to, text, nodeId } = region;
        selection = { from, to, text, nodeId };
      }
      const request: CloudChatRequest = {
        message: message.trim(),
        requestId: crypto.randomUUID(),
        model: options.model,
        ...(file ? { activePath: file.path, activeVersion: file.version } : {}),
        ...(selection ? { selection } : {}),
        ...(options.researchGenre
          ? { researchGenre: options.researchGenre }
          : {}),
        ...(options.outputFormat ? { outputFormat: options.outputFormat } : {}),
      };
      await this.submitRequest(id, request);
    } finally {
      this.project(id, (current) => ({ ...current, submitting: false }));
    }
  }

  private async submitRequest(id: string, request: CloudChatRequest) {
    try {
      const { job } = await this.api.chat(id, request);
      this.invalidateRefresh(id);
      this.project(id, (project) => ({
        ...project,
        jobs: upsert(project.jobs, job, byId),
        uncertainRequest: undefined,
        messages: project.messages.some(
          (item) => item.role === "user" && item.jobId === job.id
        )
          ? project.messages
          : [
              ...project.messages,
              {
                id: request.requestId,
                role: "user",
                content: request.message,
                createdAt: job.createdAt,
                jobId: job.id,
              },
            ],
      }));
    } catch (error) {
      if (
        error instanceof WorkspaceApiError &&
        error.status === 409 &&
        request.activePath
      )
        await this.fetchFile(id, request.activePath).catch(() => undefined);
      if (
        error instanceof WorkspaceApiError &&
        (error.status === 0 || error.status >= 500)
      )
        this.project(id, (project) => ({
          ...project,
          uncertainRequest: request,
        }));
      throw error;
    }
  }

  async retryRequest(id: string) {
    const project = this.state.projects[id];
    if (!project?.uncertainRequest || project.submitting) return;
    this.project(id, (current) => ({ ...current, submitting: true }));
    try {
      await this.submitRequest(id, project.uncertainRequest);
    } finally {
      this.project(id, (current) => ({ ...current, submitting: false }));
    }
  }

  async poll() {
    if (this.polling) return;
    this.polling = true;
    try {
      for (const [id, project] of Object.entries(this.state.projects)) {
        let finished = false;
        for (const pending of project.jobs.filter((item) => !terminal(item))) {
          const job = await this.api.job(id, pending.id);
          this.project(id, (current) => ({
            ...current,
            jobs: upsert(current.jobs, job, byId),
          }));
          if (terminal(job)) finished = true;
        }
        if (
          finished ||
          (this.state.activeId === id &&
            Date.now() - (this.lastRefresh.get(id) ?? 0) > 10000)
        )
          await this.refresh(id);
      }
    } finally {
      this.polling = false;
    }
  }

  async openProposal(id: string, proposalId: string) {
    const key = `${id}/${proposalId}`;
    const generation = (this.proposalGeneration.get(key) ?? 0) + 1;
    this.proposalGeneration.set(key, generation);
    this.project(id, (project) => ({ ...project, reviewId: proposalId }));
    const proposal = await this.api.proposal(id, proposalId);
    if (this.proposalGeneration.get(key) !== generation) return proposal;
    this.project(id, (project) => ({
      ...project,
      activePath:
        project.reviewId === proposalId ? proposal.path : project.activePath,
      proposals: upsert(project.proposals, summarize(proposal), byId),
      proposalDetails: { ...project.proposalDetails, [proposalId]: proposal },
    }));
    if (proposal.baseVersion !== null) await this.fetchFile(id, proposal.path);
    return proposal;
  }

  dismissProposal(id: string) {
    this.project(id, (project) => ({ ...project, reviewId: undefined }));
  }

  async decide(
    id: string,
    proposalId: string,
    changeId: string,
    decision: "accepted" | "rejected"
  ) {
    const project = this.state.projects[id];
    const proposal = project?.proposalDetails[proposalId];
    if (!proposal) throw new Error("수정안을 먼저 열어 주세요.");
    if (
      project.deciding.includes(proposalId) ||
      project.copying.includes(proposalId)
    )
      return;
    if (isDirty(project.documents[proposal.path]))
      throw new Error(
        "편집 중인 내용을 먼저 저장한 뒤 수정안을 다시 확인해 주세요."
      );
    const decisions = Object.fromEntries(
      proposal.changes
        .filter(
          (change) =>
            change.decision === "pending" &&
            (changeId === "all" || change.id === changeId)
        )
        .map((change) => [change.id, decision])
    );
    if (!Object.keys(decisions).length) return;
    const key = `${id}/${proposalId}`;
    this.proposalGeneration.set(
      key,
      (this.proposalGeneration.get(key) ?? 0) + 1
    );
    this.project(id, (current) => ({
      ...current,
      deciding: [...current.deciding, proposalId],
    }));
    try {
      const result = await this.api.decide(id, proposalId, decisions);
      this.proposalGeneration.set(
        key,
        (this.proposalGeneration.get(key) ?? 0) + 1
      );
      this.invalidateRefresh(id);
      this.project(id, (current) => ({
        ...current,
        proposals: upsert(current.proposals, summarize(result.proposal), byId),
        proposalDetails: {
          ...current.proposalDetails,
          [proposalId]: result.proposal,
        },
      }));
      if (result.file) this.receiveFile(id, result.file);
      this.notify(
        decision === "accepted"
          ? "승인한 변경을 파일에 저장했습니다."
          : "변경을 거절했습니다."
      );
    } catch (error) {
      if (error instanceof WorkspaceApiError && error.status === 409)
        await this.fetchFile(id, proposal.path).catch(() => undefined);
      throw error;
    } finally {
      this.project(id, (current) => ({
        ...current,
        deciding: current.deciding.filter((item) => item !== proposalId),
      }));
    }
  }

  async saveProposalCopy(id: string, proposalId: string) {
    const project = this.state.projects[id];
    if (!project?.proposalDetails[proposalId])
      throw new Error("수정안을 먼저 열어 주세요.");
    if (
      project.copying.includes(proposalId) ||
      project.deciding.includes(proposalId)
    )
      return;
    const key = `${id}/${proposalId}`;
    this.proposalGeneration.set(
      key,
      (this.proposalGeneration.get(key) ?? 0) + 1
    );
    this.project(id, (current) => ({
      ...current,
      copying: [...current.copying, proposalId],
    }));
    try {
      const result = await this.api.copy(id, proposalId);
      this.proposalGeneration.set(
        key,
        (this.proposalGeneration.get(key) ?? 0) + 1
      );
      this.invalidateRefresh(id);
      this.project(id, (current) => ({
        ...current,
        proposals: upsert(current.proposals, summarize(result.proposal), byId),
        proposalDetails: {
          ...current.proposalDetails,
          [proposalId]: result.proposal,
        },
      }));
      // A refresh can expose the copy before this response arrives. Preserve any
      // destination state opened, edited or saved since this request started.
      const current = this.state.projects[id]?.documents[result.file.path];
      if (!current || current === project.documents[result.file.path])
        this.receiveFile(id, result.file);
      this.notify(`${result.file.path} 교정본 저장 완료`);
      return result.file;
    } finally {
      this.project(id, (current) => ({
        ...current,
        copying: current.copying.filter((item) => item !== proposalId),
      }));
    }
  }

  async loadHistory(id: string, path: string) {
    const { revisions, correction } = await this.api.history(id, path);
    this.project(id, (project) => ({
      ...project,
      revisions: { ...project.revisions, [path]: revisions },
      corrections: { ...project.corrections, [path]: correction ?? undefined },
    }));
  }

  async addSource(id: string, source: SourceReference) {
    const result = await this.api.source(id, source);
    this.invalidateRefresh(id);
    this.project(id, (project) => ({
      ...project,
      sources: upsert(project.sources, result, byId),
    }));
  }

  async removeSource(id: string, sourceId: string) {
    await this.api.removeSource(id, sourceId);
    this.invalidateRefresh(id);
    this.project(id, (project) => ({
      ...project,
      sources: project.sources.filter((source) => source.id !== sourceId),
    }));
  }

  cite(
    id: string,
    path: string,
    source: SourceReference,
    selection?: TextSelection
  ) {
    const draft = this.state.projects[id]?.documents[path];
    if (!draft) return;
    if (
      selection &&
      draft.content.slice(selection.from, selection.to) !== selection.text
    )
      throw new Error("인용할 문장을 다시 선택해 주세요.");
    const recordedSource = this.state.projects[id]?.sources.find(
      (item) => item.url === source.url
    );
    this.edit(
      id,
      path,
      isHtmlFile(path)
        ? insertHtmlCitation(
            draft.content,
            source,
            selection?.nodeId,
            recordedSource?.id ?? null
          )
        : insertCitation(
            draft.content,
            source,
            selection?.to ?? draft.content.length
          )
    );
  }
}
