-- ============================================================
-- Phase 1 Numeric UI Validation Seed: Gapped Repeated Tasks
-- Purpose: validate repeated numeric tasks interrupted by replenishment tasks
-- Safe to run multiple times on PostgreSQL
-- ============================================================

-- UI validation checklist:
-- 1. Load this seed after migrations
-- 2. Start backend + frontend
-- 3. Open Solve page
-- 4. Select machine: "Numeric Phase1 Gapped UI Machine (M-NUM-GAP-001)"
-- 5. Current state: "UI Gapped Numeric Current"
-- 6. Target state: "UI Gapped Numeric Target 40"
-- Expected tasks:
--    OP_UI_CHARGE_PRESSURE x4
--    OP_UI_FILL_PULSE      x2
-- Expected logical chain:
--    CHARGE -> CHARGE -> FILL -> CHARGE -> CHARGE -> FILL

BEGIN;

-- ============================================================
-- 0. Cleanup old data for this dedicated dataset
-- ============================================================

DELETE FROM machine_state_feature
WHERE machine_state_id IN (
    SELECT id FROM machine_state
    WHERE machine_id IN (
        SELECT id FROM machine WHERE code = 'M-NUM-GAP-001'
    )
);

DELETE FROM machine_state
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'M-NUM-GAP-001'
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_UI_CHARGE_PRESSURE',
        'OP_UI_FILL_PULSE'
    )
);

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_UI_CHARGE_PRESSURE',
        'OP_UI_FILL_PULSE'
    )
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_UI_CHARGE_PRESSURE',
        'OP_UI_FILL_PULSE'
    )
);

DELETE FROM op_rule
WHERE code IN (
    'OP_UI_CHARGE_PRESSURE',
    'OP_UI_FILL_PULSE'
);

DELETE FROM resource
WHERE code IN ('TECH-NUM-GAP-01', 'TECH-NUM-GAP-02');

DELETE FROM machine
WHERE code = 'M-NUM-GAP-001';

DELETE FROM state_feature_def
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_GAPPED_UI'
);

DELETE FROM machine_type
WHERE code = 'NUMERIC_PHASE1_GAPPED_UI';

DELETE FROM feature_definition
WHERE feature_key IN ('gapped_water_level', 'gapped_pressure');

-- ============================================================
-- 1. Global feature definitions
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('gapped_water_level', 'number', NULL, NULL, 'Water level for gapped repeated numeric UI validation'),
('gapped_pressure', 'number', NULL, NULL, 'Consumable pressure for gapped repeated numeric UI validation')
ON CONFLICT (feature_key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    allowed_values = EXCLUDED.allowed_values,
    unit = EXCLUDED.unit,
    description = EXCLUDED.description;

-- ============================================================
-- 2. Machine type + machine
-- ============================================================

INSERT INTO machine_type (code, name, description)
VALUES (
    'NUMERIC_PHASE1_GAPPED_UI',
    'Numeric Phase 1 Gapped UI Test',
    'Dedicated dataset for gapped repeated numeric Phase 1 UI validation'
);

WITH mt AS (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_GAPPED_UI'
)
INSERT INTO machine (machine_type_id, code, name, location)
SELECT mt.id, 'M-NUM-GAP-001', 'Numeric Phase1 Gapped UI Machine', 'UI Validation Lab'
FROM mt;

-- ============================================================
-- 3. Machine-scoped feature defs
-- ============================================================

WITH mt AS (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_GAPPED_UI'
)
INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
SELECT mt.id, item.feature_key, item.feature_name, item.value_type, item.allowed_values
FROM mt
CROSS JOIN (
    VALUES
        ('gapped_water_level', 'Gapped Water Level', 'number', NULL::jsonb),
        ('gapped_pressure', 'Gapped Pressure', 'number', NULL::jsonb)
) AS item(feature_key, feature_name, value_type, allowed_values);

-- ============================================================
-- 4. Resources
-- ============================================================

INSERT INTO resource (code, name, resource_type, capacity, is_available, meta) VALUES
('TECH-NUM-GAP-01', 'Numeric Gapped UI Tech 01', 'NUMERIC_GAPPED_TECHNICIAN', 1, TRUE, NULL),
('TECH-NUM-GAP-02', 'Numeric Gapped UI Tech 02', 'NUMERIC_GAPPED_TECHNICIAN', 1, TRUE, NULL);

-- ============================================================
-- 5. Operation rules
-- ============================================================

WITH mt AS (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_GAPPED_UI'
)
INSERT INTO op_rule (machine_type_id, code, name, duration_min, description, is_active, is_repair)
SELECT mt.id, item.code, item.name, item.duration_min, item.description, TRUE, FALSE
FROM mt
CROSS JOIN (
    VALUES
        ('OP_UI_CHARGE_PRESSURE', 'UI Charge Pressure', 3, 'Increase consumable pressure by 1'),
        ('OP_UI_FILL_PULSE', 'UI Fill Pulse', 5, 'Increase water by 20 and consume pressure by 2')
) AS item(code, name, duration_min, description);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT r.id, p.feature_key, p.operator, p.feature_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_UI_FILL_PULSE', 'gapped_pressure', 'gte', '2')
) AS p(rule_code, feature_key, operator, feature_value)
ON p.rule_code = r.code;

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type, delta_value)
SELECT r.id, e.feature_key, e.new_value, e.effect_type, e.delta_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_UI_CHARGE_PRESSURE', 'gapped_pressure', '1', 'increment', 1.00::numeric),
        ('OP_UI_FILL_PULSE', 'gapped_water_level', '1', 'increment', 20.00::numeric),
        ('OP_UI_FILL_PULSE', 'gapped_pressure', '1', 'decrement', 2.00::numeric)
) AS e(rule_code, feature_key, new_value, effect_type, delta_value)
ON e.rule_code = r.code;

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT r.id, 'NUMERIC_GAPPED_TECHNICIAN', 1, TRUE
FROM op_rule r
WHERE r.code IN (
    'OP_UI_CHARGE_PRESSURE',
    'OP_UI_FILL_PULSE'
);

-- ============================================================
-- 6. States
-- ============================================================

WITH m AS (
    SELECT id FROM machine WHERE code = 'M-NUM-GAP-001'
), inserted AS (
    INSERT INTO machine_state (machine_id, state_type, label)
    SELECT m.id, item.state_type, item.label
    FROM m
    CROSS JOIN (
        VALUES
            ('current', 'UI Gapped Numeric Current'),
            ('target', 'UI Gapped Numeric Target 40')
    ) AS item(state_type, label)
    RETURNING id, label
)
INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value)
SELECT s.id, f.feature_key, f.feature_value
FROM inserted s
JOIN (
    VALUES
        ('UI Gapped Numeric Current', 'gapped_water_level', '0'),
        ('UI Gapped Numeric Current', 'gapped_pressure', '0'),

        ('UI Gapped Numeric Target 40', 'gapped_water_level', '40'),
        ('UI Gapped Numeric Target 40', 'gapped_pressure', '0')
) AS f(label, feature_key, feature_value)
ON f.label = s.label;

COMMIT;

-- ============================================================
-- Optional verification queries
-- ============================================================
-- SELECT mt.code, m.code, ms.id, ms.label, mf.feature_key, mf.feature_value
-- FROM machine_type mt
-- JOIN machine m ON m.machine_type_id = mt.id
-- JOIN machine_state ms ON ms.machine_id = m.id
-- JOIN machine_state_feature mf ON mf.machine_state_id = ms.id
-- WHERE mt.code = 'NUMERIC_PHASE1_GAPPED_UI'
-- ORDER BY ms.id, mf.feature_key;
