# HTML workspace

The approved first release lets an author use project files and reference
excerpts to generate a static HTML/CSS document, preview it, select an element,
request an AI revision, compare the rendered versions, approve the complete
change, and download the HTML.

The existing cloud workspace remains the entry point. Markdown editing,
review, local-folder synchronization, and saved versions keep working.

## Document and editing contract

- Recognize `.html` and `.htm` alongside existing document extensions.
- Store HTML source, including inline CSS. The application assigns persistent,
  unique `data-oc-id` values to editable body elements when HTML is saved or
  proposed. Preserve existing valid IDs and source formatting.
- Use existing `TextSelection` offsets and exact source text, with an optional
  `nodeId` for HTML selections. Optional `label`, `previewText`, and `sourceIds`
  are client presentation data. The API must resolve and verify the node ID,
  offsets, and source text against the current file.
- An HTML selection is a complete element. The agent receives surrounding
  document context but may only replace that element; its root ID must remain
  stable. Local style changes use inline `style` attributes in the selected
  subtree. Stylesheet changes require a whole-document request.
- An HTML proposal has one atomic review change. Approval validates the full
  assembled document and the existing base-version precondition.
- `outputFormat: "html"` on a chat request asks for a new HTML file using
  available sources. It is mutually exclusive with selection and researchGenre.
- Optional `data-source-ids` contains a JSON array of reference IDs. Display
  matching project sources for a selected region; retain actual citation links.
  Reference IDs and excerpts are evidence context, never agent instructions.

## Preview and interaction

- Add HTML preview/source views using the existing workspace styling.
- The preview is a sandboxed iframe without same-origin permission. Sanitize
  the HTML, deny generated scripts, and use CSP to allow only the application's
  selection bridge. Deny external requests by default, including CSS requests.
- Source-to-node mapping uses HTML parser source locations, never text search.
  Only app-generated selection messages from the current iframe and preview
  session are accepted; all values are checked against the source map.
- Provide mouse/touch selection, a keyboard-accessible region picker, an
  explicit selection clear action, and clear selected-region labels.
- Render before/after previews for proposed HTML, including newly generated
  files before approval. Keep source diffs available.
- Download source HTML without preview scripts, selection overlays, or CSP
  injected solely for preview.

## Scope

The first release supports static HTML/CSS, not generated JavaScript, external
stylesheets, embedded browsing contexts, or multi-file applications. Direct
source editing is available. Rich text editing and arbitrary text-range
selection inside HTML are later work.

## Validation

Prove correct UTF-16/Python offset handling, duplicate text in different regions,
stale selections, out-of-region edits, stable IDs, malformed HTML rejection,
atomic approval, citation preservation, and execution isolation. Run the
existing web/backend suites, type checking, lint, production build, and a
browser exercise of generation, preview selection, review, and download.
