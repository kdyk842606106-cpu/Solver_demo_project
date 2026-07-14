"""Add the system default dual-shift work calendar.

Revision ID: 011_default_dual_shift_calendar
Revises: 010_work_calendar_scheduling
Create Date: 2026-07-13
"""

from hashlib import sha256
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011_default_dual_shift_calendar"
down_revision: Union[str, None] = "010_work_calendar_scheduling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _definition() -> tuple[list[dict], list[dict], str]:
    weekly: list[dict] = []
    for weekday in range(1, 8):
        weekly.extend([
            {
                "weekday": weekday,
                "start_time": "08:00",
                "end_time": "20:00",
                "spans_next_day": False,
                "shift_code": "DAY_SHIFT",
                "shift_name": "白班",
            },
            {
                "weekday": weekday,
                "start_time": "20:00",
                "end_time": "08:00",
                "spans_next_day": True,
                "shift_code": "NIGHT_SHIFT",
                "shift_name": "夜班",
            },
        ])
    exceptions: list[dict] = []
    payload = {
        "timezone": "Asia/Shanghai",
        "weekly_windows": weekly,
        "date_exceptions": exceptions,
    }
    checksum = sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return weekly, exceptions, checksum


def upgrade() -> None:
    op.add_column(
        "work_calendar",
        sa.Column("is_system_default", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index(
        "uq_work_calendar_single_system_default",
        "work_calendar",
        ["is_system_default"],
        unique=True,
        postgresql_where=sa.text("is_system_default"),
    )

    bind = op.get_bind()
    calendar_id = bind.execute(
        sa.text("SELECT id FROM work_calendar WHERE code = 'DEFAULT_DUAL_SHIFT'")
    ).scalar_one_or_none()
    if calendar_id is None:
        calendar_id = bind.execute(
            sa.text(
                """
                INSERT INTO work_calendar
                    (code, name, description, is_active, is_system_default)
                VALUES
                    ('DEFAULT_DUAL_SHIFT', '默认白夜双班日历',
                     '系统默认七日双班日历：白班 08:00-20:00，夜班 20:00-次日 08:00',
                     TRUE, TRUE)
                RETURNING id
                """
            )
        ).scalar_one()
    else:
        bind.execute(
            sa.text(
                """
                UPDATE work_calendar
                SET name = '默认白夜双班日历', is_active = TRUE, is_system_default = TRUE
                WHERE id = :calendar_id
                """
            ),
            {"calendar_id": calendar_id},
        )

    weekly, exceptions, checksum = _definition()
    revision_no = bind.execute(
        sa.text(
            "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM work_calendar_revision "
            "WHERE work_calendar_id = :calendar_id"
        ),
        {"calendar_id": calendar_id},
    ).scalar_one()
    revision_id = bind.execute(
        sa.text(
            """
            INSERT INTO work_calendar_revision
                (work_calendar_id, revision_no, timezone, weekly_windows,
                 date_exceptions, checksum)
            VALUES
                (:calendar_id, :revision_no, 'Asia/Shanghai',
                 CAST(:weekly AS JSONB), CAST(:exceptions AS JSONB), :checksum)
            RETURNING id
            """
        ),
        {
            "calendar_id": calendar_id,
            "revision_no": revision_no,
            "weekly": json.dumps(weekly, ensure_ascii=False),
            "exceptions": json.dumps(exceptions),
            "checksum": checksum,
        },
    ).scalar_one()
    bind.execute(
        sa.text("UPDATE work_calendar SET current_revision_id = :revision_id WHERE id = :calendar_id"),
        {"revision_id": revision_id, "calendar_id": calendar_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    calendar_id = bind.execute(
        sa.text("SELECT id FROM work_calendar WHERE code = 'DEFAULT_DUAL_SHIFT'")
    ).scalar_one_or_none()
    if calendar_id is not None:
        bind.execute(
            sa.text("UPDATE work_calendar SET current_revision_id = NULL WHERE id = :calendar_id"),
            {"calendar_id": calendar_id},
        )
        bind.execute(
            sa.text("DELETE FROM work_calendar WHERE id = :calendar_id"),
            {"calendar_id": calendar_id},
        )
    op.drop_index("uq_work_calendar_single_system_default", table_name="work_calendar")
    op.drop_column("work_calendar", "is_system_default")
