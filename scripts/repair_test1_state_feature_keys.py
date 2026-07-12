"""Repair TEST1 state feature keys that collapsed Chinese object names.

The old Network Editor tokenized concrete state objects by stripping every
non-ASCII character. That made objects such as "模块B" and "工装B" both become
`b`, and "管路" / "线路" both become `object`. This script repairs the local
TEST1 data set to use the same Unicode-safe token rule as the application.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import sync_engine


MACHINE_TYPE_ID = 10006
MACHINE_ID = 10006


def normalize_state_object_token(value: str, fallback: str = "object") -> str:
    parts: list[str] = []
    ascii_part: list[str] = []

    def flush_ascii() -> None:
        token = "".join(ascii_part).strip("_")
        if token:
            parts.append(token)
        ascii_part.clear()

    for char in str(value or "").strip().lower():
        if ("a" <= char <= "z") or ("0" <= char <= "9"):
            ascii_part.append(char)
            continue
        if char == "_" or char.isspace() or char.isascii():
            if ascii_part and ascii_part[-1] != "_":
                ascii_part.append("_")
            continue
        flush_ascii()
        parts.append(f"u{ord(char):x}")

    flush_ascii()
    token = re.sub(r"_+", "_", "_".join(parts)).strip("_")
    return token or fallback


def concrete_key(template_key: str, object_name: str) -> str:
    prefix = f"{template_key}__"
    max_object_length = max(1, 64 - len(prefix))
    object_token = normalize_state_object_token(object_name)[:max_object_length].strip("_") or "object"
    return f"{prefix}{object_token}"


@dataclass(frozen=True)
class StateRepair:
    state_node_id: int
    template_key: str
    object_name: str
    feature_name: str

    @property
    def feature_key(self) -> str:
        return concrete_key(self.template_key, self.object_name)


REPAIRS: dict[str, StateRepair] = {
    "module_a_installed": StateRepair(50, "test1_dim_0001", "模块A", "模块A / 模块安装"),
    "module_b_installed": StateRepair(51, "test1_dim_0001", "模块B", "模块B / 模块安装"),
    "module_c_installed": StateRepair(52, "test1_dim_0001", "模块C", "模块C / 模块安装"),
    "pipe_connected": StateRepair(53, "test1_dim_0002", "管路", "管路 / 管线连接"),
    "line_connected": StateRepair(54, "test1_dim_0002", "线路", "线路 / 管线连接"),
    "fixture_b_installed": StateRepair(55, "test1_dim_0001", "工装B", "工装B / 模块安装"),
    "fixture_b_removed": StateRepair(56, "test1_dim_0001", "工装B", "工装B / 模块安装"),
    "module_a_tested": StateRepair(57, "test1_dim_0003", "模块A", "模块A / 调测活动"),
    "system_power_on": StateRepair(58, "test1_dim_0004", "系统上电", "系统上电 / 其他"),
}


PRECOND_FEATURES = {
    10317: "module_a_installed",
    10318: "fixture_b_installed",
    10319: "module_a_installed",
    10320: "module_b_installed",
    10321: "module_c_installed",
    10322: "module_b_installed",
    10323: "fixture_b_installed",
    10324: "fixture_b_installed",
    10325: "system_power_on",
    10326: "module_a_installed",
    10327: "module_b_installed",
    10328: "module_c_installed",
    10329: "pipe_connected",
    10330: "line_connected",
    10332: "module_a_installed",
}

EFFECT_FEATURES = {
    10245: "module_a_installed",
    10247: "module_c_installed",
    10248: "pipe_connected",
    10249: "line_connected",
    10250: "fixture_b_installed",
    10251: "fixture_b_installed",
    10252: "module_a_tested",
    10253: "system_power_on",
    10255: "module_b_installed",
}

OLD_CONCRETE_KEYS = [
    "test1_dim_0001__a",
    "test1_dim_0001__b",
    "test1_dim_0001__c",
    "test1_dim_0002__object",
    "test1_dim_0003__a",
    "test1_dim_0004__object",
]


def update_metadata(existing: object, *, template_key: str, object_name: str) -> str:
    metadata = existing if isinstance(existing, dict) else {}
    metadata = dict(metadata)
    metadata["dimension_template_key"] = template_key
    metadata["state_object_name"] = object_name
    return json.dumps(metadata, ensure_ascii=False)


def upsert_feature_definition(conn, repair: StateRepair) -> None:
    template = conn.execute(
        text(
            """
            select feature_name, value_type, allowed_values
            from state_feature_def
            where machine_type_id = :machine_type_id and feature_key = :template_key
            """
        ),
        {"machine_type_id": MACHINE_TYPE_ID, "template_key": repair.template_key},
    ).mappings().one()
    allowed_values = json.dumps(template["allowed_values"], ensure_ascii=False)
    conn.execute(
        text(
            """
            insert into feature_definition (feature_key, value_type, allowed_values, description)
            values (:feature_key, :value_type, cast(:allowed_values as jsonb), :description)
            on conflict (feature_key) do update
            set value_type = excluded.value_type,
                allowed_values = excluded.allowed_values
            """
        ),
        {
            "feature_key": repair.feature_key,
            "value_type": template["value_type"],
            "allowed_values": allowed_values,
            "description": f"Auto-created from state dimension template '{repair.template_key}'",
        },
    )
    conn.execute(
        text(
            """
            insert into state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
            values (:machine_type_id, :feature_key, :feature_name, :value_type, cast(:allowed_values as jsonb))
            on conflict (machine_type_id, feature_key) do update
            set feature_name = excluded.feature_name,
                value_type = excluded.value_type,
                allowed_values = excluded.allowed_values
            """
        ),
        {
            "machine_type_id": MACHINE_TYPE_ID,
            "feature_key": repair.feature_key,
            "feature_name": repair.feature_name,
            "value_type": template["value_type"],
            "allowed_values": allowed_values,
        },
    )


def upsert_machine_state_feature(conn, state_id: int, feature_key: str, feature_value: str) -> None:
    conn.execute(
        text(
            """
            insert into machine_state_feature (machine_state_id, feature_key, feature_value)
            values (:state_id, :feature_key, :feature_value)
            on conflict (machine_state_id, feature_key) do update
            set feature_value = excluded.feature_value
            """
        ),
        {"state_id": state_id, "feature_key": feature_key, "feature_value": feature_value},
    )


def old_key_still_referenced(conn, old_key: str) -> bool:
    checks = [
        ("state_node", "feature_key"),
        ("op_rule_precond", "feature_key"),
        ("op_rule_effect", "feature_key"),
        ("machine_state_feature", "feature_key"),
    ]
    for table, column in checks:
        count = conn.execute(
            text(f"select count(*) from {table} where {column} = :feature_key"),
            {"feature_key": old_key},
        ).scalar_one()
        if count:
            return True
    return False


def main() -> None:
    with sync_engine.begin() as conn:
        machine_type = conn.execute(
            text("select id from machine_type where id = :machine_type_id"),
            {"machine_type_id": MACHINE_TYPE_ID},
        ).scalar_one_or_none()
        if machine_type is None:
            raise RuntimeError(f"machine_type {MACHINE_TYPE_ID} not found")

        for repair in REPAIRS.values():
            upsert_feature_definition(conn, repair)

        for repair in REPAIRS.values():
            row = conn.execute(
                text("select metadata_json from state_node where id = :state_node_id"),
                {"state_node_id": repair.state_node_id},
            ).mappings().one()
            conn.execute(
                text(
                    """
                    update state_node
                    set feature_key = :feature_key,
                        metadata_json = cast(:metadata_json as jsonb)
                    where id = :state_node_id
                    """
                ),
                {
                    "state_node_id": repair.state_node_id,
                    "feature_key": repair.feature_key,
                    "metadata_json": update_metadata(
                        row["metadata_json"],
                        template_key=repair.template_key,
                        object_name=repair.object_name,
                    ),
                },
            )

        for precond_id, repair_name in PRECOND_FEATURES.items():
            conn.execute(
                text("update op_rule_precond set feature_key = :feature_key where id = :id"),
                {"id": precond_id, "feature_key": REPAIRS[repair_name].feature_key},
            )
        for effect_id, repair_name in EFFECT_FEATURES.items():
            conn.execute(
                text("update op_rule_effect set feature_key = :feature_key where id = :id"),
                {"id": effect_id, "feature_key": REPAIRS[repair_name].feature_key},
            )

        machine_state_rows = conn.execute(
            text(
                """
                select ms.id, ms.state_type, f.feature_key, f.feature_value
                from machine_state ms
                join machine_state_feature f on f.machine_state_id = ms.id
                where ms.machine_id = :machine_id
                """
            ),
            {"machine_id": MACHINE_ID},
        ).mappings().all()
        old_values: dict[tuple[int, str], str] = {
            (row["id"], row["feature_key"]): row["feature_value"] for row in machine_state_rows
        }
        for row in machine_state_rows:
            state_id = row["id"]
            old_key = row["feature_key"]
            replacement_name = {
                "test1_dim_0001__a": "module_a_installed",
                "test1_dim_0001__b": "module_b_installed",
                "test1_dim_0001__c": "module_c_installed",
                "test1_dim_0002__object": "pipe_connected",
                "test1_dim_0003__a": "module_a_tested",
                "test1_dim_0004__object": "system_power_on",
            }.get(old_key)
            if replacement_name is None:
                continue
            upsert_machine_state_feature(
                conn,
                state_id,
                REPAIRS[replacement_name].feature_key,
                row["feature_value"],
            )
            conn.execute(
                text("delete from machine_state_feature where machine_state_id = :state_id and feature_key = :old_key"),
                {"state_id": state_id, "old_key": old_key},
            )

        refreshed_rows = conn.execute(
            text(
                """
                select ms.id, ms.state_type, f.feature_key, f.feature_value
                from machine_state ms
                join machine_state_feature f on f.machine_state_id = ms.id
                where ms.machine_id = :machine_id
                """
            ),
            {"machine_id": MACHINE_ID},
        ).mappings().all()
        states = {row["id"] for row in refreshed_rows}
        for state_id in states:
            old_b_value = old_values.get((state_id, "test1_dim_0001__b"), "未安装")
            old_pipe_value = old_values.get((state_id, "test1_dim_0002__object"), "未连接")
            upsert_machine_state_feature(
                conn,
                state_id,
                REPAIRS["fixture_b_installed"].feature_key,
                "未安装" if old_b_value == "已安装" else old_b_value,
            )
            upsert_machine_state_feature(
                conn,
                state_id,
                REPAIRS["line_connected"].feature_key,
                old_pipe_value,
            )

        for old_key in OLD_CONCRETE_KEYS:
            if old_key_still_referenced(conn, old_key):
                continue
            conn.execute(
                text(
                    "delete from state_feature_def where machine_type_id = :machine_type_id and feature_key = :feature_key"
                ),
                {"machine_type_id": MACHINE_TYPE_ID, "feature_key": old_key},
            )
            conn.execute(
                text("delete from feature_definition where feature_key = :feature_key"),
                {"feature_key": old_key},
            )

    print("TEST1 state feature key repair completed")


if __name__ == "__main__":
    main()
