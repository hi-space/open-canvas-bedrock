/** Keep this static subset aligned with api/workspaces/svg.py. */
export const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
export const SVG_TAGS = new Set([
  "svg",
  "g",
  "rect",
  "circle",
  "ellipse",
  "line",
  "polyline",
  "polygon",
  "path",
  "text",
  "tspan",
  "title",
  "desc",
]);

export function svgChildAllowed(tag: string, parent: string): boolean {
  if (!SVG_TAGS.has(tag) || tag === "svg") return false;
  if (parent === "svg" || parent === "g") return tag !== "tspan";
  if (parent === "text" || parent === "tspan") return tag === "tspan";
  return (
    SVG_TAGS.has(parent) &&
    !["title", "desc"].includes(parent) &&
    (tag === "title" || tag === "desc")
  );
}
const SVG_ATTRIBUTES = new Set([
  "id",
  "class",
  "style",
  "role",
  "tabindex",
  "focusable",
  "lang",
  "viewbox",
  "width",
  "height",
  "preserveaspectratio",
  "x",
  "y",
  "x1",
  "x2",
  "y1",
  "y2",
  "cx",
  "cy",
  "r",
  "rx",
  "ry",
  "d",
  "points",
  "dx",
  "dy",
  "transform",
  "fill",
  "fill-opacity",
  "fill-rule",
  "stroke",
  "stroke-width",
  "stroke-opacity",
  "stroke-linecap",
  "stroke-linejoin",
  "stroke-dasharray",
  "stroke-dashoffset",
  "opacity",
  "vector-effect",
  "font-family",
  "font-size",
  "font-weight",
  "font-style",
  "text-anchor",
  "dominant-baseline",
  "alignment-baseline",
  "letter-spacing",
  "textlength",
  "lengthadjust",
]);

function staticCss(value: string): boolean {
  const decoded = value
    .replace(/\\(?:\r\n|[\r\n\f])/g, "")
    .replace(
      /\\([0-9a-f]{1,6})[ \t\r\n\f]?|\\([^\r\n\f])/gi,
      (_match, hex: string | undefined, literal: string) =>
        hex
          ? String.fromCodePoint(Math.min(parseInt(hex, 16), 0x10ffff))
          : literal
    )
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .toLowerCase();
  return !/@\s*(?:import|namespace)\b|(?:expression|url|(?:-webkit-)?image-set)\s*\(|(?:^|[;{])\s*(?:behavior|-moz-binding)\s*:|(?:javascript|vbscript)\s*:/.test(
    decoded
  );
}

export function svgAttributeAllowed(
  tag: string,
  name: string,
  value: string
): boolean {
  name = name.toLowerCase();
  if (name === "xmlns") return tag === "svg" && value === SVG_NAMESPACE;
  if (name.includes(":") || name.startsWith("on")) return false;
  if (
    !SVG_ATTRIBUTES.has(name) &&
    !name.startsWith("data-") &&
    !name.startsWith("aria-")
  )
    return false;
  return (
    !["style", "fill", "stroke", "font-family"].includes(name) ||
    staticCss(value)
  );
}
