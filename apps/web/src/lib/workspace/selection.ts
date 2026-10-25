import type { TextSelection } from "./types";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";

interface SourceNode {
  type: string;
  value?: string;
  children?: SourceNode[];
  position?: { start: { offset?: number }; end: { offset?: number } };
}

export function mapRenderedSelection(
  content: string,
  block: { from: number; to: number; text: string },
  start: number,
  end: number
): TextSelection | undefined {
  if (start < 0 || end <= start || end > block.text.length) return;
  // Markdown parsers omit a leading BOM from their position offsets.
  const sourceOffset = content.startsWith("\uFEFF") ? 1 : 0;
  const tree = unified().use(remarkParse).use(remarkGfm).parse(content);
  let sourceBlock: SourceNode | undefined;
  visit(tree, (node) => {
    if (
      ["paragraph", "heading", "listItem"].includes(node.type) &&
      node.position?.start.offset !== undefined &&
      node.position?.end.offset !== undefined &&
      node.position.start.offset + sourceOffset === block.from &&
      node.position.end.offset + sourceOffset === block.to
    ) {
      sourceBlock = node;
    }
  });
  if (!sourceBlock) return;
  let rendered = "";
  let unsupported = false;
  const spans: {
    start: number;
    end: number;
    source: number;
    literal: boolean;
  }[] = [];
  const walk = (node: SourceNode) => {
    if (node.type === "footnoteReference") {
      unsupported = true;
      return;
    }
    if (["html", "image", "imageReference", "break"].includes(node.type))
      return;
    if (node.type === "text" || node.type === "inlineCode") {
      const value = node.value ?? "";
      const from =
        node.position?.start.offset === undefined
          ? undefined
          : node.position.start.offset + sourceOffset;
      const to =
        node.position?.end.offset === undefined
          ? undefined
          : node.position.end.offset + sourceOffset;
      const raw =
        from === undefined || to === undefined ? "" : content.slice(from, to);
      const inlineOffset = node.type === "inlineCode" ? raw.indexOf(value) : 0;
      const literal =
        node.type === "text"
          ? raw === value
          : inlineOffset >= 0 && raw.indexOf(value, inlineOffset + 1) < 0;
      spans.push({
        start: rendered.length,
        end: rendered.length + value.length,
        source: (from ?? 0) + Math.max(0, inlineOffset),
        literal,
      });
      rendered += value;
      return;
    }
    node.children?.forEach(walk);
  };
  walk(sourceBlock);
  if (unsupported || rendered !== block.text) return;
  const first = spans.find((span) => span.start <= start && start < span.end);
  const last = spans.find((span) => span.start < end && end <= span.end);
  if (!first?.literal || !last?.literal) return;
  const from = first.source + start - first.start;
  const to = last.source + end - last.start;
  const text = block.text.slice(start, end);
  if (content.slice(from, to) !== text) return;
  return { from, to, text };
}
