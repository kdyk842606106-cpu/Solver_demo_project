"""Durable queue operations. Short transactions never span solver execution."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, update, text
from app.db.models import PlannerRunRecord

LEASE_SECONDS = 45


def check_async_request(request):
    seconds = request.get("budget", {}).get("time_limit_seconds", 60)
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or not 0 <= seconds <= 3600
    ):
        raise ValueError("求解预算必须是 0–3600 秒")
    if request.get("objectives") != [{"type": "minimize_makespan", "weight": 1.0}]:
        raise ValueError("联合求解首期只支持最短总工期")
    start = datetime.fromisoformat(request["display_start_at"].replace("Z", "+00:00"))
    if start.tzinfo is None:
        raise ValueError("计划开始时间必须包含时区偏移")
    try:
        ZoneInfo(request["display_timezone"])
    except (KeyError, ValueError) as exc:
        raise ValueError("计划时区无效") from exc


def check_joint_capabilities(scenario):
    for key in (
        "calendar",
        "calendars",
        "scheduling_rules",
        "adjustments",
        "resource_instances",
    ):
        if scenario.get(key):
            raise ValueError(f"联合求解暂不支持 {key}，请使用支持该约束的入口")
    if any(
        e.get("add_state_ids") or e.get("remove_state_ids")
        for e in scenario.get("external_events", [])
    ):
        raise ValueError("联合求解暂不支持改变状态的外部事件")


def expire_jobs(db):
    now = datetime.now(timezone.utc)
    db.execute(
        update(PlannerRunRecord)
        .where(
            PlannerRunRecord.job_status == "RUNNING",
            PlannerRunRecord.lease_until < now,
        )
        .values(
            job_status="FAILED",
            status="ERROR",
            finished_at=now,
            lease_until=None,
            error_message="WORKER_INTERRUPTED: 求解进程心跳中断，请重新提交",
            progress_version=PlannerRunRecord.progress_version + 1,
        )
    )


def claim_job(db):
    # Serialize claim decisions across workers, while allowing status reads/writes.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(73402520)"))
    expire_jobs(db)
    if db.execute(
        select(PlannerRunRecord.id)
        .where(PlannerRunRecord.job_status == "RUNNING")
        .limit(1)
    ).first():
        return None
    job = db.execute(
        select(PlannerRunRecord)
        .where(PlannerRunRecord.job_status == "QUEUED")
        .order_by(PlannerRunRecord.created_at, PlannerRunRecord.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None
    now = datetime.now(timezone.utc)
    job.job_status = "RUNNING"
    job.status = "RUNNING"
    job.started_at = now
    job.execution_token = str(uuid4())
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    db.flush()
    return {
        "id": job.id,
        "token": job.execution_token,
        "request": job.request_json,
        "hash": job.scenario_hash,
    }


def heartbeat(db, job):
    result = db.execute(
        update(PlannerRunRecord)
        .where(
            PlannerRunRecord.id == job["id"],
            PlannerRunRecord.execution_token == job["token"],
            PlannerRunRecord.job_status == "RUNNING",
            PlannerRunRecord.lease_until >= datetime.now(timezone.utc),
        )
        .values(
            lease_until=datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)
        )
    )
    return result.rowcount == 1


def save_progress(db, job, version, metrics, plan_version, candidate):
    r = PlannerRunRecord
    values = dict(progress_version=version, progress_json=metrics)
    if candidate is not None:
        values.update(plan_version=plan_version, live_plan_json=candidate)
    updated = db.execute(update(r).where(
        r.id == job["id"], r.execution_token == job["token"], r.job_status == "RUNNING",
        r.lease_until >= datetime.now(timezone.utc), r.progress_version < version,
    ).values(**values))
    return updated.rowcount == 1


def finish_job(db, job, result=None, error=None):
    if result and result.get("scenario_hash") != job["hash"]:
        error = "求解结果快照哈希不一致"
    values = dict(
        job_status="FAILED" if error else "FINISHED",
        status="ERROR" if error else result["status"],
        finished_at=datetime.now(timezone.utc),
        lease_until=None,
        error_message=error,
        progress_version=PlannerRunRecord.progress_version + 1,
    )
    if not error:
        values["result_json"] = {
            "run_id": job["id"],
            "scenario_hash": job["hash"],
            "base_scenario_hash": job["request"]["base_scenario_hash"],
            "results": {"JOINT_CP_SAT": result},
        }
    result = db.execute(
        update(PlannerRunRecord)
        .where(
            PlannerRunRecord.id == job["id"],
            PlannerRunRecord.execution_token == job["token"],
            PlannerRunRecord.job_status == "RUNNING",
            PlannerRunRecord.lease_until >= datetime.now(timezone.utc),
        )
        .values(**values)
    )
    return result.rowcount == 1
