from fastapi import APIRouter

from schemas import CopilotChatRequest, CopilotChatResponse
from services import ai_service

router = APIRouter(tags=["copilot"])


# ── POST /api/copilot/chat ────────────────────────────────────────────────────

@router.post("/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(body: CopilotChatRequest) -> CopilotChatResponse:
    result = await ai_service.chat(
        message=body.message,
        current_page=body.current_page,
        data_context=body.data_context,
        history=body.history,
    )
    return CopilotChatResponse(
        assistant_text=result["assistant_text"],
        suggestions=result.get("suggestions"),
    )
