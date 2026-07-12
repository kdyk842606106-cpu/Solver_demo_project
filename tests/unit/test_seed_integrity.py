from pathlib import Path

from scripts.load_seed_data import split_sql_statements


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_resource_upserts_match_database_unique_constraint() -> None:
    for relative_path in (
        "seeds/004_aircraft_final_assembly_seed.sql",
        "seeds/007_pump_body_integration_seed.sql",
    ):
        sql = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        resource_upsert = sql.split("INSERT INTO resource", maxsplit=1)[1].split(";", maxsplit=1)[0]
        assert "ON CONFLICT (machine_id, code) DO UPDATE SET" in resource_upsert
        assert "ON CONFLICT (code) DO UPDATE SET" not in resource_upsert


def test_seed_loader_owns_transaction_boundaries() -> None:
    statements = split_sql_statements("-- seed\nBEGIN; INSERT INTO sample VALUES (1); COMMIT;")
    assert statements == ["INSERT INTO sample VALUES (1)"]
