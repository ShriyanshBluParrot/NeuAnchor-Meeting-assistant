from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core import rag_engine
from db import get_meeting

router = APIRouter(prefix="/meetings", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


@router.post("/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    meeting = await get_meeting(session_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Unknown session")
    if meeting["status"] != "ready":
        raise HTTPException(status_code=409, detail="Meeting is not ready yet")

    async def event_generator():
        async for token in rag_engine.answer_stream(session_id, req.question):
            yield {"data": token}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())
