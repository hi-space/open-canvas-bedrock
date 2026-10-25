import createDOMPurify from "dompurify";
import {
  parse,
  serialize,
  type DefaultTreeAdapterTypes,
  type ParserError,
} from "parse5";
import type { TextSelection } from "./types";
import { SVG_NAMESPACE, svgAttributeAllowed, svgChildAllowed } from "./svg";

type HtmlNode = DefaultTreeAdapterTypes.Node;
type HtmlElement = DefaultTreeAdapterTypes.Element;
type HtmlSourceNode = HtmlElement | DefaultTreeAdapterTypes.TextNode;

const NODE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/;
const HTML_NAMESPACE = "http://www.w3.org/1999/xhtml";
const VOID_TAGS = new Set(["br", "col", "hr", "img", "wbr"]);
// Keep this static subset aligned with workspaces/html_documents.py.
const REGION_TAGS = new Set([
  ...VOID_TAGS,
  "a",
  "abbr",
  "address",
  "article",
  "aside",
  "b",
  "bdi",
  "bdo",
  "blockquote",
  "caption",
  "cite",
  "code",
  "colgroup",
  "dd",
  "del",
  "details",
  "dfn",
  "div",
  "dl",
  "dt",
  "em",
  "figcaption",
  "figure",
  "footer",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "header",
  "hgroup",
  "i",
  "ins",
  "kbd",
  "li",
  "main",
  "mark",
  "nav",
  "ol",
  "p",
  "pre",
  "q",
  "rp",
  "rt",
  "ruby",
  "s",
  "samp",
  "section",
  "small",
  "span",
  "strong",
  "sub",
  "summary",
  "sup",
  "table",
  "tbody",
  "td",
  "tfoot",
  "th",
  "thead",
  "time",
  "tr",
  "u",
  "ul",
  "var",
  "svg",
]);
const NON_REGION_TAGS = new Set([
  "html",
  "head",
  "body",
  "base",
  "meta",
  "title",
  "link",
  "style",
  "script",
  "template",
  "noscript",
  "iframe",
  "frame",
  "frameset",
  "object",
  "embed",
  "applet",
  "math",
  "form",
  "input",
  "button",
  "textarea",
  "select",
  "option",
  "optgroup",
  "fieldset",
  "datalist",
  "output",
  "label",
  "keygen",
  "audio",
  "video",
  "source",
  "track",
  "portal",
]);
const REMOVED_PREVIEW_TAGS = new Set(
  [...NON_REGION_TAGS].filter(
    (tag) => !["html", "head", "body", "style", "title"].includes(tag)
  )
);
const REMOVED_PREVIEW_ATTRIBUTES = new Set([
  "href",
  "xlink:href",
  "action",
  "formaction",
  "form",
  "target",
  "download",
  "ping",
  "srcset",
  "imagesrcset",
  "srcdoc",
  "background",
  "poster",
  "manifest",
  "profile",
  "codebase",
  "archive",
  "longdesc",
  "nonce",
  "autofocus",
  "autoplay",
  "contenteditable",
  "tabindex",
  "accesskey",
  "popover",
  "popovertarget",
  "is",
]);
const EMBEDDED_IMAGE =
  /^data:image\/(?:png|jpeg|gif|webp|avif|bmp);base64,[A-Za-z0-9+/=\s]+$/i;

export interface HtmlRegion extends TextSelection {
  nodeId: string;
  label: string;
  previewText: string;
  sourceIds: string[];
  parentId?: string;
}

function isElement(node: HtmlNode): node is HtmlElement {
  return "tagName" in node;
}

function attribute(node: HtmlElement, name: string): string | undefined {
  return node.attrs.find((item) => item.name === name)?.value;
}

function elements(root: HtmlNode): HtmlElement[] {
  const result: HtmlElement[] = [];
  const pending: HtmlNode[] = [root];
  while (pending.length) {
    const node = pending.pop()!;
    if (isElement(node)) result.push(node);
    if ("childNodes" in node) pending.push(...node.childNodes.toReversed());
    if ("content" in node)
      pending.push((node as DefaultTreeAdapterTypes.Template).content);
  }
  return result;
}

function isDescendant(node: HtmlSourceNode, ancestor: HtmlSourceNode): boolean {
  let parent = node.parentNode;
  while (parent) {
    if (parent === ancestor) return true;
    parent = "parentNode" in parent ? parent.parentNode : null;
  }
  return false;
}

function isBodyRegion(node: HtmlElement): boolean {
  let current: HtmlNode | null = node;
  while (current && isElement(current)) {
    if (current !== node && current.tagName === "body") return true;
    if (
      (current.namespaceURI !== HTML_NAMESPACE &&
        !(
          current === node &&
          current.namespaceURI === SVG_NAMESPACE &&
          current.tagName === "svg"
        )) ||
      !REGION_TAGS.has(current.tagName)
    )
      return false;
    current = current.parentNode;
  }
  return false;
}

function ambiguousRanges(nodes: HtmlElement[]): Set<HtmlNode> {
  const ambiguous = new Set<HtmlNode>();
  const stack: HtmlSourceNode[] = [];
  const located = [
    ...nodes,
    ...nodes.flatMap((node) =>
      node.childNodes.filter(
        (child): child is DefaultTreeAdapterTypes.TextNode => "value" in child
      )
    ),
  ]
    .filter(
      (node) =>
        node.sourceCodeLocation &&
        (!isElement(node) || node.sourceCodeLocation.startTag)
    )
    .sort(
      (left, right) =>
        left.sourceCodeLocation!.startOffset -
        right.sourceCodeLocation!.startOffset
    );
  for (const node of located) {
    const location = node.sourceCodeLocation!;
    while (
      stack.length &&
      stack.at(-1)!.sourceCodeLocation!.endOffset <= location.startOffset
    )
      stack.pop();
    while (
      stack.length &&
      stack.at(-1)!.sourceCodeLocation!.endOffset < location.endOffset
    ) {
      ambiguous.add(stack.pop()!);
      ambiguous.add(node);
    }
    // Foster parenting can move rendered content outside its source container.
    for (let index = stack.length - 1; index >= 0; index--) {
      if (isDescendant(node, stack[index])) break;
      ambiguous.add(stack[index]);
      // Merged foster-parented text may span a source element's whole range.
      if (!isElement(stack[index])) ambiguous.add(node);
    }
    stack.push(node);
  }
  return ambiguous;
}

function previewText(node: HtmlElement): string {
  const parts: string[] = [];
  const pending: HtmlNode[] = [node];
  let length = 0;
  while (pending.length && length < 500) {
    const child = pending.pop()!;
    if ("value" in child) {
      parts.push(child.value);
      length += child.value.length;
    } else if (isElement(child) && !NON_REGION_TAGS.has(child.tagName)) {
      const alt = attribute(child, "alt");
      if (alt) parts.push(alt);
      pending.push(...child.childNodes.toReversed());
    }
  }
  return Array.from(parts.join(" ").replace(/\s+/g, " ").trim())
    .slice(0, 180)
    .join("");
}

function sourceIds(node: HtmlElement): string[] {
  const value = attribute(node, "data-source-ids");
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (
      !Array.isArray(parsed) ||
      !parsed.every(
        (item) => typeof item === "string" && item.trim().length > 0
      )
    )
      return [];
    return [...new Set(parsed as string[])];
  } catch {
    return [];
  }
}

export function htmlRegions(content: string): HtmlRegion[] {
  const errors: ParserError[] = [];
  const document = parse(content, {
    sourceCodeLocationInfo: true,
    onParseError: (error) => errors.push(error),
  });
  const nodes = elements(document);
  const counts = new Map<string, number>();
  for (const node of nodes) {
    const id = attribute(node, "data-oc-id");
    if (id) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  const ambiguous = ambiguousRanges(nodes);
  const mapped = new Map<HtmlElement, HtmlRegion>();
  for (const node of nodes) {
    const nodeId = attribute(node, "data-oc-id");
    const location = node.sourceCodeLocation;
    if (
      !nodeId ||
      !NODE_ID.test(nodeId) ||
      counts.get(nodeId) !== 1 ||
      !isBodyRegion(node) ||
      ambiguous.has(node) ||
      !location?.startTag ||
      !location.attrs?.["data-oc-id"] ||
      (!VOID_TAGS.has(node.tagName) &&
        !location.endTag &&
        !(
          node.tagName === "svg" &&
          node.namespaceURI === SVG_NAMESPACE &&
          /\/>\s*$/.test(
            content.slice(location.startOffset, location.endOffset)
          )
        )) ||
      errors.some(
        (error) =>
          error.code === "duplicate-attribute" &&
          error.startOffset >= location.startTag!.startOffset &&
          error.startOffset < location.startTag!.endOffset
      )
    )
      continue;
    const text = previewText(node);
    const description =
      attribute(node, "aria-label") || attribute(node, "title") || text;
    const tagLabel = node.tagName === "svg" ? "SVG 도식" : node.tagName;
    const label = description
      ? `${tagLabel} · ${Array.from(description).slice(0, 64).join("")}`
      : tagLabel;
    mapped.set(node, {
      nodeId,
      from: location.startOffset,
      to: location.endOffset,
      text: content.slice(location.startOffset, location.endOffset),
      label,
      previewText: text,
      sourceIds: sourceIds(node),
    });
  }
  for (const [node, region] of mapped) {
    let parent = node.parentNode;
    while (parent && isElement(parent)) {
      const parentRegion = mapped.get(parent);
      if (parentRegion) {
        region.parentId = parentRegion.nodeId;
        break;
      }
      parent = parent.parentNode;
    }
  }
  return [...mapped.values()].sort((left, right) => left.from - right.from);
}

export function selectionForHtmlMessage(
  data: unknown,
  token: string,
  content: string
): TextSelection | undefined {
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  const message = data as Record<string, unknown>;
  if (
    message.type !== "oc-html-select" ||
    message.token !== token ||
    typeof message.nodeId !== "string"
  )
    return;
  const region = htmlRegions(content).find(
    (item) => item.nodeId === message.nodeId
  );
  if (!region) return;
  const { from, to, text, nodeId, label, previewText, sourceIds } = region;
  return { from, to, text, nodeId, label, previewText, sourceIds };
}

function bridgeScript(token: string, ids: string[]): string {
  const literal = (value: string | string[]) =>
    JSON.stringify(value)
      .replace(/</g, "\\u003c")
      .replace(/\u2028/g, "\\u2028")
      .replace(/\u2029/g, "\\u2029");
  return `((token, ids) => {
    "use strict";
    const allowed = new Set(ids);
    const nodes = new Map();
    for (const node of document.querySelectorAll("[data-oc-id]")) {
      const id = node.getAttribute("data-oc-id");
      if (allowed.has(id)) nodes.set(id, node);
    }
    let selected = null;
    let hovered = null;
    const originals = new Map();
    const properties = ["outline", "outline-offset", "box-shadow", "transition"];
    function mark(node, active) {
      originals.set(node, properties.map(name => [
        name, node.style.getPropertyValue(name), node.style.getPropertyPriority(name)
      ]));
      node.style.setProperty("outline",
        active ? "3px solid #2f6e4b" : "2px dashed #668b55", "important");
      node.style.setProperty("outline-offset", "-3px", "important");
      node.style.setProperty("box-shadow",
        active ? "inset 0 0 0 4px rgba(47,110,75,.16)" : "none", "important");
      node.style.setProperty("transition", "none", "important");
      node.setAttribute(active ? "data-oc-preview-selected" : "data-oc-preview-hover", "");
    }
    function paint() {
      for (const [node, values] of originals) {
        for (const [name, value, priority] of values) {
          if (value) node.style.setProperty(name, value, priority);
          else node.style.removeProperty(name);
        }
        node.removeAttribute("data-oc-preview-selected");
        node.removeAttribute("data-oc-preview-hover");
      }
      originals.clear();
      if (hovered && hovered !== selected) mark(hovered, false);
      if (selected) mark(selected, true);
    }
    function closest(target) {
      let node = target instanceof Element ? target : null;
      while (node) {
        const id = node.getAttribute("data-oc-id");
        if (nodes.get(id) === node) return node;
        node = node.parentElement;
      }
      return null;
    }
    document.addEventListener("pointerover", event => {
      const next = closest(event.target);
      if (next !== hovered) { hovered = next; paint(); }
    }, true);
    document.addEventListener("pointerout", event => {
      if (!event.relatedTarget && hovered) { hovered = null; paint(); }
    }, true);
    document.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      const node = closest(event.target);
      if (node) parent.postMessage({
        type: "oc-html-select", token, nodeId: node.getAttribute("data-oc-id")
      }, "*");
    }, true);
    for (const type of ["auxclick", "submit", "dragstart"]) {
      document.addEventListener(type, event => event.preventDefault(), true);
    }
    window.addEventListener("message", event => {
      const data = event.data;
      if (event.source !== parent || !data || typeof data !== "object" ||
          data.type !== "oc-html-highlight" || data.token !== token ||
          (data.nodeId !== null && !nodes.has(data.nodeId))) return;
      selected = data.nodeId === null ? null : nodes.get(data.nodeId);
      hovered = null;
      paint();
      if (selected && typeof selected.scrollIntoView === "function") {
        selected.scrollIntoView({block: "nearest", inline: "nearest"});
      }
    });
  })(${literal(token)}, ${literal(ids)});`;
}

export function createHtmlPreview(
  content: string,
  token: string,
  interactive: boolean
): string {
  const purifier = createDOMPurify(window);
  if (!purifier.isSupported)
    throw new Error("이 브라우저에서는 HTML 미리보기를 사용할 수 없어요.");

  const allowedIds = new Set(
    htmlRegions(content).map((region) => region.nodeId)
  );
  const earlyStyles: string[] = [];
  // Strip active/resource-bearing markup before a browser parser sees it.
  const tree = parse(content);
  for (const node of elements(tree)) {
    node.childNodes = node.childNodes.filter(
      (child) =>
        !isElement(child) ||
        (child.namespaceURI === HTML_NAMESPACE &&
          node.namespaceURI !== SVG_NAMESPACE &&
          !REMOVED_PREVIEW_TAGS.has(child.tagName)) ||
        (child.namespaceURI === SVG_NAMESPACE &&
          (node.namespaceURI === HTML_NAMESPACE
            ? child.tagName === "svg"
            : svgChildAllowed(child.tagName, node.tagName)))
    );
    node.attrs = node.attrs.filter(({ name, value, namespace, prefix }) => {
      if (
        node.namespaceURI === SVG_NAMESPACE &&
        (!svgAttributeAllowed(node.tagName, name, value) ||
          (namespace && (name !== "xmlns" || prefix)))
      )
        return false;
      if (
        name === "style" &&
        (node.tagName === "html" || node.tagName === "head")
      ) {
        // These attributes would be parsed before the first head CSP.
        const selector = node.tagName === "html" ? "html:root" : "head";
        earlyStyles.push(`${selector} { ${value.replace(/</g, "\\3c ")} }`);
        return false;
      }
      if (name.startsWith("on") || REMOVED_PREVIEW_ATTRIBUTES.has(name))
        return false;
      if (name === "src")
        return node.tagName === "img" && EMBEDDED_IMAGE.test(value);
      if (name === "data-oc-id") return allowedIds.has(value);
      return !name.startsWith("data-oc-");
    });
  }

  const clean = purifier.sanitize(serialize(tree), {
    WHOLE_DOCUMENT: true,
    RETURN_DOM: true,
    USE_PROFILES: { html: true, svg: true },
    FORBID_TAGS: [...REMOVED_PREVIEW_TAGS],
    FORBID_ATTR: [...REMOVED_PREVIEW_ATTRIBUTES],
    ADD_TAGS: ["style", "title"],
  }) as HTMLElement;
  const head = clean.querySelector("head");
  const body = clean.querySelector("body");
  if (!head || !body) throw new Error("HTML 미리보기를 준비하지 못했어요.");
  // Add only safe scroll targets back; arbitrary authored tab stops stay removed.
  for (const diagram of body.querySelectorAll("svg")) {
    const wrapper = diagram.parentElement;
    if (
      wrapper?.localName === "div" &&
      [wrapper.style.overflowX, wrapper.style.overflow].some((value) =>
        ["auto", "scroll"].includes(value)
      )
    )
      wrapper.setAttribute("tabindex", "0");
  }

  const nonce = [...window.crypto.getRandomValues(new Uint8Array(18))]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  const policy = clean.ownerDocument.createElement("meta");
  policy.setAttribute("http-equiv", "Content-Security-Policy");
  policy.setAttribute(
    "content",
    [
      "default-src 'none'",
      `script-src ${interactive ? `'nonce-${nonce}'` : "'none'"}`,
      "script-src-attr 'none'",
      "style-src 'unsafe-inline'",
      "img-src data:",
      "connect-src 'none'",
      "font-src 'none'",
      "media-src 'none'",
      "object-src 'none'",
      "frame-src 'none'",
      "child-src 'none'",
      "worker-src 'none'",
      "manifest-src 'none'",
      "base-uri 'none'",
      "form-action 'none'",
    ].join("; ")
  );
  head.prepend(policy);
  const viewport = clean.ownerDocument.createElement("meta");
  viewport.name = "viewport";
  viewport.content = "width=device-width, initial-scale=1";
  policy.after(viewport);
  if (earlyStyles.length) {
    const style = clean.ownerDocument.createElement("style");
    style.textContent = earlyStyles.join("\n");
    head.append(style);
  }

  if (interactive) {
    const script = clean.ownerDocument.createElement("script");
    script.setAttribute("nonce", nonce);
    script.textContent = bridgeScript(token, [...allowedIds]);
    body.append(script);
  }
  return `<!doctype html>${clean.outerHTML}`;
}
