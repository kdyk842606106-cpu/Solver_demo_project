"""Real API + PostgreSQL + worker acceptance. Use an isolated acceptance database."""

import argparse
import copy
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from app.db.session import SyncSessionLocal
    from app.db.models import PlannerRunRecord
    from app.services.planner_engine_bridge import _planner_modules
    from app.services.planner_jobs import finish_job, heartbeat

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8016")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/react-cutover/acceptance.json"
    )
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8-sig"))
    if not source.get("states"):
        scenario = _planner_modules()["scenario_from_dict"](source)
        source["states"] = [
            {"id": s.id, "name": s.name} for s in scenario.state_definitions
        ]
    source["name"] = "React 256 活动队列验收"
    with httpx.Client(base_url=args.api, timeout=30) as api:
        response = api.post(
            "/api/v1/planner-scenarios/import",
            json={"scenario": source, "preserve_ids": False},
        )
        response.raise_for_status()
        record = response.json()
        scenario = record["scenario"]
        request = {
            "scenario_id": record["id"],
            "expected_revision": record["revision"],
            "current_state_ids": scenario["initial_state_ids"],
            "target_state_ids": scenario["goal_state_ids"],
            "client_request_id": str(uuid4()),
            "seed": 11,
            "budget": {"time_limit_seconds": 60},
            "display_start_at": "2026-11-04T08:00:00+08:00",
            "display_timezone": "Asia/Shanghai",
        }

        # Concurrent retries must resolve to one durable run even before the first finishes.
        def submit():
            r = httpx.post(
                args.api + "/api/v1/planner-runs/async", json=request, timeout=30
            )
            r.raise_for_status()
            return r.json()

        with ThreadPoolExecutor(max_workers=3) as pool:
            replies = list(pool.map(lambda _: submit(), range(3)))
        assert len({r["id"] for r in replies}) == 1
        run_id = replies[0]["id"]
        phases = set()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            run = api.get("/api/v1/planner-runs/" + run_id).json()
            phases.add(run["job_status"])
            if run["job_status"] in ("FINISHED", "FAILED"):
                break
            time.sleep(0.5)
        assert run["job_status"] == "FINISHED", run
        result = run["result"]["results"]["JOINT_CP_SAT"]
        assert (
            result["paths"] and result["paths"][0]["validator_status"] == "VALID"
        ), result
        assert (
            result["proven_optimal"]
            and result["paths"][0]["metrics"]["makespan"]
            == result["lower_bound"]
            == 1451
        )

        # Simulate an abandoned worker lease in the actual PostgreSQL queue.
        lost_id = "planner-run:" + str(uuid4())
        token = str(uuid4())
        with SyncSessionLocal.begin() as db:
            db.add(
                PlannerRunRecord(
                    id=lost_id,
                    scenario_id=record["id"],
                    scenario_hash=run["scenario_hash"],
                    engine="JOINT_CP_SAT",
                    status="RUNNING",
                    job_status="RUNNING",
                    execution_token=token,
                    request_json=copy.deepcopy(run["request"]),
                    lease_until=datetime.now(timezone.utc) - timedelta(seconds=60),
                )
            )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            lost = api.get("/api/v1/planner-runs/" + lost_id).json()
            if lost["job_status"] == "FAILED":
                break
            time.sleep(0.5)
        assert (
            lost["job_status"] == "FAILED"
            and "WORKER_INTERRUPTED" in lost["error_message"]
        )
        with SyncSessionLocal.begin() as db:
            stale = {
                "id": lost_id,
                "token": token,
                "hash": run["scenario_hash"],
                "request": run["request"],
            }
            assert not heartbeat(db, stale)
            assert not finish_job(db, stale, result=result)
        evidence = {
            "api": args.api,
            "scenario_id": record["id"],
            "run_id": run_id,
            "activity_count": len(scenario["activities"]),
            "windows": len(scenario.get("time_windows", [])),
            "concurrent_idempotency": True,
            "observed_phases": sorted(phases),
            "expired_lease_recovered": True,
            "stale_writes_rejected": True,
            "result": {
                k: result.get(k)
                for k in [
                    "status",
                    "proven_optimal",
                    "lower_bound",
                    "elapsed_seconds",
                    "first_solution_seconds",
                ]
            },
            "validator": result["paths"][0]["validator_status"],
            "makespan": result["paths"][0]["metrics"]["makespan"],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence, ensure_ascii=True))


if __name__ == "__main__":
    main()
