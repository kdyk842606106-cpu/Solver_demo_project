"""Run with python -m app.planner_worker. One durable job, one spawned process."""

from __future__ import annotations

import logging
import multiprocessing as mp
import time

from app.db.session import SyncSessionLocal
from app.services.planner_jobs import claim_job, heartbeat, finish_job
from app.services.planner_jobs import save_progress

log = logging.getLogger("planner-worker")


def solve_child(connection, job):
    try:
        from app.services.planner_engine_bridge import run_engine

        def report(metrics, best):
            candidate = None
            if best is not None:
                from planner_experiment.models import to_primitive
                candidate = {"validator_status": best.validator_status, "executions": to_primitive(best.executions),
                             "metrics": to_primitive(best.metrics)}
            connection.send(("progress", metrics, candidate))

        request = job["request"]
        result = run_engine(
            request["effective_scenario_snapshot"],
            engine="JOINT_CP_SAT",
            run_id=job["id"],
            seed=request["seed"],
            budget_override=request.get("effective_budget") or request.get("budget") or {"time_limit_seconds": 60},
            objectives=request["objectives"],
            progress_observer=report,
        )
        connection.send((result, None))
    except BaseException as exc:
        connection.send((None, f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


def execute_job(job):
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=solve_child, args=(sender, job))
    child.start()
    sender.close()
    started = time.monotonic()
    hard_limit = (
        float((job["request"].get("effective_budget") or job["request"].get("budget", {})).get("time_limit_seconds", 60)) + 120
    )
    result, error = None, None
    buffer = ProgressBuffer()
    last_heartbeat = started
    try:
        while True:
            if receiver.poll(buffer.poll_timeout()):
                try:
                    message = receiver.recv()
                except EOFError:
                    error = "WORKER_INTERRUPTED: 求解子进程异常退出"
                    break
                if message[0] != "progress":
                    result, error = message
                    break
                buffer.receive(*message[1:])
            elif not child.is_alive():
                error = f"WORKER_INTERRUPTED: 求解子进程退出 ({child.exitcode})"
                break
            if time.monotonic() - started > hard_limit:
                error = "WORKER_WATCHDOG: 求解进程超过预算及清理宽限时间"
                break
            now = time.monotonic()
            if buffer.due(now) or now - last_heartbeat >= 2:
                with SyncSessionLocal.begin() as db:
                    if not heartbeat(db, job):
                        return
                    if buffer.due(now) and not buffer.flush(db, job):
                        return
                last_heartbeat = now
        with SyncSessionLocal.begin() as db:
            if buffer.dirty and not buffer.flush(db, job):
                return
            finish_job(db, job, result, error)
    finally:
        receiver.close()
        child.join(timeout=2)
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)


class ProgressBuffer:
    """Persist the first incumbent immediately; coalesce subsequent samples and plans."""
    interval = 5

    def __init__(self):
        self.version = self.plan_version = 0
        self.metrics = self.candidate = None
        self.last_write = 0
        self.dirty = self.first_plan = False

    def receive(self, metrics, candidate):
        self.version += 1
        self.metrics, self.dirty = metrics, True
        if candidate is not None:
            self.first_plan = self.plan_version == 0
            self.plan_version = self.version
            self.candidate = candidate

    def due(self, now):
        return self.dirty and (self.first_plan or now - self.last_write >= self.interval)

    def poll_timeout(self):
        if not self.dirty:
            return 2
        return max(0, min(2, self.last_write + self.interval - time.monotonic()))

    def flush(self, db, job):
        ok = save_progress(db, job, self.version, self.metrics, self.plan_version, self.candidate)
        self.last_write = time.monotonic()
        self.dirty = self.first_plan = False
        self.candidate = None
        return ok


def main():
    logging.basicConfig(level=logging.INFO)
    log.info("Planner worker started; global concurrency=1")
    while True:
        try:
            with SyncSessionLocal.begin() as db:
                job = claim_job(db)
            if job:
                log.info("Executing %s", job["id"])
                execute_job(job)
            else:
                time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("Worker iteration failed; leases protect interrupted jobs")
            time.sleep(5)


if __name__ == "__main__":
    main()
