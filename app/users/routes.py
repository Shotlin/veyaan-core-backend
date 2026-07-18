from fastapi import APIRouter, Depends

from app.api.responses import ApiResponse
from app.auth.dependencies import get_current_user
from app.users.models import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return ApiResponse(data={
        "id": str(current_user.id),
        "display_name": current_user.display_name,
        "email": current_user.email,
        "status": current_user.status.value,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    })
