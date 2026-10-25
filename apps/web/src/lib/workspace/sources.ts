import type { SourceReference } from "./types";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";
import { parseFragment, type DefaultTreeAdapterMap } from "parse5";

export interface DocumentReference extends SourceReference {
  label: string;
  count: number;
}

export function referenceUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (
      !["https:", "http:"].includes(url.protocol) ||
      url.username ||
      url.password
    ) {
      return null;
    }
    return url.href;
  } catch {
    return null;
  }
}

export function extractReferences(markdown: string): DocumentReference[] {
  const tree = unified().use(remarkParse).use(remarkGfm).parse(markdown);
  const definitions = new Map<string, { url: string; title?: string | null }>();
  const references = new Map<string, DocumentReference>();
  visit(tree, "definition", (node) => {
    definitions.set(node.identifier.toLowerCase(), node);
  });
  const add = (inputUrl: string, label: string, title?: string | null) => {
    const url = referenceUrl(inputUrl);
    if (!url) return;
    const existing = references.get(url);
    if (existing) {
      existing.count++;
      return;
    }
    references.set(url, {
      id: referenceId(url),
      url,
      title:
        title ||
        (/^\d+$/.test(label) ? new URL(url).hostname : label) ||
        new URL(url).hostname,
      label,
      count: 1,
    });
  };
  visit(tree, (node) => {
    if (node.type === "link") {
      add(node.url, plainText(node), node.title);
    } else if (node.type === "linkReference") {
      const definition = definitions.get(node.identifier.toLowerCase());
      if (definition) add(definition.url, plainText(node), definition.title);
    } else if (node.type === "html") {
      const walkHtml = (element: DefaultTreeAdapterMap["node"]) => {
        if ("tagName" in element) {
          if (["script", "style", "template"].includes(element.tagName)) return;
          if (element.tagName === "a") {
            const href = element.attrs.find(
              (attr) => attr.name === "href"
            )?.value;
            const title = element.attrs.find(
              (attr) => attr.name === "title"
            )?.value;
            if (href) add(href, htmlText(element).trim(), title);
          }
        }
        if ("childNodes" in element) element.childNodes.forEach(walkHtml);
      };
      walkHtml(parseFragment(node.value));
    }
  });
  return [...references.values()];
}

function htmlText(node: DefaultTreeAdapterMap["node"]): string {
  if (node.nodeName === "#text" && "value" in node) return node.value;
  return "childNodes" in node ? node.childNodes.map(htmlText).join("") : "";
}

export function insertCitation(
  content: string,
  source: SourceReference,
  position: number
): string {
  const url = referenceUrl(source.url);
  if (!url)
    throw new Error("http 또는 https로 시작하는 출처 링크를 입력해 주세요.");
  if (
    !Number.isInteger(position) ||
    position < 0 ||
    position > content.length
  ) {
    throw new Error("인용을 넣을 문장을 다시 선택해 주세요.");
  }
  const references = extractReferences(content);
  const existing = references.find((reference) => reference.url === url);
  const numbers = references
    .filter((reference) => /^\d+$/.test(reference.label))
    .map((reference) => Number(reference.label));
  const number =
    existing && /^\d+$/.test(existing.label)
      ? existing.label
      : String(Math.max(0, ...numbers) + 1);
  const title = source.title
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/[\r\n]/g, " ");
  const citation = ` [${number}](<${url}> "${title}")`;
  return content.slice(0, position) + citation + content.slice(position);
}

function plainText(node: unknown): string {
  if (!node || typeof node !== "object") return "";
  if ("value" in node && typeof node.value === "string") return node.value;
  if ("children" in node && Array.isArray(node.children))
    return node.children.map(plainText).join("");
  return "";
}

function referenceId(url: string): string {
  let hash = BigInt("14695981039346656037");
  for (let index = 0; index < url.length; index++) {
    hash = BigInt.asUintN(
      64,
      (hash ^ BigInt(url.charCodeAt(index))) * BigInt("1099511628211")
    );
  }
  return `link:${hash.toString(16)}`;
}

export function mergeReferences(
  content: string,
  sources: SourceReference[]
): SourceReference[] {
  const merged = new Map<string, SourceReference>(
    extractReferences(content).map((source) => [source.url, source])
  );
  for (const source of sources) {
    const url = referenceUrl(source.url);
    if (url) merged.set(url, { ...merged.get(url), ...source, url });
  }
  return [...merged.values()];
}

export function validateProposalReferences(
  before: string,
  after: string,
  sources: SourceReference[]
): void {
  const original = extractReferences(before);
  const proposed = extractReferences(after);
  const allowed = new Set([
    ...original.map((source) => source.url),
    ...sources
      .filter((source) => source.excerpt?.trim())
      .map((source) => referenceUrl(source.url)),
  ]);
  if (proposed.some((source) => !allowed.has(source.url))) {
    throw new Error(
      "수정안에 근거가 제공되지 않은 출처가 포함되어 있습니다. 출처와 발췌를 추가한 뒤 다시 요청해 주세요."
    );
  }
  if (
    original.some(
      (source) =>
        (proposed.find((item) => item.url === source.url)?.count ?? 0) <
        source.count
    )
  ) {
    throw new Error(
      "수정안에서 기존 출처가 사라졌습니다. 인용을 유지하도록 다시 요청해 주세요."
    );
  }
  const tree = unified().use(remarkParse).use(remarkGfm).parse(after);
  visit(tree, (node) => {
    if (
      (node.type === "link" || node.type === "definition") &&
      /^[a-z][a-z\d+.-]*:/i.test(node.url) &&
      !referenceUrl(node.url)
    ) {
      throw new Error("수정안에 안전하지 않은 출처 링크가 포함되어 있습니다.");
    }
    if (node.type === "html" && !before.includes(node.value)) {
      throw new Error(
        "수정안에 새 HTML이 포함되어 있습니다. Markdown 형식과 출처 링크로 다시 요청해 주세요."
      );
    }
  });
}
