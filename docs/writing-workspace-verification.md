# Writing workspace implementation verification

Verified on **2026-10-25**, against the working-tree implementation based on `2232b6d6a947f56016ea3b147f44ae9dc54ed491`.

This record covers the initial implementation checks before deployment. The later
production release passed 55 frontend tests, container health/authentication
checks, real task-role Opus inference and Firecrawl extraction; see the
[production deployment record](./deployment/canvas-hi-yoo.md).

## Automated checks

| Check | Result |
| --- | --- |
| Frontend `yarn test` | 39 tests passed, 7 files |
| Frontend type checking | Passed standalone and within the final production build |
| Frontend `yarn lint` | No errors; 17 existing legacy warnings |
| Frontend `yarn build` | Passed; all 15 generated pages, including `/canvas` |
| Backend `python -m pytest -q` | 29 passed, 41 subtests passed |
| Backend dependency consistency | All 77 installed environment packages compatible |
| `git diff --check` | Passed |

The backend emits one pre-existing `datetime.utcnow()` deprecation warning from its memory store. Production and model APIs were tested with fake model responses; no paid inference was performed.

## Browser checks

`apps/web/tests/workspace_smoke.py` passed all eight workflows:

1. Import a Markdown file, capture an exact selection, view a proposal without mutating the original, approve it, and reload the persisted draft.
2. Switch files while inference is pending and keep the response attached to its original document; reject without mutation.
3. Add source evidence, insert a clickable inline citation, and export Markdown with original references intact.
4. Change a URL while scraping is pending and prevent evidence from the first URL being attached to the second.
5. Connect real browser filesystem handles, detect an external change, review it, and reload persisted handles.
6. Catch a file change immediately before save, preserve the external file, explicitly retain the browser draft, and save it.
7. Recover a deleted file through the normal Save button without retaining the obsolete folder binding.
8. Render at 390px, avoid horizontal overflow, and open/close file and inspector panels.

These tests use isolated native OPFS handles instead of interacting with the OS directory picker. AI and Firecrawl responses are stubbed. They do not establish account-level Bedrock permissions, native OS picker permissions, or atomic coordination with another process during the final filesystem commit window.

The retained `/canvas` was also exercised at desktop and mobile sizes with saved messages, BlockNote rendering, version navigation/comparison, chat resizing/collapse, composer input, and attachment add/remove. There were no page or console errors.

## Independent review and fixes

| Review finding | Resolution |
| --- | --- |
| A stale browser tab could overwrite another tab's drafts and metadata | IndexedDB transaction revision checks reject stale writes; a regression test confirms the other tab's documents remain reachable |
| Rendered text could be mapped to matching text inside a citation URL | Map through Markdown AST text positions; reject ambiguous formatted selections and clear previous selection |
| Long citation URLs exceeded the backend source-ID limit | Stable bounded source IDs; regression with a long URL |
| Partially approving a moved citation could delete it | Validate the accepted document after every AI approval; reference-dependent edits can be approved together |
| A whole-document diff could relocate a selected deletion among repeated text | Diff the selection itself and offset changes into the original document |
| A delayed source response could attach evidence to a different URL | Bind retrieval to the requested URL and cancel/discard it when the URL changes |
| Saving a missing file retained its former folder/path | Treat a newly picked target as a new file binding |
| Request scope appeared to change during inference | Display the captured request selection while it is pending |
| A document grown beyond the read-size limit could be written before the error was found | Check UTF-8 byte size before opening a write |

## Implementation decisions

- Markdown is the canonical file format; reading does not reserialize the source through a rich-text editor.
- The browser retains drafts and handles in IndexedDB; disk writes remain explicit.
- The new workspace is the home page, while conversation functionality remains at `/canvas`.
- Unsupported directory-picker environments use import/download.
- DOCX informs review presentation and document hierarchy; DOCX format round-tripping is not included.
- The existing Yarn Classic workflow is retained, with current direct application dependency pins. The verification environment used Node 22.19.0 and Python 3.13.8.
- TypeScript 7 requires a compatible native lint path, so Oxlint replaces the incompatible legacy parser stack.
- Bedrock model support is documented from AWS primary sources. Live account inference and scraping are environment checks, not claimed by this verification.

See [workspace usage](./writing-workspace.md), [dependency versions](./dependency-upgrade.md), and [model configuration and evidence](./bedrock-models.md).
