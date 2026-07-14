"""
FastAPI application entry point.

Registers all API routes and global exception handlers.
"""

import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db.session import async_engine
from app.api.v1 import adjustments, calendars, imports, master_data, plans, solve, state, system
from app.services.plan_adjustment import PlanAdjustmentError
from app.services.system_status import get_release_info

FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_DIST = FRONTEND_ROOT / "dist"
FRONTEND_DIST_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_DEV_INDEX = FRONTEND_ROOT / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print("Starting up...")
    from app.db.session import patch_sqlite_types
    patch_sqlite_types()
    yield
    # Shutdown
    print("Shutting down...")
    await async_engine.dispose()


app = FastAPI(
    title="State-Driven Process Planning + Resource Optimization System",
    description="API for process planning and resource optimization",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Exception handlers
# ============================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Structured HTTP error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": f"HTTP_{exc.status_code}",
            "error_message": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — returns 500."""
    import os

    content = {
        "error_code": "INTERNAL_ERROR",
        "error_message": str(exc),
    }
    if os.getenv("DEBUG", "").lower() in ("1", "true"):
        content["traceback"] = traceback.format_exc()
    return JSONResponse(status_code=500, content=content)


@app.exception_handler(PlanAdjustmentError)
async def plan_adjustment_exception_handler(request: Request, exc: PlanAdjustmentError):
    """Preserve stable plan-adjustment error codes at the API boundary."""
    if exc.code in {"PLAN_NOT_FOUND", "ADJUSTMENT_NOT_FOUND"}:
        status_code = 404
    elif exc.code in {"ADJUSTMENT_STALE", "BASELINE_PLAN_CHANGED", "PLAN_NOT_BASELINE"}:
        status_code = 409
    else:
        status_code = 422
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": exc.code,
            "error_message": str(exc),
            "details": exc.details,
        },
    )


# ============================================================
# Routes
# ============================================================


app.include_router(solve.router, prefix="/api/v1")
app.include_router(state.router, prefix="/api/v1")
app.include_router(master_data.router, prefix="/api/v1")
app.include_router(plans.router, prefix="/api/v1")
app.include_router(imports.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(calendars.router, prefix="/api/v1")
app.include_router(adjustments.router, prefix="/api/v1")
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False),
    name="frontend-assets",
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    release = get_release_info()
    return {
        "status": "healthy",
        "version": release["app_version"],
        "commit": release["app_commit"],
        "release_id": release["release_id"],
    }


@app.get("/")
async def frontend_index():
    """Serve the built frontend from the API host, falling back to the Vite entry."""
    return _frontend_index_response()


@app.get("/frontend")
async def frontend_alias():
    """Convenience alias for the local frontend."""
    return _frontend_index_response()


@app.get("/frontend/{path:path}")
async def frontend_spa_alias(path: str):
    """Serve the frontend SPA for browser routes under /frontend."""
    return _frontend_index_response()


def _frontend_index_response():
    if FRONTEND_DIST_INDEX.exists():
        return FileResponse(FRONTEND_DIST_INDEX)
    if FRONTEND_DEV_INDEX.exists():
        return FileResponse(FRONTEND_DEV_INDEX)
    raise HTTPException(status_code=404, detail="Frontend index.html not found")
