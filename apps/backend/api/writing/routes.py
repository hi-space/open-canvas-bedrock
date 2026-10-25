"""The writing API never invokes the conversation graph."""
from fastapi import APIRouter

from api.writing.models import WritingRequest, WritingResponse
from api.writing.service import propose_writing

router = APIRouter()


@router.post("/propose", response_model=WritingResponse)
async def propose_endpoint(request: WritingRequest) -> WritingResponse:
    return await propose_writing(request)
