"""Verify that the local verifier-machine deployment is safe to run.

Checks:
- database connectivity through the project SQLAlchemy settings
- Alembic current revision equals the migration script head
- mapped SQLAlchemy tables/columns exist in the database
- optional data-format checks for feature_key and enum-value consistency
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.system_status import build_system_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Check deployment readiness.")
    parser.add_argument(
        "--strict-data",
        action="store_true",
        help="Run data-format checks and fail on detected data issues.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete status payload as JSON.",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=50,
        help="Maximum issues to report.",
    )
    args = parser.parse_args()

    status = build_system_status(
        include_data_checks=args.strict_data,
        max_issues=args.max_issues,
    )

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        release = status["release"]
        alembic = status["database"]["alembic"]
        print("Deployment readiness")
        print(f"  status: {status['status']}")
        print(f"  app_version: {release.get('app_version')}")
        print(f"  app_commit: {release.get('app_commit')}")
        print(f"  release_id: {release.get('release_id')}")
        print(f"  alembic current: {', '.join(alembic['current_heads']) or '<none>'}")
        print(f"  alembic expected: {', '.join(alembic['expected_heads']) or '<none>'}")
        print(f"  schema issues: {status['database']['schema_issue_count']}")
        print(f"  data issues: {status['database']['data_issue_count']}")
        if status["database"].get("data_checks_skipped"):
            print("  data checks: skipped because schema checks failed")
        for issue in status["issues"]:
            print(f"  FAIL {issue['code']}: {issue['message']}")
            print(f"       {json.dumps(issue['detail'], ensure_ascii=False)}")
        if status["truncated"]:
            print("  More issues exist but were truncated.")

    return 0 if status["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
