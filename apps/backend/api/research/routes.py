"""Serve rendered research figures to the canvas."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from agents.deep_research.diagrams.assets import resolve_asset

router = APIRouter()


@router.get("/assets/{run_id}/{filename}")
async def get_asset(run_id: str, filename: str) -> FileResponse:
    path = resolve_asset(run_id, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})
