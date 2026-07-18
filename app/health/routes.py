from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.api.dependencies import get_current_user_context
from app.auth.user_context import UserContext
from app.health.checks import health_checker

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness():
    return JSONResponse(content=await health_checker.check_liveness())


@router.get("/ready")
async def readiness():
    result = await health_checker.check_readiness()
    status_code = 200 if result.get("ready") else 503
    return JSONResponse(content=result, status_code=status_code)


@router.get("/detail")
async def detailed_health(current_user: UserContext = Depends(get_current_user_context)):
    return JSONResponse(content=await health_checker.check_detailed())
