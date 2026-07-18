from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.errors import ApiError, ErrorCode
from app.api.responses import ErrorDetail, ErrorResponse
from app.observability.logging import logger


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except ApiError as exc:
            request_id = getattr(request.state, "request_id", "unknown")
            trace_id = getattr(request.state, "trace_id", "unknown")

            logger.warning(
                "api_exception",
                request_id=request_id,
                trace_id=trace_id,
                error_code=exc.code.value,
                message=exc.message,
                details=exc.details,
                path=request.url.path,
            )

            return JSONResponse(
                status_code=exc.status_code,
                content=ErrorResponse(
                    request_id=request_id,
                    error=ErrorDetail(
                        code=exc.code.value,
                        message=exc.message,
                        details=exc.details,
                    ),
                ).model_dump(mode="json"),
            )
        except Exception as exc:
            request_id = getattr(request.state, "request_id", "unknown")
            trace_id = getattr(request.state, "trace_id", "unknown")

            logger.exception(
                "unhandled_exception",
                request_id=request_id,
                trace_id=trace_id,
                path=request.url.path,
                error=str(exc),
            )

            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    request_id=request_id,
                    error=ErrorDetail(
                        code=ErrorCode.INTERNAL_ERROR.value,
                        message="An internal error occurred",
                    ),
                ).model_dump(mode="json"),
            )
