"""FastAPI entrypoint: app wiring, unified error schema, CORS, scheduler."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import activations, auth, licenses, products, stats, users, verify
from app.config import settings
from app.core.errors import ApiError
from app.schemas.common import ErrorResponse
from app.services.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_json(status_code: int, error_code: str, message: str, detail=None) -> JSONResponse:
    body = ErrorResponse(error_code=error_code, message=message, detail=detail)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    return _error_json(exc.status_code, exc.error_code, exc.message, exc.detail)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    detail = [
        {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")}
        for e in exc.errors()
    ]
    return _error_json(422, "validation_error", "요청 형식이 올바르지 않습니다.", detail)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    return _error_json(exc.status_code, "http_error", str(exc.detail))


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}


for router in (
    auth.router,
    users.router,
    products.router,
    licenses.router,
    activations.router,
    verify.router,
    stats.router,
):
    app.include_router(router, prefix=settings.api_prefix)
