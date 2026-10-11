from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.service import assistant_service
from app.assistant.tools import AuthorizedTripTools
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models import User

router = APIRouter(prefix="/assistant", tags=["AI Trip Assistant"])


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Retrieve authorized context data
    trips = await AuthorizedTripTools.get_my_recent_trips(current_user.id, db)
    active_status = await AuthorizedTripTools.get_active_ride_status(current_user.id, db)

    context = {
        "user_name": current_user.full_name,
        "recent_trips": trips,
        "active_status": active_status,
    }

    ai_reply = await assistant_service.generate_response(req.message, context)
    return ChatResponse(response=ai_reply)
