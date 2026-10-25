"""Figure rendering for research documents. Each renderer returns False instead of raising when it cannot
produce a clean figure; a document without a figure beats a document with a broken one."""
import logging
import tempfile
from pathlib import Path

from agents.deep_research.diagrams import aws_drawio, concept
from agents.deep_research.diagrams.assets import asset_url, run_dir

logger = logging.getLogger(__name__)

RENDERERS = {"aws_architecture": aws_drawio, "concept": concept}


def available_kinds() -> list[str]:
    return [kind for kind, renderer in RENDERERS.items() if renderer.available()]


async def render_figure(model, kind: str, request: str, evidence: str, language: str,
                        owner: str, run_id: str, slug: str) -> str | None:
    """Render a figure into the owner's asset folder and return its canvas URL, or None."""
    renderer = RENDERERS.get(kind)
    if renderer is None or not renderer.available():
        return None
    try:
        target = run_dir(owner, run_id) / f"{slug}.png"
        with tempfile.TemporaryDirectory(prefix=f"fig-{slug}-") as tmp:
            ok = await renderer.create(model, request, evidence, language, Path(tmp), slug, target)
    except Exception:
        logger.exception("figure %s (%s) failed", slug, kind)
        return None
    return asset_url(run_id, target.name) if ok and target.is_file() else None
