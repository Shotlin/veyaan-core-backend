from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user_context
from app.api.responses import ApiResponse
from app.auth.user_context import UserContext

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_current_user_info(current_user: UserContext = Depends(get_current_user_context)):
    return ApiResponse(
        data={
            "id": str(current_user.id),
            "supabase_user_id": current_user.supabase_user_id,
            "email": current_user.email,
            "status": current_user.status,
            "created_at": None,
        }
    )


@router.get("/verify")
async def verify_session(current_user: UserContext = Depends(get_current_user_context)):
    return ApiResponse(
        data={
            "valid": True,
            "user_id": current_user.supabase_user_id,
            "email": current_user.email,
        }
    )
