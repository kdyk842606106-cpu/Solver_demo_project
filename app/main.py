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

from app.db.session import async_engine
from app.api.v1 import master_data, plans, solve, state

FRONTEND_INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


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


# ============================================================
# Routes
# ============================================================


app.include_router(solve.router, prefix="/api/v1")
app.include_router(state.router, prefix="/api/v1")
app.include_router(master_data.router, prefix="/api/v1")
app.include_router(plans.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def frontend_index():
    """Serve the local single-file frontend from the API host to avoid file:// origins."""
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(FRONTEND_INDEX)


@app.get("/frontend")
async def frontend_alias():
    """Convenience alias for the local frontend."""
    return await frontend_index()
