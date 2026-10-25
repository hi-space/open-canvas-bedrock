"""The static SVG subset supported by HTML documents and the browser preview."""

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SVG_TAGS = frozenset({
    "svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "path", "text", "tspan", "title", "desc",
})
SVG_TEXT = frozenset({"text", "tspan", "title", "desc"})
SVG_ATTRIBUTES = frozenset({
    "id", "class", "style", "role", "tabindex", "focusable", "lang",
    "viewbox", "width", "height", "preserveaspectratio",
    "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry",
    "d", "points", "dx", "dy", "transform",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
    "stroke-opacity", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
    "stroke-dashoffset", "opacity", "vector-effect",
    "font-family", "font-size", "font-weight", "font-style", "text-anchor",
    "dominant-baseline", "alignment-baseline", "letter-spacing", "textlength",
    "lengthadjust",
})


def svg_attribute_allowed(tag: str, name: str, value: str | None) -> bool:
    if name == "xmlns":
        return tag == "svg" and value == SVG_NAMESPACE
    return ":" not in name and (
        name in SVG_ATTRIBUTES or name.startswith(("data-", "aria-"))
    )


def svg_child_allowed(tag: str, parent: str | None) -> bool:
    if tag not in SVG_TAGS or tag == "svg":
        return False
    if parent in {"svg", "g"}:
        return tag != "tspan"
    if parent in {"text", "tspan"}:
        return tag == "tspan"
    if parent in SVG_TAGS - SVG_TEXT:
        return tag in {"title", "desc"}
    return False
