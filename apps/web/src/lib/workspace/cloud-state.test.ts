import { describe, expect, it } from "vitest";
import { WorkspaceApiError } from "./cloud-api";
import { CloudWorkspaceController } from "./cloud-state";
import type {
  CloudChatRequest,
  CloudFile,
  CloudJob,
  CloudProposal,
  CloudWorkspaceDetail,
  WorkspaceService,
} from "./cloud-types";

const file = (
  path = "a.md",
  content = "original",
  version = "v1"
): CloudFile => ({
  path,
  name: path,
  content,
  version,
  bytes: content.length,
  updatedAt: 1,
});
const snapshot = (id: string): CloudWorkspaceDetail => ({
  workspace: { id, name: id, createdAt: 1, updatedAt: 1 },
  files: [file()],
  messages: [],
  proposals: [],
  jobs: [],
  sources: [],
});
const job: CloudJob = {
  id: "job-a",
  status: "running",
  createdAt: 2,
  updatedAt: 2,
  proposalIds: [],
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function service(overrides: Partial<WorkspaceService> = {}): WorkspaceService {
  return {
    list: async () => ({
      workspaces: [snapshot("a").workspace, snapshot("b").workspace],
      storage: "cloud",
    }),
    create: async (name) => ({ id: name, name, createdAt: 1, updatedAt: 1 }),
    detail: async (id) => snapshot(id),
    file: async (_id, path) => file(path),
    save: async (_id, input) => file(input.path, input.content, "v2"),
    chat: async () => ({ job }),
    job: async () => job,
    history: async () => ({ revisions: [] }),
    source: async (_id, source) => source,
    readSource: async () => {
      throw new Error("Unexpected source body read");
    },
    removeSource: async () => ({ ok: true }),
    proposal: async () => {
      throw new Error("Unexpected proposal");
    },
    decide: async () => {
      throw new Error("Unexpected approval");
    },
    copy: async () => {
      throw new Error("Unexpected copy");
    },
    ...overrides,
  };
}

describe("cloud workspace state and captured request context", () => {
  it("does not invent provenance IDs for a citation extracted from an imported HTML file", async () => {
    const original =
      '<p data-oc-id="p">내용 <a href="https://example.org/old">원문</a></p>';
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file("page.html", original)],
        }),
        file: async () => file("page.html", original),
      })
    );
    await controller.initialize();
    controller.cite(
      "a",
      "page.html",
      {
        id: "link:synthetic",
        title: "원문",
        url: "https://example.org/old",
      },
      { from: 0, to: original.length, text: original, nodeId: "p" }
    );
    const result =
      controller.getSnapshot().projects.a.documents["page.html"].content;
    expect(result).not.toContain("data-source-ids");
    expect(result.match(/href="https:\/\/example.org\/old"/g)).toHaveLength(2);
  });

  it("requests a new HTML result without changing the active Markdown file", async () => {
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    await controller.send("프로젝트 자료로 소개 페이지를 만들어 주세요", {
      outputFormat: "html",
    });
    expect(sent?.outputFormat).toBe("html");
    expect(sent?.researchGenre).toBeUndefined();
    expect(sent?.selection).toBeUndefined();
    expect(controller.getSnapshot().projects.a.documents["a.md"].content).toBe(
      "original"
    );
  });

  it("rejects mixing HTML generation with a selected-passage edit", async () => {
    const controller = new CloudWorkspaceController(service());
    await controller.initialize();
    await expect(
      controller.send("generate", {
        outputFormat: "html",
        selection: { from: 0, to: 8, text: "original" },
      })
    ).rejects.toThrow(/생성/);
  });

  it("combines research, HTML and selected project files in the captured request", async () => {
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    await controller.send("출처와 그림이 있는 HTML 보고서", {
      researchGenre: "blog",
      outputFormat: "html",
      contextPaths: ["a.md"],
    });
    expect(sent).toMatchObject({
      researchGenre: "blog",
      outputFormat: "html",
      contextPaths: ["a.md"],
      activePath: "a.md",
      activeVersion: "v1",
    });
    expect(sent?.selection).toBeUndefined();
  });

  it("preserves an explicit web-only selection and rejects creating research on a text range", async () => {
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    await expect(
      controller.send("선택 조사", {
        researchGenre: "blog",
        selection: { from: 0, to: 8, text: "original" },
      })
    ).rejects.toThrow(/선택/);
    await controller.send("웹 조사", {
      researchGenre: "blog",
      contextPaths: [],
    });
    expect(sent?.contextPaths).toEqual([]);
  });

  it("saves a selected background document before research snapshots it", async () => {
    const saved: string[] = [];
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file(), file("b.md")],
        }),
        save: async (_id, input) => {
          saved.push(input.path);
          return file(input.path, input.content, "v2");
        },
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    await controller.openFile("a", "b.md");
    controller.edit("a", "b.md", "연구에 쓸 최신 메모");
    await controller.openFile("a", "a.md");
    await controller.send("메모를 참고해 조사", {
      researchGenre: "blog",
      contextPaths: ["b.md"],
    });
    expect(saved).toContain("b.md");
    expect(sent?.contextPaths).toEqual(["b.md"]);
    expect(
      controller.getSnapshot().projects.a.documents["b.md"].file.content
    ).toBe("연구에 쓸 최신 메모");
  });

  it("accepts server-assigned HTML IDs in a selected research document", async () => {
    const original = "<main>원문</main>";
    const canonical = '<main data-oc-id="main">새 자료</main>';
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file("page.html", original)],
        }),
        file: async () => file("page.html", original),
        save: async () => file("page.html", canonical, "v2"),
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    controller.edit("a", "page.html", "<main>새 자료</main>");
    await controller.send("이 자료로 조사", {
      researchGenre: "blog",
      contextPaths: ["page.html"],
    });
    expect(sent?.activeVersion).toBe("v2");
    expect(sent?.contextPaths).toEqual(["page.html"]);
  });

  it("does not save background typing that arrived after the research request started", async () => {
    const pending = deferred<CloudFile>();
    const saved: string[] = [];
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file(), file("b.md")],
        }),
        save: async (_id, input) => {
          saved.push(input.path);
          return input.path === "a.md"
            ? pending.promise
            : file(input.path, input.content, "v2");
        },
      })
    );
    await controller.initialize();
    await controller.openFile("a", "b.md");
    await controller.openFile("a", "a.md");
    controller.edit("a", "a.md", "저장 중");
    const sending = controller.send("자료로 조사", {
      researchGenre: "blog",
      contextPaths: ["b.md"],
    });
    controller.edit("a", "b.md", "요청 후 새로 입력");
    pending.resolve(file("a.md", "저장 중", "v2"));
    await expect(sending).rejects.toThrow(/변경/);
    expect(saved).toEqual(["a.md"]);
  });

  it("sends the canonical HTML version after the server assigns element IDs", async () => {
    const original = "<main><p>자료</p></main>";
    const edited = "<main><p>새 자료</p></main>";
    const canonical =
      '<main data-oc-id="main"><p data-oc-id="p">새 자료</p></main>';
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file("page.html", original)],
        }),
        file: async () => file("page.html", original),
        save: async () => file("page.html", canonical, "v2"),
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    controller.edit("a", "page.html", edited);
    await controller.send("더 간결하게");
    expect(sent?.activeVersion).toBe("v2");
    expect(
      controller.getSnapshot().projects.a.documents["page.html"].content
    ).toBe(canonical);
  });

  it("does not submit an HTML request against typing that happened during save", async () => {
    const original = '<main data-oc-id="main">자료</main>';
    const saved = '<main data-oc-id="main">저장할 자료</main>';
    const newer = '<main data-oc-id="main">더 새로운 자료</main>';
    const response = deferred<CloudFile>();
    let sent = false;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file("page.html", original)],
        }),
        file: async () => file("page.html", original),
        save: async () => response.promise,
        chat: async () => {
          sent = true;
          return { job };
        },
      })
    );
    await controller.initialize();
    controller.edit("a", "page.html", saved);
    const sending = controller.send("다듬기");
    controller.edit("a", "page.html", newer);
    response.resolve(file("page.html", saved, "v2"));
    await expect(sending).rejects.toThrow(/변경/);
    expect(sent).toBe(false);
    expect(
      controller.getSnapshot().projects.a.documents["page.html"].content
    ).toBe(newer);
  });

  it("resolves the same selected HTML node after canonical IDs shift source offsets", async () => {
    const selected = '<p data-oc-id="selected">같은 글 🙂</p>';
    const original = `<main data-oc-id="main">${selected}</main>`;
    const edited = original.replace(selected, `<h2>제목</h2>${selected}`);
    const canonical = edited.replace("<h2>", '<h2 data-oc-id="heading">');
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file("page.html", original)],
        }),
        file: async () => file("page.html", original),
        save: async () => file("page.html", canonical, "v2"),
        chat: async (_id, request) => {
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    controller.edit("a", "page.html", edited);
    await controller.send("영역 수정", {
      selection: {
        from: edited.indexOf(selected),
        to: edited.indexOf(selected) + selected.length,
        text: selected,
        nodeId: "selected",
      },
    });
    expect(sent?.selection?.nodeId).toBe("selected");
    expect(sent?.selection?.from).toBe(canonical.indexOf(selected));
    expect(canonical.slice(sent?.selection?.from, sent?.selection?.to)).toBe(
      selected
    );
  });

  it("loads the preferred file when a folder refresh supersedes initial loading", async () => {
    const first = deferred<CloudWorkspaceDetail>();
    const second = deferred<CloudWorkspaceDetail>();
    const started = deferred<void>();
    let calls = 0;
    const controller = new CloudWorkspaceController(
      service({
        detail: async () => {
          calls++;
          started.resolve();
          return calls === 1 ? first.promise : second.promise;
        },
      })
    );
    const initializing = controller.initialize("a", "notes.md");
    await started.promise;
    const refreshing = controller.refresh("a");
    const detail = { ...snapshot("a"), files: [file(), file("notes.md")] };
    first.resolve(detail);
    await initializing;
    second.resolve(detail);
    await refreshing;
    expect(controller.getSnapshot().projects.a.activePath).toBe("notes.md");
    expect(
      controller.getSnapshot().projects.a.documents["notes.md"]?.content
    ).toBe("original");
  });

  it("keeps recovered work when typing begins before browser hydration completes", async () => {
    const controller = new CloudWorkspaceController(service());
    await controller.initialize();
    controller.edit("a", "a.md", "new typing");
    controller.restoreDraft("a", "a.md", {
      file: file(),
      content: "previously unsaved work",
      recovery: "an earlier recovery",
    });
    const draft = controller.getSnapshot().projects.a.documents["a.md"];
    expect(draft.content).toBe("new typing");
    expect([draft.recovery, ...(draft.recoveryCopies ?? [])]).toContain(
      "previously unsaved work"
    );
    expect([draft.recovery, ...(draft.recoveryCopies ?? [])]).toContain(
      "an earlier recovery"
    );
  });

  it("ignores an older proposal read after an approval has completed", async () => {
    const original: CloudProposal = {
      id: "p1",
      jobId: job.id,
      path: "a.md",
      kind: "ai",
      instruction: "edit",
      explanation: "explanation",
      baseContent: "original",
      proposedContent: "approved",
      baseVersion: "v1",
      appliedVersion: null,
      createdAt: 1,
      status: "pending",
      changes: [
        {
          id: "c1",
          from: 0,
          to: 8,
          before: "original",
          after: "approved",
          decision: "pending",
        },
      ],
    };
    const late = deferred<CloudProposal>();
    let reads = 0;
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => (reads++ ? late.promise : original),
        decide: async () => ({
          proposal: {
            ...original,
            status: "accepted",
            appliedVersion: "v2",
            changes: [{ ...original.changes[0], decision: "accepted" }],
          },
          file: file("a.md", "approved", "v2"),
        }),
      })
    );
    await controller.initialize();
    await controller.openProposal("a", "p1");
    const reopening = controller.openProposal("a", "p1");
    await controller.decide("a", "p1", "all", "accepted");
    late.resolve(original);
    await reopening;
    expect(controller.getSnapshot().projects.a.proposalDetails.p1.status).toBe(
      "accepted"
    );
    expect(controller.getSnapshot().projects.a.proposals[0].pendingCount).toBe(
      0
    );
    expect(controller.getSnapshot().projects.a.documents["a.md"].content).toBe(
      "approved"
    );
  });

  it("reopens the selected file on reload instead of choosing a different first file", async () => {
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({
          ...snapshot(id),
          files: [file(), file("notes.md")],
        }),
      })
    );
    await controller.initialize("a", "notes.md");
    expect(controller.getSnapshot().projects.a.activePath).toBe("notes.md");
    expect(
      controller.getSnapshot().projects.a.documents["notes.md"].content
    ).toBe("original");
  });

  it("does not autosave a draft for a second request while the project agent is busy", async () => {
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({ ...snapshot(id), jobs: [job] }),
      })
    );
    await controller.initialize();
    controller.edit("a", "a.md", "a later draft");
    await expect(controller.send("another request")).rejects.toThrow(/작업/);
    expect(
      controller.getSnapshot().projects.a.documents["a.md"].file.content
    ).toBe("original");
  });
  it("does not let an older project refresh roll back a just-saved file", async () => {
    const pending = deferred<CloudWorkspaceDetail>();
    let reads = 0;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => (reads++ ? pending.promise : snapshot(id)),
      })
    );
    await controller.initialize();
    const refreshing = controller.refresh("a");
    controller.edit("a", "a.md", "new content");
    await controller.save("a", "a.md");
    pending.resolve(snapshot("a"));
    await refreshing;
    expect(controller.getSnapshot().projects.a.files[0].version).toBe("v2");
  });

  it("retries an uncertain chat request using the same request ID", async () => {
    const requests: CloudChatRequest[] = [];
    const controller = new CloudWorkspaceController(
      service({
        chat: async (_id, request) => {
          requests.push(request);
          if (requests.length === 1)
            throw new WorkspaceApiError(0, "connection lost");
          return { job };
        },
      })
    );
    await controller.initialize();
    await expect(controller.send("one request")).rejects.toThrow();
    await controller.retryRequest("a");
    expect(requests[0].requestId).toBe(requests[1].requestId);
    expect(controller.getSnapshot().projects.a.jobs).toHaveLength(1);
    expect(
      controller.getSnapshot().projects.a.uncertainRequest
    ).toBeUndefined();
  });

  it("saves a dirty file with its base version before sending its UTF-16 selection", async () => {
    const original = "🙂 문장 입니다.";
    const edited = "🙂 바뀐 문장 입니다.";
    let saved: { id: string; base: string | null; content: string } | undefined;
    let sent: CloudChatRequest | undefined;
    const controller = new CloudWorkspaceController(
      service({
        file: async () => file("a.md", original),
        save: async (id, input) => {
          saved = { id, base: input.baseVersion, content: input.content };
          return file("a.md", input.content, "v-edited");
        },
        chat: async (id, request) => {
          expect(saved).toEqual({ id: "a", base: "v1", content: edited });
          expect(id).toBe("a");
          sent = request;
          return { job };
        },
      })
    );
    await controller.initialize();
    controller.edit("a", "a.md", edited);
    await controller.send("교정", {
      selection: { from: 3, to: edited.length, text: "바뀐 문장 입니다." },
      model: "test-model",
    });
    expect(sent?.activeVersion).toBe("v-edited");
    expect(sent?.selection).toEqual({
      from: 3,
      to: edited.length,
      text: "바뀐 문장 입니다.",
    });
    expect(controller.getSnapshot().projects.a.documents["a.md"].content).toBe(
      edited
    );
  });

  it("keeps an in-flight job attached to its captured project after a switch", async () => {
    const response = deferred<{ job: CloudJob }>();
    const controller = new CloudWorkspaceController(
      service({
        chat: async () => response.promise,
      })
    );
    await controller.initialize();
    const sending = controller.send("다듬어 주세요");
    await controller.selectWorkspace("b");
    response.resolve({ job });
    await sending;
    const state = controller.getSnapshot();
    expect(state.activeId).toBe("b");
    expect(state.projects.a.jobs.map((item) => item.id)).toContain("job-a");
    expect(state.projects.b.jobs).toEqual([]);
    expect(state.projects.b.documents["a.md"].content).toBe("original");
  });

  it("preserves newer edits typed while an earlier save is in flight", async () => {
    const response = deferred<CloudFile>();
    const controller = new CloudWorkspaceController(
      service({
        save: async () => response.promise,
      })
    );
    await controller.initialize();
    controller.edit("a", "a.md", "saved edit");
    const saving = controller.save("a", "a.md");
    controller.edit("a", "a.md", "more recent typing");
    response.resolve(file("a.md", "saved edit", "v2"));
    await saving;
    const draft = controller.getSnapshot().projects.a.documents["a.md"];
    expect(draft.file.content).toBe("saved edit");
    expect(draft.content).toBe("more recent typing");
  });

  it("refreshes a 409 without overwriting the local draft or submitting chat", async () => {
    let reads = 0;
    let chats = 0;
    const controller = new CloudWorkspaceController(
      service({
        file: async () => (reads++ ? file("a.md", "external", "v3") : file()),
        save: async () => {
          throw new WorkspaceApiError(409, "Version changed");
        },
        chat: async () => {
          chats++;
          return { job };
        },
      })
    );
    await controller.initialize();
    controller.edit("a", "a.md", "my unsaved text");
    await expect(controller.send("다듬기")).rejects.toThrow();
    const draft = controller.getSnapshot().projects.a.documents["a.md"];
    expect(draft.content).toBe("my unsaved text");
    expect(draft.file.version).toBe("v1");
    expect(draft.remote?.content).toBe("external");
    expect(chats).toBe(0);
  });

  it("retains an already loaded running job for reload polling", async () => {
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) => ({ ...snapshot(id), jobs: [job] }),
        job: async () => ({
          ...job,
          status: "failed",
          error: "Retry this request",
        }),
      })
    );
    await controller.initialize();
    await controller.poll();
    expect(controller.getSnapshot().projects.a.jobs[0].status).toBe("failed");
    expect(controller.getSnapshot().projects.a.jobs[0].error).toBe(
      "Retry this request"
    );
  });

  it("uses only server change decisions and does not replace another file", async () => {
    const proposal: CloudProposal = {
      id: "p1",
      jobId: job.id,
      path: "a.md",
      kind: "ai",
      instruction: "edit",
      explanation: "explanation",
      baseContent: "original",
      proposedContent: "approved",
      baseVersion: "v1",
      appliedVersion: null,
      createdAt: 1,
      status: "pending",
      changes: [
        {
          id: "c1",
          from: 0,
          to: 8,
          before: "original",
          after: "approved",
          decision: "pending",
        },
      ],
    };
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => proposal,
        decide: async (id, proposalId, decisions) => {
          expect({ id, proposalId, decisions }).toEqual({
            id: "a",
            proposalId: "p1",
            decisions: { c1: "accepted" },
          });
          return {
            proposal: {
              ...proposal,
              status: "accepted",
              appliedVersion: "v2",
              changes: [{ ...proposal.changes[0], decision: "accepted" }],
            },
            file: file("a.md", "approved", "v2"),
          };
        },
      })
    );
    await controller.initialize();
    await controller.openProposal("a", "p1");
    await controller.selectWorkspace("b");
    await controller.decide("a", "p1", "c1", "accepted");
    expect(controller.getSnapshot().projects.a.documents["a.md"].content).toBe(
      "approved"
    );
    expect(controller.getSnapshot().projects.b.documents["a.md"].content).toBe(
      "original"
    );
  });
});

describe("full correction copies", () => {
  const proposal: CloudProposal = {
    id: "copy-proposal",
    jobId: job.id,
    path: "a.md",
    kind: "ai",
    instruction: "proofread",
    explanation: "full correction",
    baseContent: "original",
    proposedContent: "full correction",
    baseVersion: "v1",
    appliedVersion: "v1",
    createdAt: 1,
    status: "pending",
    changes: [
      {
        id: "c1",
        from: 0,
        to: 8,
        before: "original",
        after: "full correction",
        decision: "pending",
      },
    ],
  };
  const savedCopy = { path: "a.교정본-20261025.md", createdAt: 2 };
  const saved = {
    proposal: { ...proposal, savedCopy },
    file: file(savedCopy.path, "full correction", "v2"),
  };
  const correction = {
    ...savedCopy,
    proposalId: proposal.id,
    sourcePath: "a.md",
    baseContent: "original",
    proposedContent: "full correction",
  };

  it("adds the server copy and preserves unsaved source edits and decisions", async () => {
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => proposal,
        copy: async (id, proposalId) => {
          expect({ id, proposalId }).toEqual({
            id: "a",
            proposalId: proposal.id,
          });
          return saved;
        },
      })
    );
    await controller.initialize();
    await controller.openProposal("a", proposal.id);
    controller.edit("a", "a.md", "my newer draft");
    await controller.saveProposalCopy("a", proposal.id);
    const project = controller.getSnapshot().projects.a;
    expect(project.documents["a.md"].content).toBe("my newer draft");
    expect(project.documents["a.md"].file.content).toBe("original");
    expect(project.documents[savedCopy.path].content).toBe("full correction");
    expect(project.proposalDetails[proposal.id].changes).toEqual(
      proposal.changes
    );
    expect(project.proposals[0].savedCopy).toEqual(savedCopy);
    expect(project.activePath).toBe("a.md");
    expect(project.copying).toEqual([]);
  });

  it("does not navigate back or replace drafts when a copy finishes in another project", async () => {
    const pending = deferred<typeof saved>();
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => proposal,
        copy: async () => pending.promise,
      })
    );
    await controller.initialize();
    await controller.openProposal("a", proposal.id);
    const copying = controller.saveProposalCopy("a", proposal.id);
    controller.dismissProposal("a");
    await controller.openFile("a", "notes.md");
    await controller.selectWorkspace("b");
    controller.edit("b", "a.md", "keep writing in project b");
    pending.resolve(saved);
    await copying;
    const state = controller.getSnapshot();
    expect(state.activeId).toBe("b");
    expect(state.projects.a.activePath).toBe("notes.md");
    expect(state.projects.a.reviewId).toBeUndefined();
    expect(state.projects.a.documents[savedCopy.path].content).toBe(
      "full correction"
    );
    expect(state.projects.b.documents[savedCopy.path]).toBeUndefined();
    expect(state.projects.b.documents["a.md"].content).toBe(
      "keep writing in project b"
    );
  });

  it("serializes copying and approval for the same proposal", async () => {
    const pending = deferred<typeof saved>();
    let copies = 0;
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => proposal,
        copy: async () => {
          copies++;
          return pending.promise;
        },
      })
    );
    await controller.initialize();
    await controller.openProposal("a", proposal.id);
    const copying = controller.saveProposalCopy("a", proposal.id);
    expect(controller.getSnapshot().projects.a.copying).toEqual([proposal.id]);
    await controller.saveProposalCopy("a", proposal.id);
    await controller.decide("a", proposal.id, "all", "accepted");
    pending.resolve(saved);
    await copying;
    expect(copies).toBe(1);
    expect(
      controller.getSnapshot().projects.a.proposalDetails[proposal.id].status
    ).toBe("pending");
  });

  it("does not start a copy while approval is still in flight", async () => {
    const pending = deferred<{ proposal: CloudProposal; file: CloudFile }>();
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => proposal,
        decide: async () => pending.promise,
      })
    );
    await controller.initialize();
    await controller.openProposal("a", proposal.id);
    const deciding = controller.decide("a", proposal.id, "all", "accepted");
    await controller.saveProposalCopy("a", proposal.id);
    pending.resolve({
      proposal: {
        ...proposal,
        status: "accepted",
        changes: [{ ...proposal.changes[0], decision: "accepted" }],
      },
      file: file("a.md", "full correction", "v2"),
    });
    await deciding;
    expect(controller.getSnapshot().projects.a.files).toHaveLength(1);
  });

  it("releases a failed copy for retry without dropping the source draft", async () => {
    let attempt = 0;
    const controller = new CloudWorkspaceController(
      service({
        proposal: async () => proposal,
        copy: async () => {
          if (attempt++ === 0) throw new WorkspaceApiError(0, "응답 확인 실패");
          return saved;
        },
      })
    );
    await controller.initialize();
    await controller.openProposal("a", proposal.id);
    controller.edit("a", "a.md", "unsaved work");
    await expect(controller.saveProposalCopy("a", proposal.id)).rejects.toThrow(
      "응답 확인 실패"
    );
    expect(controller.getSnapshot().projects.a.copying).toEqual([]);
    expect(controller.getSnapshot().projects.a.files).toHaveLength(1);
    await controller.saveProposalCopy("a", proposal.id);
    expect(controller.getSnapshot().projects.a.documents["a.md"].content).toBe(
      "unsaved work"
    );
    expect(
      controller.getSnapshot().projects.a.documents[savedCopy.path].content
    ).toBe("full correction");
  });

  it("ignores a proposal read and project refresh started before a copy was saved", async () => {
    const lateProposal = deferred<CloudProposal>();
    const lateProject = deferred<CloudWorkspaceDetail>();
    let proposalReads = 0;
    let projectReads = 0;
    const controller = new CloudWorkspaceController(
      service({
        detail: async (id) =>
          projectReads++ ? lateProject.promise : snapshot(id),
        proposal: async () =>
          proposalReads++ ? lateProposal.promise : proposal,
        copy: async () => saved,
      })
    );
    await controller.initialize();
    await controller.openProposal("a", proposal.id);
    const reopening = controller.openProposal("a", proposal.id);
    const refreshing = controller.refresh("a");
    await controller.saveProposalCopy("a", proposal.id);
    lateProposal.resolve(proposal);
    lateProject.resolve(snapshot("a"));
    await Promise.all([reopening, refreshing]);
    const project = controller.getSnapshot().projects.a;
    expect(project.proposalDetails[proposal.id].savedCopy).toEqual(savedCopy);
    expect(project.proposals[0].savedCopy).toEqual(savedCopy);
    expect(project.files.map((item) => item.path)).toContain(savedCopy.path);
  });

  it("hydrates the immutable comparison record when loading copy history", async () => {
    const controller = new CloudWorkspaceController(
      service({
        history: async (_id, path) => ({
          revisions: [],
          correction: path === savedCopy.path ? correction : null,
        }),
      })
    );
    await controller.initialize();
    await controller.loadHistory("a", savedCopy.path);
    await controller.loadHistory("a", "a.md");
    expect(
      controller.getSnapshot().projects.a.corrections[savedCopy.path]
    ).toEqual(correction);
    expect(
      controller.getSnapshot().projects.a.corrections["a.md"]
    ).toBeUndefined();
  });

  it.each([false, true])(
    "preserves a newer saved copy when its initial save response arrives late (continued typing: %s)",
    async (continuedTyping) => {
      const pending = deferred<typeof saved>();
      let remoteCopy: CloudFile | undefined;
      const controller = new CloudWorkspaceController(
        service({
          proposal: async () => proposal,
          detail: async (id) => ({
            ...snapshot(id),
            files: [file(), ...(remoteCopy ? [remoteCopy] : [])],
          }),
          file: async (_id, path) =>
            path === savedCopy.path ? remoteCopy! : file(path),
          copy: async () => {
            remoteCopy = saved.file;
            return pending.promise;
          },
          save: async (_id, input) => {
            remoteCopy = file(input.path, input.content, "v3");
            return remoteCopy;
          },
        })
      );
      await controller.initialize();
      await controller.openProposal("a", proposal.id);
      const copying = controller.saveProposalCopy("a", proposal.id);
      await controller.refresh("a");
      await controller.openFile("a", savedCopy.path);
      controller.edit("a", savedCopy.path, "manual saved edit");
      await controller.save("a", savedCopy.path);
      if (continuedTyping)
        controller.edit("a", savedCopy.path, "continued typing");
      const seen: string[] = [];
      const unsubscribe = controller.subscribe(() =>
        seen.push(
          controller.getSnapshot().projects.a.documents[savedCopy.path].content
        )
      );
      pending.resolve(saved);
      await copying;
      unsubscribe();
      const project = controller.getSnapshot().projects.a;
      expect(project.documents[savedCopy.path].content).toBe(
        continuedTyping ? "continued typing" : "manual saved edit"
      );
      expect(project.documents[savedCopy.path].file.version).toBe("v3");
      expect(project.documents[savedCopy.path].remote).toBeUndefined();
      expect(
        project.files.find((item) => item.path === savedCopy.path)?.version
      ).toBe("v3");
      expect(seen).not.toContain("full correction");
    }
  );
});
