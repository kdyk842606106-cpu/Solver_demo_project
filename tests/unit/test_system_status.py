import json

import pytest

from app.services import system_status


def test_release_info_uses_relative_metadata_source(tmp_path, monkeypatch):
    (tmp_path / "VERSION.json").write_text(
        json.dumps(
            {
                "app_version": "0.3.0",
                "app_commit": "abc123",
                "release_id": "review-build",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(system_status, "PROJECT_ROOT", tmp_path)
    for key in ("APP_VERSION", "APP_COMMIT", "RELEASE_ID"):
        monkeypatch.delenv(key, raising=False)

    release = system_status.get_release_info()

    assert release == {
        "app_version": "0.3.0",
        "app_commit": "abc123",
        "release_id": "review-build",
        "version_file": "VERSION.json",
        "version_file_error": None,
    }
    assert str(tmp_path) not in json.dumps(release)


def test_build_system_status_skips_data_checks_when_schema_is_invalid(monkeypatch):
    schema_issue = system_status.DeployIssue(
        code="SCHEMA_TABLE_MISSING",
        message="missing",
        detail={"table": "state_node"},
    )
    monkeypatch.setattr(
        system_status,
        "get_alembic_status",
        lambda: {"current_heads": ["008"], "expected_heads": ["009"], "is_current": False},
    )
    monkeypatch.setattr(system_status, "check_schema_columns", lambda max_issues: [schema_issue])

    def fail_if_called(max_issues):
        raise AssertionError("data checks must not run against an invalid schema")

    monkeypatch.setattr(system_status, "check_data_format", fail_if_called)
    monkeypatch.setattr(system_status, "get_release_info", lambda: {"app_version": "test"})

    result = system_status.build_system_status(include_data_checks=True, max_issues=5)

    assert result["status"] == "blocked"
    assert result["database"]["data_checks_skipped"] is True
    assert result["issues"] == [schema_issue.as_dict()]


@pytest.mark.asyncio
async def test_system_status_api_forwards_bounded_query(client, monkeypatch):
    captured = {}

    def fake_status(*, include_data_checks, max_issues):
        captured.update(
            include_data_checks=include_data_checks,
            max_issues=max_issues,
        )
        return {
            "status": "ready",
            "release": {"app_version": "test"},
            "database": {},
            "issues": [],
            "truncated": False,
        }

    monkeypatch.setattr("app.api.v1.system.build_system_status", fake_status)

    response = await client.get(
        "/api/v1/system/status?include_data_checks=true&max_issues=7"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert captured == {"include_data_checks": True, "max_issues": 7}

    invalid = await client.get("/api/v1/system/status?max_issues=201")
    assert invalid.status_code == 422
