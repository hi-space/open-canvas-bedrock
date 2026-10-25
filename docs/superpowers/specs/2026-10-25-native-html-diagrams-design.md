# Native technical diagrams in HTML

## User direction

HTML reports may draw diagrams directly with HTML/CSS or inline SVG. A diagram
should explain technical structure, responsibilities, relationships, or request
order. Use an installed diagram skill when its specialized assets or layout add
value; an HTML diagram must not depend on a diagram skill or rasterizer.

## Shipped behavior

- HTML research defaults to native diagrams. Hierarchies/layers use responsive
  HTML/CSS; connected flows and sequences use inline SVG.
- The model supplies a bounded semantic diagram specification: components with
  responsibilities, layers, and labeled directed relationships. The application
  computes layout and escapes all labels. Do not omit unsupported edges silently.
- The outline explains why a figure helps the technical explanation, and can
  explicitly select an available specialized skill. If that renderer is missing
  or fails, HTML falls back to native rendering.
- Markdown research retains its current PNG/skill behavior.
- Native diagrams stay in the canonical HTML, preview, approved file, and offline
  download. No image fetch or PNG generation is needed for native output.
- Normal workspace HTML generation/editing may also use the same static SVG subset.
- SVG is one selectable/editable region. Preserve its complete source subtree and
  all surrounding HTML when a selected diagram is replaced.
- Allow SVG shapes, paths, groups, and text only. Reject scripts, foreignObject,
  HTML integration inside SVG text/description, animations, use/image, URI-bearing
  attributes, non-SVG namespaces, and resource paint URLs. Keep the preview sandbox
  and source/approval validation.
- Native figure captions and source citations remain attached to the corresponding
  document section. Internal figure placeholders are resolved only from trusted
  graph figures and never remain in a saved HTML file.

## Builder choices

- Extend the existing `FigurePlan` with `renderer: auto | native | skill` and a
  short `reason`; defaults preserve existing requests and test fixtures.
- Pass `outputFormat` into the research state. Native capabilities are always
  available for HTML; installed-skill availability is separately described.
- Use a new `diagrams/native.py` with a Pydantic specification and deterministic
  HTML/SVG rendering. At most four rows, four nodes per row, sixteen nodes total,
  and twenty-four relationships; sequences have at most six participants.
- Native markup is inserted at trusted figure placeholders after Markdown parsing.
  User/model-authored raw HTML remains escaped by the Markdown adapter.
- Trusted figure boundaries split Markdown sections before parsing, preventing an
  unclosed code fence from absorbing a figure. Source extraction uses the same
  boundaries, and every expected native figure must be consumed.
- Paint connector strokes before number badges. Keep SVG at its natural text
  scale in a horizontally scrollable viewport, with width-aware text wrapping.
  Sanitized SVG scroll wrappers are keyboard-focusable.
- Static SVG elements: svg, g, rect, circle, ellipse, line, polyline, polygon,
  path, text, tspan, title, desc. SVG roots get editor IDs; SVG descendants do not
  become separate selectable regions.
- No new dependency, service, skill installation, or deployment is needed.
- Continue in the existing `codex/research-html` managed worktree.

## Evidence and verification

Use the technical-visualizer skill's entity/relationship/layer analysis, not its
default output-file workflow; the user's requested destination is the app's HTML.
Consult the HTML foreign-content rules and DOMPurify SVG profile documentation.

Tests cover valid SVG, parser integration/namespace traps, selected subtree edits,
SVG survival in the sanitized preview, every semantic edge, skill-free HTML
research, deliberate skill selection/fallback, caption/citation assembly, and
native SVG in offline downloads. Use real Chromium to inspect the generated
technical diagram and confirm no research-image requests in the native workflow.
