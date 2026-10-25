"""Serve rendered research figures to the canvas."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from agents.deep_research.diagrams.assets import resolve_asset
from api.workspaces.identity import owner_key

router = APIRouter()


@router.get("/assets/{run_id}/{filename}")
def get_asset(run_id: str, filename: str, owner: str = Depends(owner_key)) -> FileResponse:
    # Another owner's figure is indistinguishable from a missing one.
    path = resolve_asset(owner, run_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
