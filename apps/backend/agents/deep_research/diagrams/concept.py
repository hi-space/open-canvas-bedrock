"""Concept / process figures in the aws-diagram-design house style (awsdiag.Canvas), rasterized by Chrome.

The model chooses content on a grid (rows of nodes, edges between neighbours); this module computes every
coordinate, so arrows always attach to box edges and never cross a box — the rules the skill enforces.
"""
import asyncio
import html
import importlib
import logging
import os
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agents.deep_research.diagrams.assets import find_skill_dir
from agents.deep_research.llm import ainvoke_json

logger = logging.getLogger(__name__)

NodeKind = Literal["step", "focal", "store", "external", "input", "optional", "security"]
KIND_LABELS = {
    "en": {"step": "Step", "focal": "Focus", "store": "Storage", "external": "External",
           "input": "Input / actor", "optional": "Optional", "security": "Security", "dashed": "Optional / async"},
    "ko": {"step": "단계", "focal": "핵심", "store": "저장소", "external": "외부 시스템",
           "input": "입력 / 사용자", "optional": "선택", "security": "보안", "dashed": "선택 / 비동기"},
}


class ConceptNode(BaseModel):
    id: str
    name: str = Field(description="<= 22 characters")
    sub: str | None = Field(default=None, description="optional one-line sublabel, <= 28 characters")
    kind: NodeKind = "step"
    icon: str | None = None


class ConceptEdge(BaseModel):
    source: str
    target: str
    label: str | None = Field(default=None, description="<= 12 characters, uppercase verb")
    dashed: bool = False


class ConceptSpec(BaseModel):
    title: str
    description: str
    rows: list[list[ConceptNode]] = Field(min_length=1, max_length=4)
    edges: list[ConceptEdge] = Field(default_factory=list, max_length=16)


def skill_dir() -> Path | None:
    return find_skill_dir("AWS_DIAGRAM_SKILL_DIR", "aws-diagram-design")


def _chrome() -> str | None:
    return next((p for p in (shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser")) if p), None)


def available() -> bool:
    return skill_dir() is not None and _chrome() is not None


@lru_cache(maxsize=1)
def _awsdiag():
    root = skill_dir()
    os.environ.setdefault("AWS_DIAGRAM_SKILL_DIR", str(root))
    sys.path.insert(0, str(root / "scripts/pygen"))
    try:
        return importlib.import_module("awsdiag")
    finally:
        sys.path.remove(str(root / "scripts/pygen"))


@lru_cache(maxsize=1)
def _icon_names() -> str:
    lib = _awsdiag()
    generic = re.findall(r"^### (\S+)$", lib.GENERIC_MD.read_text(), re.M)
    return f"AWS: {', '.join(sorted(lib.AWS))}\nGeneric: {', '.join(generic)}"


SYSTEM = """You design one explanatory figure for a document: a process, pipeline, lifecycle, layered stack or
comparison flow, drawn as a grid of boxes.

Rules:
- rows: 1-4 rows, each 1-4 nodes (the figure is shown at document width; wider grids become unreadable),
  read left to right, top to bottom. Same column = vertically aligned.
- edges connect only grid neighbours: the next/previous node in the same row, or the node directly
  above/below in the same column. Anything else is dropped, so arrange the grid so the flow works.
- Text is tight: name <= 22 characters, optional sub <= 28 characters, edge label <= 12 characters
  (uppercase verb like "EMBED", "RETRIEVE") or null.
- 1-2 nodes kind "focal" (the point of the figure). "store" for data, "input" for actors, "external" for
  third parties, "optional" for optional steps, "security" for guards.
- icon: optional, only from this list, else null:
{icons}
- Write text in the document language. Keep AWS service names in English."""


def _layout(spec: ConceptSpec, lib, language: str):
    nodes = [n for row in spec.rows for n in row]
    has_sub = any(n.sub for n in nodes)
    h = 64 if has_sub else 48
    w = max(184, *(lib.min_node_w(n.name, n.sub, bool(n.icon), h) for n in nodes))
    w = min(w, 320)
    pos = {n.id: (r, c) for r, row in enumerate(spec.rows) for c, n in enumerate(row)}
    edges = []
    for e in spec.edges:
        if e.source not in pos or e.target not in pos or e.source == e.target:
            continue
        (r1, c1), (r2, c2) = pos[e.source], pos[e.target]
        if (r1 == r2 and abs(c1 - c2) == 1) or (c1 == c2 and abs(r1 - r2) == 1):
            edges.append((e, (r1, c1), (r2, c2)))
        else:
            logger.info("concept figure: dropped non-adjacent edge %s → %s", e.source, e.target)
    label_w = max((lib.text_w(e.label, lib.LABEL_SIZE, mono=True) for e, a, b in edges if e.label and a[0] == b[0]), default=0)
    gap_x = max(80, int(label_w) + 40)
    gap_y = 72
    cols = max(len(row) for row in spec.rows)
    kinds = list(dict.fromkeys(n.kind for n in nodes))
    legend = len(kinds) > 1 or any(e.dashed for e, _, _ in edges)
    width = 80 + cols * w + (cols - 1) * gap_x
    height = 40 + len(spec.rows) * h + (len(spec.rows) - 1) * gap_y + (96 if legend else 40)
    c = lib.Canvas(width, height, "figure", spec.title, spec.description, language)

    def box(r, col):
        return 40 + col * (w + gap_x), 40 + r * (h + gap_y)

    for e, (r1, c1), (r2, c2) in edges:
        x1, y1 = box(r1, c1)
        x2, y2 = box(r2, c2)
        if r1 == r2:
            sx, ex = (x1 + w, x2) if c2 > c1 else (x1, x2 + w)
            cy = y1 + h // 2
            c.path(c.hline(sx, cy, ex), dashed=e.dashed)
            if e.label:
                c.label((sx + ex) / 2, cy - 12, e.label)
        else:
            sy, ey = (y1 + h, y2) if r2 > r1 else (y1, y2 + h)
            cx = x1 + w // 2
            c.path(c.vline(cx, sy, ey), dashed=e.dashed)
            if e.label:
                c.label(cx + 16, (sy + ey) / 2 + 4, e.label, anchor="start")
    for r, row in enumerate(spec.rows):
        for col, n in enumerate(row):
            x, y = box(r, col)
            icon = n.icon if n.icon and _icon_ok(lib, n.icon) else None
            c.node(x, y, w, h, n.name, n.sub if has_sub else None, icon=icon, kind=n.kind)
    if legend:
        names = KIND_LABELS.get(language, KIND_LABELS["en"])
        items = [(k, names[k]) for k in kinds]
        if any(e.dashed for e, _, _ in edges):
            items.append(("arrow-dashed", names["dashed"]))
        c.legend(items)
    return c, width, height


def _icon_ok(lib, name: str) -> bool:
    if lib.is_aws_icon(name):
        return True
    try:
        lib.generic_icon(name, 0, 0)
        return True
    except KeyError:
        return False


def _page(lib, canvas, width: int, height: int) -> str:
    fonts = Path(lib.FONTS)
    faces = "".join(
        f"@font-face{{font-family:'{fam}';font-weight:{wt};src:local('{fam}'),url('file://{fonts / fn}') format('woff2');}}"
        for fam, wt, fn in [
            ("Amazon Ember", 400, "AmazonEmber_W_Rg.woff2"), ("Amazon Ember", 600, "AmazonEmber_W_SBd.woff2"),
            ("Amazon Ember", 700, "AmazonEmber_W_Bd.woff2"), ("Amazon Ember Mono", 400, "AmazonEmberMono_W_Rg.woff2"),
        ]
    )
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(canvas.title)}</title>"
        f"<style>{faces}*{{margin:0;padding:0}}body{{background:#fff}}"
        f"svg{{width:{width}px;height:{height}px;display:block}}</style></head><body>{canvas.svg()}</body></html>"
    )


SCALE = 2
# Headless Chrome reserves part of --window-size for browser UI, so the viewport is shorter than the window.
# Shoot a taller window and crop to the figure.
WINDOW_SLACK = 200


async def _screenshot(page: Path, target: Path, width: int, height: int) -> bool:
    from PIL import Image

    raw = target.with_suffix(".raw.png")
    proc = await asyncio.create_subprocess_exec(
        _chrome(), "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}", f"--window-size={width},{height + WINDOW_SLACK}",
        "--virtual-time-budget=2000", f"--screenshot={raw}", page.as_uri(),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), 60)
    except asyncio.TimeoutError:
        proc.kill()
        return False
    if not raw.is_file():
        logger.warning("chrome screenshot failed: %s", err.decode("utf-8", "replace")[-500:])
        return False
    with Image.open(raw) as image:
        image.crop((0, 0, width * SCALE, height * SCALE)).save(target, optimize=True)
    raw.unlink()
    return True


async def create(model, request: str, evidence: str, language: str, work: Path, slug: str, target: Path) -> bool:
    lib = _awsdiag()
    system = SYSTEM.replace("{icons}", _icon_names())
    user = f"<figure-request>\n{request}\n</figure-request>\n\n<evidence>\n{evidence}\n</evidence>"
    spec = await ainvoke_json(model, system, user, ConceptSpec)
    lib.WARNINGS.clear()
    if any(len(row) > 4 for row in spec.rows):
        logger.warning("concept figure %s has a row wider than 4 nodes", slug)
        return False
    canvas, width, height = _layout(spec, lib, language)
    issues = canvas.check()
    if issues:
        logger.warning("concept figure %s layout issues: %s", slug, issues)
        return False
    page = work / f"{slug}.html"
    page.write_text(_page(lib, canvas, width, height), encoding="utf-8")
    return await _screenshot(page, target, width, height)
