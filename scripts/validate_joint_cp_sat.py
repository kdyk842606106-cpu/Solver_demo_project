"""Replay a raw experiment input through the product bridge, without an oracle.

Usage: python scripts/validate_joint_cp_sat.py INPUT_JSON --seconds 60
The source file is read only; acceptance evidence is written under docs/validation.
"""
import argparse
import copy
from dataclasses import replace
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.planner_engine_bridge import _planner_modules, run_engine
from app.services.planner_scenarios import expand_packages, validate_scenario


def compact_result(result):
    summary = {key: value for key, value in result.items() if key != "paths"}
    summary["paths"] = []
    for path in result.get("paths", []):
        kept = {key: path[key] for key in ("path_id", "metrics", "validator_status", "validator_version",
                "raw_makespan", "normalization_saved_time", "discovered_at_seconds", "final_state_ids")}
        kept["executions"] = [{key: row[key] for key in ("activity_id", "ordinal", "start_time", "end_time")}
                              for row in path["executions"]]
        summary["paths"].append(kept)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/validation/JOINT_CP_SAT_256_20261103.json")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    modules = _planner_modules()
    original = modules["scenario_from_dict"](payload)
    # Experimental inputs infer state definitions. The product contract requires
    # explicit definitions; materialize names/IDs without changing any constraint.
    if not payload.get("states"):
        payload["states"] = [{"id": state.id, "name": state.name} for state in original.state_definitions]
    issues = validate_scenario(copy.deepcopy(payload))
    if issues:
        raise ValueError(issues[:5])
    effective = modules["scenario_from_dict"](expand_packages(payload))
    # The UI derives a milestone display flag from relation roles. It does not
    # affect this joint compiler or Simulator; all execution attributes must match.
    assert tuple(replace(a, is_milestone=False) for a in original.activities) == tuple(
        replace(a, is_milestone=False) for a in effective.activities)
    for field in ("resources", "external_events", "initial_state_ids", "goal_state_ids",
                  "forbidden_state_ids", "execution_mode", "max_steps", "start_time"):
        assert getattr(original, field) == getattr(effective, field), field
    result = run_engine(payload, engine="JOINT_CP_SAT", run_id="product-joint-acceptance", seed=args.seed,
                        budget_override={"time_limit_seconds": args.seconds})
    evidence = {"source": str(args.input.resolve()), "source_sha256": hashlib.sha256(raw).hexdigest(),
                "semantic_roundtrip_checked": True, "activity_count": len(original.activities),
                "window_count": len(payload.get("time_windows", [])), "result": compact_result(result)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("status", "error", "proven_optimal", "lower_bound",
                                                     "first_solution_seconds", "elapsed_seconds")}, ensure_ascii=False))
    assert result["paths"] and all(p["validator_status"] == "VALID" for p in result["paths"]), result["status"]


if __name__ == "__main__":
    main()
