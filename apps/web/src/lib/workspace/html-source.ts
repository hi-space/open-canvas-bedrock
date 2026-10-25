import { parse, type DefaultTreeAdapterMap } from "parse5";
import { referenceUrl } from "./sources";
import type { SourceReference } from "./types";

type Element = DefaultTreeAdapterMap["element"];

const citationContainers = new Set([
  "body",
  "main",
  "section",
  "article",
  "div",
  "aside",
  "header",
  "footer",
  "nav",
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "li",
  "td",
  "th",
  "blockquote",
  "figcaption",
  "figure",
  "address",
  "details",
  "summary",
]);
const phrasingContainers = new Set([
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "summary",
]);

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character]!
  );
}

/** Add a visible citation and retain the selected region's source identity. */
export function insertHtmlCitation(
  content: string,
  source: SourceReference,
  nodeId?: string,
  provenanceId: string | null = source.id
): string {
  const url = referenceUrl(source.url);
  if (!url)
    throw new Error("http 또는 https로 시작하는 출처 링크를 입력해 주세요.");
  const tree = parse(content, { sourceCodeLocationInfo: true });
  const elements: Element[] = [];
  const walk = (node: DefaultTreeAdapterMap["node"]) => {
    if ("tagName" in node) elements.push(node);
    if ("childNodes" in node) node.childNodes.forEach(walk);
  };
  walk(tree);
  const matches = elements.filter((element) =>
    element.attrs.some(
      (attr) => attr.name === "data-oc-id" && attr.value === nodeId
    )
  );
  const selected = nodeId ? matches[0] : undefined;
  if (
    nodeId &&
    (matches.length !== 1 || !selected?.sourceCodeLocation?.startTag)
  )
    throw new Error("인용을 넣을 영역을 다시 선택해 주세요.");
  const link = `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>`;
  const edits: { from: number; to: number; text: string }[] = [];
  if (selected && provenanceId) {
    const location = selected.sourceCodeLocation!;
    const current = selected.attrs.find(
      (attr) => attr.name === "data-source-ids"
    );
    let ids: string[] = [];
    if (current) {
      try {
        const parsed: unknown = JSON.parse(current.value);
        if (Array.isArray(parsed))
          ids = parsed.filter((id): id is string => typeof id === "string");
      } catch {
        throw new Error("영역의 출처 정보를 확인한 뒤 다시 선택해 주세요.");
      }
    }
    const attribute = `data-source-ids="${escapeHtml(JSON.stringify([...new Set([...ids, provenanceId])]))}"`;
    const existing = location.attrs?.["data-source-ids"];
    const end = location.startTag!.endOffset;
    const lastAttributeEnd = Math.max(
      0,
      ...Object.values(location.attrs ?? {}).map(
        (attribute) => attribute.endOffset
      )
    );
    const selfClosing = content[end - 2] === "/" && lastAttributeEnd <= end - 2;
    const insert = selfClosing ? end - 2 : end - 1;
    edits.push(
      existing
        ? {
            from: existing.startOffset,
            to: existing.endOffset,
            text: attribute,
          }
        : { from: insert, to: insert, text: ` ${attribute}` }
    );
  }

  let enclosingLink: Element | undefined;
  let ancestor: DefaultTreeAdapterMap["node"] | null = selected ?? null;
  while (ancestor && "tagName" in ancestor) {
    if (ancestor.tagName === "a") enclosingLink = ancestor;
    ancestor = ancestor.parentNode;
  }
  if (
    selected &&
    !enclosingLink &&
    citationContainers.has(selected.tagName) &&
    selected.sourceCodeLocation?.endTag
  ) {
    const offset = selected.sourceCodeLocation.endTag.startOffset;
    edits.push({ from: offset, to: offset, text: ` ${link}` });
  } else if (selected) {
    // A citation cannot be a direct child of table/list structures. Place it
    // after the enclosing structure, while provenance stays on the selection.
    let anchor = enclosingLink ?? selected;
    while (
      anchor.parentNode &&
      "tagName" in anchor.parentNode &&
      !citationContainers.has(anchor.parentNode.tagName)
    ) {
      anchor = anchor.parentNode;
    }
    const offset = anchor.sourceCodeLocation?.endOffset;
    if (offset === undefined)
      throw new Error("인용을 넣을 문단을 다시 선택해 주세요.");
    const parent = anchor.parentNode;
    const inline =
      parent && "tagName" in parent && phrasingContainers.has(parent.tagName);
    edits.push({
      from: offset,
      to: offset,
      text: inline ? ` ${link}` : `<p>${link}</p>`,
    });
  } else {
    const body = elements.find((element) => element.tagName === "body");
    const offset =
      body?.sourceCodeLocation?.endTag?.startOffset ?? content.length;
    edits.push({ from: offset, to: offset, text: `<p>${link}</p>` });
  }
  return edits
    .sort((a, b) => b.from - a.from)
    .reduce(
      (result, edit) =>
        result.slice(0, edit.from) + edit.text + result.slice(edit.to),
      content
    );
}
