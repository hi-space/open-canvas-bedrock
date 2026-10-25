# Frontend dependency upgrade

Registry checked: **2026-10-25T02:12:23+00:00**. Scope: `apps/web` and the retained conversation canvas. Backend upgrades and Bedrock model verification are recorded separately.

Every retained direct dependency is pinned to the stable `latest` version returned by the public npm registry during this task. Versions are exact rather than ranges. Yarn Classic `1.22.22` remains the package manager, explicitly declared in `packageManager`; the generated `yarn.lock` is the sole lockfile. The stale npm lockfile was removed. No peer-dependency bypasses or compiler-error suppression were added.

## Platform and compatibility

- Next.js `14.2.25` → `16.4.3`; React/React DOM `18` → `19.3.1`; TypeScript `5` → `7.0.2`; Tailwind CSS `3` → `4.3.3`; Vitest `3` → `5.0.5`.
- The retained Webpack configuration sets the browser worker global used by FFmpeg. `dev` and `build` explicitly select the supported Webpack bundler so Next 16 does not silently ignore that configuration.
- TypeScript 7 is a native compiler and does not expose the former compiler API. Next 16.4 supports invoking the project compiler CLI through `experimental.useTypeScriptCli`; this is enabled explicitly. `typecheck` generates route types and runs `tsc --noEmit`. Production builds still run full TypeScript checks.
- The latest `typescript-eslint` release, `8.72.0`, declares a TypeScript peer range of `>=4.8.4 <6.1.0`; it cannot use the TypeScript 7 compiler API. The old ESLint preset/parser stack was therefore replaced with current Oxlint, which parses TypeScript natively and includes Next, React, TypeScript, import, and accessibility rules. No incompatible parser was forced into the installation.
- Oxlint keeps unused bindings and the classic Rules of Hooks as errors, with effect-dependency and intentional autofocus diagnostics as warnings. React Compiler-only `refs`, `immutability`, and `set-state-in-effect` checks are disabled because this application does not enable React Compiler. The SVG icon file retains valid `role="img"` attributes, with a file-specific exception for the rule that incorrectly recommends HTML image elements for inline SVGs. Dynamic Lucide icon lookup is explicitly permitted by the namespace-import rule.
- Tailwind now uses `@tailwindcss/postcss` and explicit `@config` loading. Renamed shadow, radius, blur, and outline utility classes were migrated to retain their prior meaning. The removed assistant-ui Tailwind plugin was replaced by the equivalent application utility classes where used.
- A browser test exposed `Transaction.changedRange` missing from an older hoisted ProseMirror transform despite current BlockNote/Tiptap packages. Regenerating the complete lockfile refreshes mutually compatible transitive versions; no package-resolution override was used.
- assistant-ui hooks now use `useAui`/`useAuiState`; message extraction and message-part types use their current APIs. Attachment source metadata comes from the client scope. React 19 ref types include `null`.
- Resizable panels now use `Group`/`Separator`, `orientation`, and explicit percentage strings: current panel versions interpret numbers as pixels. A collapsed chat leaves one full-width canvas panel without a dangling separator.
- Existing inaccurate user and artifact-union types were corrected, while authentication remains disabled. The no-op middleware was removed. Artifact-history controls now reference the version-navigation fields actually returned by the hook. Unused imports, callbacks, and unused diff computations were removed; the retained side-by-side viewer behavior remains unchanged.

## Direct dependency audit

“Before” shows the original manifest declarations; “After” shows the exact installed version. The prior lockfile was fully regenerated after a browser test exposed stale transitive ProseMirror copies.

| Package | Before | After | Notes |
| --- | --- | --- | --- |
| `@assistant-ui/react` | `^0.7.68` | `0.15.31` | Stable npm latest |
| `@assistant-ui/react-markdown` | `^0.7.2` | `0.14.24` | Stable npm latest |
| `@assistant-ui/react-syntax-highlighter` | `^0.7.2` | `0.14.7` | Stable npm latest |
| `@babel/runtime` | `—` | `8.0.8` | Added: workspace feature, explicit peer, or current tooling |
| `@blocknote/core` | `^0.42.3` | `0.56.0` | Stable npm latest |
| `@blocknote/mantine` | `^0.42.3` | `removed` | Removed: unused or replaced tooling |
| `@blocknote/react` | `^0.42.3` | `0.56.0` | Stable npm latest |
| `@blocknote/shadcn` | `^0.42.3` | `0.56.0` | Stable npm latest |
| `@codemirror/autocomplete` | `—` | `6.20.4` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/lang-cpp` | `^6.0.2` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-html` | `^6.4.9` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-java` | `^6.0.1` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-javascript` | `^6.2.2` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-json` | `^6.0.1` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-markdown` | `—` | `6.5.2` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/lang-php` | `^6.0.1` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-python` | `^6.1.6` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-rust` | `^6.0.1` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-sql` | `^6.8.0` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/lang-xml` | `^6.1.0` | `removed` | Removed: unused or replaced tooling |
| `@codemirror/language` | `—` | `6.13.1` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/lint` | `—` | `6.9.7` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/search` | `—` | `6.7.2` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/state` | `—` | `6.7.6` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/theme-one-dark` | `—` | `6.1.3` | Added: workspace feature, explicit peer, or current tooling |
| `@codemirror/view` | `—` | `6.43.15` | Added: workspace feature, explicit peer, or current tooling |
| `@eslint/js` | `^9.12.0` | `removed` | Removed: unused or replaced tooling |
| `@ffmpeg/ffmpeg` | `^0.12.15` | `0.12.15` | Stable npm latest |
| `@ffmpeg/util` | `^0.12.2` | `0.12.2` | Stable npm latest |
| `@floating-ui/dom` | `—` | `1.8.0` | Added: workspace feature, explicit peer, or current tooling |
| `@langchain/community` | `^0.3.58` | `removed` | Removed: unused or replaced tooling |
| `@langchain/core` | `^1.0.6` | `1.3.0` | Stable npm latest |
| `@langchain/langgraph-sdk` | `^0.0.107` | `1.12.7` | Stable npm latest |
| `@mendable/firecrawl-js` | `1.10.1` | `removed` | Removed: unused or replaced tooling |
| `@nextjournal/lang-clojure` | `^1.0.0` | `removed` | Removed: unused or replaced tooling |
| `@radix-ui/react-accordion` | `^1.2.2` | `1.3.1` | Stable npm latest |
| `@radix-ui/react-avatar` | `^1.1.2` | `1.3.1` | Stable npm latest |
| `@radix-ui/react-checkbox` | `^1.1.2` | `1.4.1` | Stable npm latest |
| `@radix-ui/react-dialog` | `^1.1.5` | `1.3.1` | Stable npm latest |
| `@radix-ui/react-dropdown-menu` | `^2.1.2` | `2.2.1` | Stable npm latest |
| `@radix-ui/react-hover-card` | `^1.1.2` | `1.2.1` | Stable npm latest |
| `@radix-ui/react-icons` | `^1.3.2` | `1.3.2` | Stable npm latest |
| `@radix-ui/react-label` | `^2.1.0` | `2.1.17` | Stable npm latest |
| `@radix-ui/react-navigation-menu` | `^1.2.1` | `removed` | Removed: unused or replaced tooling |
| `@radix-ui/react-popover` | `^1.1.2` | `1.3.1` | Stable npm latest |
| `@radix-ui/react-progress` | `^1.1.0` | `1.2.1` | Stable npm latest |
| `@radix-ui/react-select` | `^2.1.2` | `2.4.1` | Stable npm latest |
| `@radix-ui/react-slider` | `^1.2.1` | `1.6.1` | Stable npm latest |
| `@radix-ui/react-slot` | `^1.1.1` | `1.5.0` | Stable npm latest |
| `@radix-ui/react-switch` | `^1.2.6` | `removed` | Removed: unused or replaced tooling |
| `@radix-ui/react-toast` | `^1.2.2` | `1.3.1` | Stable npm latest |
| `@radix-ui/react-tooltip` | `^1.1.7` | `1.4.1` | Stable npm latest |
| `@replit/codemirror-lang-csharp` | `^6.2.0` | `removed` | Removed: unused or replaced tooling |
| `@tailwindcss/postcss` | `—` | `4.3.3` | Added: workspace feature, explicit peer, or current tooling |
| `@tiptap/extensions` | `^3.11.0` | `removed` | Removed: unused or replaced tooling |
| `@types/diff-match-patch` | `^1.0.36` | `1.0.36` | Moved to development dependencies |
| `@types/eslint__js` | `^8.42.3` | `removed` | Removed: unused or replaced tooling |
| `@types/js-cookie` | `^3.0.6` | `3.0.6` | Stable npm latest |
| `@types/lodash` | `^4.17.12` | `4.17.27` | Stable npm latest |
| `@types/node` | `^20` | `26.6.5` | Stable npm latest |
| `@types/pdf-parse` | `^1.1.4` | `removed` | Removed: unused or replaced tooling |
| `@types/react` | `^18` | `19.3.0` | Stable npm latest |
| `@types/react-dom` | `^18` | `19.3.0` | Stable npm latest |
| `@types/react-syntax-highlighter` | `^15.5.13` | `15.5.13` | Moved to development dependencies |
| `@types/uuid` | `^10.0.0` | `removed` | Removed: unused or replaced tooling |
| `@typescript-eslint/eslint-plugin` | `^8.12.2` | `removed` | Removed: unused or replaced tooling |
| `@typescript-eslint/parser` | `^8.8.1` | `removed` | Removed: unused or replaced tooling |
| `@uiw/react-codemirror` | `^4.23.5` | `4.25.12` | Stable npm latest |
| `@uiw/react-md-editor` | `^4.0.4` | `removed` | Removed: unused or replaced tooling |
| `@vercel/kv` | `^2.0.0` | `removed` | Removed: unused or replaced tooling |
| `ansi-styles` | `^6.2.3` | `removed` | Removed: unused or replaced tooling |
| `class-variance-authority` | `^0.7.0` | `0.7.1` | Stable npm latest |
| `clsx` | `^2.1.1` | `2.1.1` | Stable npm latest |
| `cmdk` | `1.0.0` | `1.1.1` | Stable npm latest |
| `codemirror` | `—` | `6.0.2` | Added: workspace feature, explicit peer, or current tooling |
| `date-fns` | `^4.1.0` | `4.4.0` | Stable npm latest |
| `diff-match-patch` | `^1.0.5` | `1.0.5` | Stable npm latest |
| `dotenv` | `^16.4.5` | `removed` | Removed: unused or replaced tooling |
| `eslint` | `^8` | `removed` | Removed: unused or replaced tooling |
| `eslint-config-next` | `14.2.10` | `removed` | Removed: unused or replaced tooling |
| `eslint-plugin-unused-imports` | `^4.1.4` | `removed` | Removed: unused or replaced tooling |
| `fake-indexeddb` | `—` | `6.2.6` | Added: real IndexedDB transaction tests |
| `framer-motion` | `^11.11.9` | `14.6.0` | Stable npm latest |
| `groq-sdk` | `^0.13.0` | `removed` | Removed: unused or replaced tooling |
| `js-cookie` | `^3.0.5` | `3.0.8` | Stable npm latest |
| `katex` | `—` | `0.19.1` | Added: workspace feature, explicit peer, or current tooling |
| `langsmith` | `^0.3.60` | `removed` | Removed: unused or replaced tooling |
| `lodash` | `^4.17.21` | `4.18.1` | Stable npm latest |
| `lucide-react` | `^0.474.0` | `1.61.0` | Stable npm latest |
| `next` | `14.2.25` | `16.4.3` | Stable npm latest |
| `nuqs` | `^2.4.1` | `2.10.2` | Stable npm latest |
| `oxlint` | `—` | `1.89.0` | Added: workspace feature, explicit peer, or current tooling |
| `patch-package` | `^8.0.1` | `removed` | Removed: unused or replaced tooling |
| `pdf-parse` | `^1.1.1` | `removed` | Removed: unused or replaced tooling |
| `postcss` | `^8` | `8.5.31` | Stable npm latest |
| `postinstall-postinstall` | `^2.1.0` | `removed` | Removed: unused or replaced tooling |
| `prettier` | `^3.3.3` | `3.9.10` | Stable npm latest |
| `react` | `^18` | `19.3.1` | Stable npm latest |
| `react-colorful` | `^5.6.1` | `5.8.1` | Stable npm latest |
| `react-dom` | `^18` | `19.3.1` | Stable npm latest |
| `react-icons` | `^5.3.0` | `5.7.0` | Stable npm latest |
| `react-json-view` | `^1.21.3` | `removed` | Removed: unused or replaced tooling |
| `react-markdown` | `^9.0.1` | `10.1.0` | Stable npm latest |
| `react-resizable-panels` | `^2.1.7` | `4.15.0` | Stable npm latest |
| `react-syntax-highlighter` | `^15.5.0` | `16.1.2` | Stable npm latest |
| `rehype-katex` | `^7.0.1` | `7.0.1` | Stable npm latest |
| `remark-gfm` | `^4.0.0` | `4.0.1` | Stable npm latest |
| `remark-math` | `^6.0.0` | `6.0.0` | Stable npm latest |
| `remark-parse` | `—` | `11.0.0` | Added: workspace feature, explicit peer, or current tooling |
| `tailwind-merge` | `^2.5.2` | `3.7.0` | Stable npm latest |
| `tailwind-scrollbar` | `^3.1.0` | `4.0.2` | Stable npm latest |
| `tailwind-scrollbar-hide` | `^1.1.7` | `4.0.0` | Stable npm latest |
| `tailwindcss` | `^3.4.1` | `4.3.3` | Stable npm latest |
| `tailwindcss-animate` | `^1.0.7` | `1.0.7` | Stable npm latest |
| `tsx` | `^4.19.1` | `removed` | Removed: unused or replaced tooling |
| `turbo` | `latest` | `removed` | Removed: unused or replaced tooling |
| `typescript` | `^5` | `7.0.2` | Stable npm latest |
| `typescript-eslint` | `^8.8.1` | `removed` | Removed: unused or replaced tooling |
| `unified` | `—` | `11.0.5` | Added: workspace feature, explicit peer, or current tooling |
| `unist-util-visit` | `—` | `5.2.0` | Added: workspace feature, explicit peer, or current tooling |
| `uuid` | `^10.0.0` | `14.0.3` | Stable npm latest |
| `vite` | `—` | `8.3.5` | Added: workspace feature, explicit peer, or current tooling |
| `vitest` | `^3.0.4` | `5.0.5` | Stable npm latest |
| `zod` | `^3.23.8` | `removed` | Removed: unused or replaced tooling |
| `zustand` | `^5.0.3` | `5.0.16` | Stable npm latest |

## Verification

- Baseline: the checkout had no `node_modules`, no test/typecheck scripts, and an obsolete `next lint` command. No pre-existing successful frontend build was assumed.
- Initial fresh install and compiler run exposed removed assistant-ui/panel APIs and pre-existing context/navigation typing problems; those diagnostics drove the compatibility changes.
- `yarn install --non-interactive` and `yarn install --frozen-lockfile --non-interactive`: passed. Required peer packages were added explicitly; the completed installations produced no peer warnings. All 84 direct package versions match both the installed manifests and the npm stable-latest snapshot.
- Retained-file Oxlint check: passed with 17 existing effect-dependency/autofocus warnings. These remain visible; no lint error was ignored.
- Initial production bundle: Webpack compilation passed in 36.3 seconds; its subsequent full TypeScript check identified in-progress workspace hook errors, which were reported to that task owner.
- Validation environment: Node.js 22.19.0, Yarn 1.22.22, Linux x64.
- `src/lib/editor-compatibility.test.ts`: passes a real installed ProseMirror transaction through insertion and changed-range tracking, guarding the runtime failure reproduced with the former lockfile.
- Final `yarn test`: **39 tests across 7 files passed**, including the writing workspace and installed editor compatibility.
- Final `yarn build`: passed end to end in 56 seconds, including TypeScript, all 15 generated pages, and `/canvas`, after the workspace review fixes.
- Final `yarn lint`: no errors; 17 existing conversation-canvas warnings remain. New workspace modules have no lint warnings.
- The writing workspace's eight browser integration workflows passed with no page errors; see [verification record](./writing-workspace-verification.md).
- Production `/canvas` browser smoke passed at 1440×1000 and 390×844 with mocked API responses: saved user/assistant messages, BlockNote Markdown, composer input, attachment add/remove, and panel drag resizing. Chat width changed from approximately 360 to 479 pixels. No page or console errors were recorded. No paid inference was performed.
- The main workspace task is completing its additional review fixes and final whole-project type/lint checks; the retained frontend files have no outstanding compiler or lint errors.

## Primary sources

- npm registry: `https://registry.npmjs.org/<package>/latest` (each package was queried individually, including scoped package names).
- Next 16 migration: https://nextjs.org/docs/app/guides/upgrading/version-16
- Next lint configuration and direct plugin support: https://nextjs.org/docs/app/api-reference/config/eslint
- Next TypeScript CLI configuration: https://nextjs.org/docs/app/api-reference/config/next-config-js/useTypeScriptCli
- Next TypeScript compiler source and shipped declarations: `next@16.4.3`, `dist/lib/verify-typescript-setup.js`, `dist/lib/typescript/runTypeScriptCli.js`, and `dist/server/config-shared.d.ts` from its npm tarball.
- TypeScript compiler and typescript-eslint peer requirements: `typescript@7.0.2` and `@typescript-eslint/parser@8.72.0` npm metadata.
- Tailwind migration: https://github.com/tailwindlabs/tailwindcss.com/blob/main/src/docs/upgrade-guide.mdx
- assistant-ui migration: https://github.com/assistant-ui/assistant-ui/blob/main/apps/docs/content/docs/migrations/v0-15.mdx
- assistant-ui message-part migration: https://github.com/assistant-ui/assistant-ui/blob/main/apps/docs/content/docs/migrations/v0-11.mdx
- Resizable panels API and size units: https://github.com/bvaughn/react-resizable-panels/blob/main/README.md
- Oxlint release metadata and supported rules: `oxlint@1.89.0` npm package, its bundled configuration schema, and `oxlint --help`.

Documentation was read directly from official framework sites, maintainer repositories, and published package tarballs. The available Firecrawl credential rejected authentication, so direct reads were used.
