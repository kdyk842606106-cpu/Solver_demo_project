"""System status endpoints for deployment verification."""

from fastapi import APIRouter, Query

from app.services.system_status import build_system_status


router = APIRouter(tags=["system"])


@router.get("/system/status")
def system_status(
    include_data_checks: bool = Query(
        default=False,
        description="Run heavier data-format checks in addition to revision/schema checks.",
    ),
    max_issues: int = Query(default=50, ge=1, le=200),
):
    # This endpoint performs synchronous SQLAlchemy inspection. A regular
    # FastAPI handler runs in the thread pool instead of blocking the event
    # loop while deployment checks query PostgreSQL.
    return build_system_status(
        include_data_checks=include_data_checks,
        max_issues=max_issues,
    )
