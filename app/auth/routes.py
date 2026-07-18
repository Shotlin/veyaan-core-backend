from fastapi import APIRouter, Depends

from app.api.responses import ApiResponse
from app.auth.dependencies import get_current_user, get_token_claims
from app.auth.models import TokenClaims
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return ApiResponse(data={
        "id": str(current_user.id),
        "supabase_user_id": current_user.supabase_user_id,
        "display_name": current_user.display_name,
        "email": current_user.email,
        "status": current_user.status.value,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    })


@router.get("/verify")
async def verify_session(claims: TokenClaims = Depends(get_token_claims)):
    return ApiResponse(data={
        "valid": True,
        "user_id": claims.sub,
        "email": claims.email,
        "exp": claims.exp,
    })
