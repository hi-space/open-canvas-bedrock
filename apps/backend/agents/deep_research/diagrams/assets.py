"""Where rendered figures live on disk and how the canvas reaches them."""
import os
import re
from pathlib import Path

ASSET_URL_PREFIX = "/api/research/assets"
_OWNER = re.compile(r"^[a-f0-9]{64}$")
_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SAFE_FILE = re.compile(r"^[A-Za-z0-9_-]{1,80}\.png$")


def assets_root() -> Path:
    """RESEARCH_ASSETS_DIR, else beside project files on persistent storage, else a local data folder."""
    if os.getenv("RESEARCH_ASSETS_DIR"):
        return Path(os.environ["RESEARCH_ASSETS_DIR"])
    if os.getenv("WORKSPACE_ROOT"):
        return Path(os.environ["WORKSPACE_ROOT"]) / "research-assets"
    return Path(__file__).resolve().parents[3] / "data" / "research_assets"


def run_dir(owner: str, run_id: str) -> Path:
    """Figures are stored per owner; only that owner's session can read them back."""
    if not _OWNER.match(owner) or not _SAFE.match(run_id):
        raise ValueError("invalid owner or run id")
    path = assets_root() / owner / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def asset_url(run_id: str, filename: str) -> str:
    return f"{ASSET_URL_PREFIX}/{run_id}/{filename}"


def resolve_asset(owner: str, run_id: str, filename: str) -> Path | None:
    """Path for a served asset, or None when the name is not one this module could have written."""
    if not _OWNER.match(owner) or not _SAFE.match(run_id) or not _SAFE_FILE.match(filename):
        return None
    path = assets_root() / owner / run_id / filename
    return path if path.is_file() else None


def find_skill_dir(env_var: str, plugin: str) -> Path | None:
    """An explicit env path, else the newest installed Claude Code plugin version of the skill."""
    explicit = os.getenv(env_var)
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_dir() else None
    candidates = (Path.home() / ".claude/plugins/cache").glob(f"*/{plugin}/*/skills/{plugin}")

    def version(path: Path) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in path.parents[1].name.split("."))
        except ValueError:
            return (0,)

    ordered = sorted((p for p in candidates if p.is_dir()), key=version)
    return ordered[-1] if ordered else None
