from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_user_service
from app.api.responses import ApiResponse
from app.auth.models import TokenClaims
from app.users.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def current_user(
    token_claims: TokenClaims = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    user = await user_service.get_or_create_user(token_claims)
    return ApiResponse(data={
        "id": str(user.id),
        "supabase_user_id": user.supabase_user_id,
        "display_name": user.display_name,
        "email": user.email,
        "status": user.status,
        "created_at": user.created_at,
    })


@router.get("/verify")
async def verify_session(
    token_claims: TokenClaims = Depends(get_current_user)
):
    return ApiResponse(data={
        "valid": True,
        "user_id": token_claims.sub,
        "email": token_claims.email,
    })
