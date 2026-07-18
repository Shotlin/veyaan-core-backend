from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user_context
from app.api.responses import ApiResponse
from app.auth.user_context import UserContext

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/profile")
async def get_profile(current_user: UserContext = Depends(get_current_user_context)):
    return ApiResponse(
        data={
            "id": str(current_user.id),
            "email": current_user.email,
            "status": current_user.status,
            "supabase_user_id": current_user.supabase_user_id,
        }
    )
