from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse
from app.auth.models import TokenClaims

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_current_user_profile(
    token_claims: TokenClaims = Depends(get_current_user)
):
    return ApiResponse(data={
        "user_id": token_claims.sub,
        "email": token_claims.email,
        "email_verified": token_claims.email_verified,
    })
