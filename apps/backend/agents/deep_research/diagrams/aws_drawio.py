"""AWS architecture figures through the aws-drawio-diagram skill's own tooling.

The model fills a structured brief; the skill's scaffold/build scripts do layout and validation; the drawio
CLI exports PNG. Builder errors go back to the model as feedback, the same loop the skill runs by hand.
"""
import asyncio
import json
import logging
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agents.deep_research.diagrams.assets import find_skill_dir
from agents.deep_research.llm import ainvoke_json

logger = logging.getLogger(__name__)
MAX_REPAIRS = 2


class Component(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    service: str = Field(description="Display name, e.g. 'Lambda', 'Amazon Bedrock'")
    stencil: str = Field(description="Exact stencil name from the catalog")
    pattern: Literal["service", "resource"] = "service"
    role: str
    group: str = Field(description="Role group name, or 'outside' for actors outside AWS")


class Relationship(BaseModel):
    source: str
    target: str
    what: str = Field(description="Short noun phrase drawn on the arrow, <= 3 words")
    kind: Literal["sync", "async", "aux"] = "sync"


class AwsDiagramSpec(BaseModel):
    title: str
    components: list[Component] = Field(min_length=2, max_length=16)
    relationships: list[Relationship] = Field(min_length=1, max_length=20)


def skill_dir() -> Path | None:
    return find_skill_dir("AWS_DRAWIO_SKILL_DIR", "aws-drawio-diagram")


def available() -> bool:
    return skill_dir() is not None and shutil.which("drawio") is not None


@lru_cache(maxsize=1)
def _catalog() -> tuple[str, frozenset[str]]:
    root = skill_dir()
    index = json.loads((root / "scripts/stencil-index.json").read_text())["stencils"]
    names = frozenset(name for name, meta in index.items() if meta.get("renderable", True))
    lines = [
        f"{name} | {meta.get('label', '')} | {meta.get('kind')}"
        for name, meta in index.items()
        if meta.get("renderable", True) and meta.get("kind") in ("service", "resource")
    ]
    aliases = (root / "references/aws-icons-aliases.md").read_text()
    return "stencil | label | pattern\n" + "\n".join(lines) + "\n\n" + aliases, names


SYSTEM = """You are the Architect hat of the aws-drawio-diagram skill. Turn a figure request into a diagram
brief that looks like an AWS reference architecture.

Rules:
- Only real AWS services or actors that the request and evidence name. No abstract boxes ("Platform", "Agents").
- Every stencil must be copied exactly from the catalog. Renamed services: see the alias table
  (OpenSearch -> elasticsearch_service, CloudWatch -> cloudwatch_2, SageMaker AI -> sagemaker_2).
- pattern "resource" for actors and generic marks (user, users, mobile_client, client); "service" otherwise.
- 2-6 role groups with short names (<= 18 characters). Actors outside AWS use group "outside".
- One edge per real interaction, primary request path first. "what" is a short noun phrase (<= 3 words,
  words <= 12 letters), e.g. "invoke model", "store vectors". kind: sync (solid), async (dashed), aux
  (dashed, for monitoring/logging/auth checks).
- Every component has at least one relationship. Keep it readable: 5-12 components.

<stencil-catalog>
{catalog}
</stencil-catalog>"""


def render_brief(spec: AwsDiagramSpec, language: str) -> str:
    kind = {"sync": "sync", "async": "async (dashed)", "aux": "aux (dashed)"}
    rows = [
        f"| {c.id} | {c.service} (`{c.stencil}`{', resource' if c.pattern == 'resource' else ''}) "
        f"| {c.role} | {c.group} |"
        for c in spec.components
    ]
    rels = [
        f"| {i} | {r.source} → {r.target} | {r.what} | {kind[r.kind]} |"
        for i, r in enumerate(spec.relationships, 1)
    ]
    groups = list(dict.fromkeys(c.group for c in spec.components if c.group != "outside"))
    return "\n".join([
        f"# {spec.title}", "", "Audience: technical.", f"Language: {language}", "",
        "## Components", "| id | Service (stencil) | Role in this system | Group |", "|---|---|---|---|", *rows, "",
        "## Relationships", "| # | From → To | What flows | Kind |", "| --- | --- | --- | --- |", *rels, "",
        "## Groups", " · ".join(groups), "",
    ])


def _precheck(spec: AwsDiagramSpec, names: frozenset[str]) -> list[str]:
    ids = {c.id for c in spec.components}
    errors = [f"unknown stencil '{c.stencil}' for {c.id}" for c in spec.components if c.stencil not in names]
    errors += [
        f"relationship {r.source} → {r.target} names an undefined component"
        for r in spec.relationships if r.source not in ids or r.target not in ids
    ]
    linked = {r.source for r in spec.relationships} | {r.target for r in spec.relationships}
    errors += [f"component {i} has no relationship" for i in ids - linked]
    return errors


async def _run(*args: str, cwd: Path, timeout: float = 120) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, f"timed out: {' '.join(args[:3])}"
    return proc.returncode or 0, out.decode("utf-8", "replace")


async def _build(spec: AwsDiagramSpec, language: str, work: Path, slug: str) -> tuple[bool, str]:
    scripts = skill_dir() / "scripts"
    for stale in work.glob(f"{slug}.*"):
        stale.unlink()  # the contract file freezes ids; a repaired spec is a new architecture
    (work / f"{slug}.brief.md").write_text(render_brief(spec, language), encoding="utf-8")
    code, out = await _run(sys.executable, str(scripts / "scaffold_spec.py"), f"{slug}.brief.md", f"{slug}.json", cwd=work)
    if code != 0:
        return False, out
    code, build_out = await _run(sys.executable, str(scripts / "build_diagram.py"), f"{slug}.json", f"{slug}.drawio", cwd=work)
    return code == 0, out + build_out


async def _export(work: Path, slug: str, target: Path) -> bool:
    args = ["drawio", "-x", "-f", "png", "-b", "10", "-s", "2", "-o", str(target), f"{slug}.drawio"]
    if shutil.which("xvfb-run"):
        args = ["xvfb-run", "-a", *args]
    code, out = await _run(*args, cwd=work, timeout=90)
    if code != 0 or not target.is_file():
        logger.warning("drawio export failed: %s", out[-800:])
        return False
    return True


async def create(model, request: str, evidence: str, language: str, work: Path, slug: str, target: Path) -> bool:
    """Render one AWS architecture figure to `target` (PNG). Returns False when it could not be made clean."""
    catalog, names = _catalog()
    system = SYSTEM.replace("{catalog}", catalog)
    user = f"<figure-request>\n{request}\n</figure-request>\n\n<evidence>\n{evidence}\n</evidence>"
    spec = await ainvoke_json(model, system, user, AwsDiagramSpec)
    for attempt in range(MAX_REPAIRS + 1):
        problems = _precheck(spec, names)
        if not problems:
            ok, log = await _build(spec, language, work, slug)
            if ok:
                return await _export(work, slug, target)
            problems = [line.strip() for line in log.splitlines() if any(
                key in line for key in ("ERROR", "warn:", "W4", "W5", "W7", "W8", "W9", "unresolved", "hint:")
            )][:25] or [log[-1500:]]
        logger.info("aws diagram %s attempt %d problems: %s", slug, attempt, problems)
        if attempt == MAX_REPAIRS:
            return False
        repair = (
            f"{user}\n\n<previous-brief>\n{spec.model_dump_json()}\n</previous-brief>\n"
            "The diagram builder rejected it:\n- " + "\n- ".join(problems) +
            "\nFix the brief: look up exact stencils, shorten 'what' phrases (<= 6 letters across group borders), "
            "reduce components or move them to fewer groups. Keep the architecture faithful."
        )
        spec = await ainvoke_json(model, system, repair, AwsDiagramSpec)
    return False
