# File-based writing workspace

## Intent

Make Open Canvas useful alongside local writing tools: open Markdown files created by Claude Code or Codex, see external changes, request an AI revision of a sentence or paragraph, review the actual changes, and apply only approved edits. Show citations where a claim is made and make the original reference directly reachable.

The user also requested upgrading the project's dependencies and model choices to the latest stable releases available when this work is performed.

## Product decisions

- The home page becomes a Korean-language writing workspace. The previous conversation canvas remains accessible at `/canvas`, including existing thread links.
- Markdown is the canonical, lossless document format. Support `.md`, `.markdown`, and `.txt`. A rich reading view and a Markdown editing view share that source.
- Use the existing Next.js/React/TypeScript frontend and FastAPI/Amazon Bedrock backend, upgraded to current stable versions. Do not introduce a hosted storage service.
- Connect a directory through the browser File System Access API. The user explicitly chooses the directory. Persist drafts, revisions, and directory handles in IndexedDB on this browser.
- On browsers without directory write support, offer file import and Markdown download. Describe the difference in the interface rather than claiming synchronization.
- Use an editorial layout: quiet warm background, white document page, green approval accents, restrained typography, a compact file rail, and a right panel for revision review, sources, and history.
- Treat the user's requested UX changes and dependency/model upgrades as the authorized scope. File format is an implementation assumption pending their optional clarification; Markdown best matches the existing editor and local coding tools.

## Layout and workflows

### File workspace

The left rail contains folder connection, file import, a new document action, search, filenames with relative paths, and status. The document header shows its filename, draft/disk status, editor/reading tabs, save, and export.

Opening a directory scans supported text documents, skipping dot-directories, `node_modules`, and build output. Bound scanning and document sizes and report skipped files. Refresh automatically and on focus; provide a manual refresh.

An external change is a proposed replacement, not an invisible overwrite. If the browser draft also changed, preserve both versions, show the conflict, and require review. Saving re-reads the file before writing and refuses to overwrite a file that changed since the known disk snapshot. File deletion or permission loss leaves the browser draft available.

New and imported files work without a backend connection. Browser draft persistence and disk save are separate statuses. Switching files and reloading must preserve drafts and pending proposals.

### Editing and review

Markdown editing provides exact selection offsets. The reading view supports paragraph-level requests and selections that can be unambiguously mapped to the source; ambiguous formatted selections lead the user to the source editor rather than guessing.

Selection opens a compact action bar: proofread, clarify, shorten, and custom instruction. The right panel keeps the selected passage visible while the request runs and shows loading, cancellation, and actionable failures.

AI output is a proposal held outside the document. Each change shows removed and inserted text. The user can accept/reject individual changes or the entire proposal. Unchanged content is not marked as replaced, following the DOCX skill's tracked-change principle.

Proposals retain an immutable base document and per-change decisions. Applying a change verifies that the draft still matches the expected base plus previously accepted changes. Manual edits or external updates make the proposal stale rather than silently applying it to a different location. Repeated text and Korean/emoji characters must not target the wrong occurrence.

Approved changes update the draft and append bounded revision history. Writing to disk remains an explicit Save action. History can preview a prior revision and restore it as a new draft revision.

### References

Sources have stable IDs, title, HTTP(S) URL, and optional excerpt. Users can add a source URL and supplied excerpt, see already linked references, and insert a citation at the current selection/cursor. When configured, the existing Firecrawl service can retrieve a reference; failure leaves a useful manual path.

AI requests receive the supplied sources and excerpts. Instruct the model to cite only supplied evidence with standard Markdown links, never fabricate a reference or a claim from a URL alone. Existing source links in the document must survive rewrites. Numeric inline citations appear as compact, accessible links that open the source.

Markdown import/export preserves source links. DOCX is design inspiration for precise revision tracking and document hierarchy; full Word format round-tripping is outside this initial scope unless the user's file-format clarification requests it.

## Backend interface

Add a stateless `POST /api/writing/propose` endpoint, separate from the existing mutating conversation graph.

Request:

```typescript
type WritingRequest = {
  document: string;
  selectedText?: string;
  instruction: string;
  model?: string;
  sources: { id: string; title: string; url: string; excerpt?: string }[];
};
```

Response:

```typescript
type WritingResponse = {
  replacement: string;
  explanation: string;
};
```

When `selectedText` is present, `replacement` replaces only that selection; otherwise it represents a whole-document proposal. Offsets remain entirely on the client to avoid Python/JavaScript Unicode offset differences. Validate input bounds, selection membership, source URLs, allowed model IDs, generated JSON, response truncation, and invented citation URLs. A failed/truncated request never becomes an approvable proposal.

Reuse the existing Bedrock model factory and server-side AWS credential chain. Calls travel through same-origin Next.js API routes. Do not expose credentials in the browser. Model catalog responses remain compatible with the existing `/api/models/list` contract.

## Upgrade requirements

- Resolve each retained direct npm dependency from the registry's stable `latest` tag. Remove obsolete unused packages instead of carrying incompatible libraries with no consumers.
- Resolve backend dependencies from stable PyPI releases and retain a reproducible pinned dependency set.
- Upgrade React/Next.js, lint/configuration, async framework APIs, and affected component APIs together. Do not suppress type checking or enable global peer-dependency bypasses as the solution.
- Verify current Bedrock model IDs, API compatibility, and inference regions in primary AWS documentation. Use a current supported Claude model by default; explain what was verified and distinguish documentation from an actual account invocation.
- Keep frontend and backend model catalogs consistent, support configured region/model overrides, and handle unsupported sampling parameters for newer model families.

## Verification

Unit tests must cover exact selection replacement, per-change review, stale proposals, repeated text, Unicode, source validation/citation preservation, and disk conflicts. Backend tests use a fake model response at the external AI boundary, with no paid inference.

Run frontend tests, type checking, lint, and a production build; run backend tests and dependency consistency checks. Exercise the running UI at desktop and mobile sizes, including import, selecting text, proposal approval/rejection, history, citations, persistence, and a real file-handle test where the browser environment supports it.

## Explicit limits

No operating-system background watcher runs after the browser closes. No automatic Git commits, deployment, or external publication. Browser permission prompts are part of choosing and saving local files. Real inference depends on this environment's AWS access and model entitlement; report whether it was actually exercised.
