from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse
from app.auth.models import TokenClaims
from app.health.checks import health_checker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness():
    return ApiResponse(data=await health_checker.check_liveness())


@router.get("/ready")
async def readiness():
    result = await health_checker.check_readiness()
    return ApiResponse(data=result)


@router.get("/detail")
async def detailed_health(current_user: TokenClaims = Depends(get_current_user)):
    return ApiResponse(data=await health_checker.check_detailed())
