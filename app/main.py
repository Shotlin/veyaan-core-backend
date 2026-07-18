from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.middleware.error_handling import ErrorHandlingMiddleware
from app.api.middleware.request_id import RequestIdMiddleware
from app.api.middleware.tracing import TracingMiddleware
from app.approvals.routes import router as approvals_router
from app.audit.routes import router as audit_router
from app.auth.routes import router as auth_router
from app.cache import valkey_client
from app.commands.routes import router as commands_router
from app.config import settings
from app.database.connection import close_db, init_db
from app.devices.routes import router as devices_router
from app.emergency_stop.routes import router as emergency_stop_router
from app.events.nats_client import nats_client
from app.health.routes import router as health_router
from app.notifications.routes import router as notifications_router
from app.observability.logging import logger
from app.security.rate_limiter import RateLimitMiddleware
from app.users.routes import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_up", service_version=settings.SERVICE_VERSION)

    await init_db()
    await valkey_client.connect()
    await nats_client.connect()

    logger.info("startup_complete")

    yield

    logger.info("shutting_down")

    await nats_client.disconnect()
    await valkey_client.disconnect()
    await close_db()

    logger.info("shutdown_complete")


app = FastAPI(
    title="VEYAAN API",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(TracingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimitMiddleware)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routes
app.include_router(health_router)
app.include_router(auth_router, prefix="/v1")
app.include_router(users_router, prefix="/v1")
app.include_router(devices_router, prefix="/v1")
app.include_router(commands_router, prefix="/v1")
app.include_router(emergency_stop_router, prefix="/v1")
app.include_router(approvals_router, prefix="/v1")
app.include_router(audit_router, prefix="/v1")
app.include_router(notifications_router)


@app.get("/")
async def root():
    return {
        "service": "VEYAAN API",
        "version": settings.SERVICE_VERSION,
        "environment": settings.ENVIRONMENT,
    }
