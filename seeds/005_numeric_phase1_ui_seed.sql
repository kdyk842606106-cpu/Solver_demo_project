-- ============================================================
-- Phase 1 Numeric UI Validation Seed
-- Purpose: dedicated UI/manual validation dataset for numeric Phase 1
-- Safe to run multiple times on PostgreSQL
-- ============================================================

-- UI validation checklist:
-- 1. Start backend + frontend
-- 2. Open Solve page
-- 3. Select machine: "Numeric Phase1 UI Machine (M-NUM-UI-001)"
-- 4. Run the following targets:
--    - UI Numeric Target 40
--    - UI Numeric Mixed Target
--    - UI Numeric Unreachable Target

BEGIN;

-- ============================================================
-- 0. Cleanup old data for this dedicated dataset
-- ============================================================

DELETE FROM machine_state_feature
WHERE machine_state_id IN (
    SELECT id FROM machine_state
    WHERE machine_id IN (
        SELECT id FROM machine WHERE code = 'M-NUM-UI-001'
    )
);

DELETE FROM machine_state
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'M-NUM-UI-001'
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_UI_PRESSURIZE',
        'OP_UI_FILL_WATER',
        'OP_UI_FILL_EXACT_10',
        'OP_UI_CALIBRATE'
    )
);

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_UI_PRESSURIZE',
        'OP_UI_FILL_WATER',
        'OP_UI_FILL_EXACT_10',
        'OP_UI_CALIBRATE'
    )
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_UI_PRESSURIZE',
        'OP_UI_FILL_WATER',
        'OP_UI_FILL_EXACT_10',
        'OP_UI_CALIBRATE'
    )
);

DELETE FROM op_rule
WHERE code IN (
    'OP_UI_PRESSURIZE',
    'OP_UI_FILL_WATER',
    'OP_UI_FILL_EXACT_10',
    'OP_UI_CALIBRATE'
);

DELETE FROM resource
WHERE code IN ('TECH-NUM-UI-01', 'TECH-NUM-UI-02');

DELETE FROM machine
WHERE code = 'M-NUM-UI-001';

DELETE FROM state_feature_def
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_UI'
);

DELETE FROM machine_type
WHERE code = 'NUMERIC_PHASE1_UI';

DELETE FROM feature_definition
WHERE feature_key IN ('water_level', 'pressure');

-- ============================================================
-- 1. Global feature definitions
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('water_level', 'number', NULL, NULL, 'Water level for numeric Phase 1 UI validation'),
('pressure', 'number', NULL, NULL, 'Pressure for numeric Phase 1 UI validation')
ON CONFLICT (feature_key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    allowed_values = EXCLUDED.allowed_values,
    unit = EXCLUDED.unit,
    description = EXCLUDED.description;

-- ============================================================
-- 2. Machine type + machine
-- ============================================================

INSERT INTO machine_type (code, name, description)
VALUES ('NUMERIC_PHASE1_UI', 'Numeric Phase 1 UI Test', 'Dedicated dataset for numeric Phase 1 UI validation')
;

WITH mt AS (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_UI'
)
INSERT INTO machine (machine_type_id, code, name, location)
SELECT mt.id, 'M-NUM-UI-001', 'Numeric Phase1 UI Machine', 'UI Validation Lab'
FROM mt;

-- ============================================================
-- 3. Machine-scoped feature defs
-- ============================================================

WITH mt AS (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_UI'
)
INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
SELECT mt.id, item.feature_key, item.feature_name, item.value_type, item.allowed_values
FROM mt
CROSS JOIN (
    VALUES
        ('water_level', 'Water Level', 'number', NULL::jsonb),
        ('pressure', 'Pressure', 'number', NULL::jsonb),
        ('calibration', 'Calibration', 'enum', '["off", "on"]'::jsonb)
) AS item(feature_key, feature_name, value_type, allowed_values);

-- ============================================================
-- 4. Resources
-- ============================================================

INSERT INTO resource (machine_id, code, name, resource_type, capacity, is_available, meta) VALUES
((SELECT id FROM machine WHERE code = 'M-NUM-UI-001'), 'TECH-NUM-UI-01', 'Numeric UI Tech 01', 'NUMERIC_TECHNICIAN', 1, TRUE, NULL),
((SELECT id FROM machine WHERE code = 'M-NUM-UI-001'), 'TECH-NUM-UI-02', 'Numeric UI Tech 02', 'NUMERIC_TECHNICIAN', 1, TRUE, NULL);

-- ============================================================
-- 5. Operation rules
-- ============================================================

WITH mt AS (
    SELECT id FROM machine_type WHERE code = 'NUMERIC_PHASE1_UI'
)
INSERT INTO op_rule (machine_type_id, code, name, duration_min, description, is_active, is_repair)
SELECT mt.id, item.code, item.name, item.duration_min, item.description, TRUE, FALSE
FROM mt
CROSS JOIN (
    VALUES
        ('OP_UI_PRESSURIZE',  'UI Pressurize',   3, 'Increase pressure by 1 for implicit numeric precondition validation'),
        ('OP_UI_FILL_WATER',  'UI Fill Water',   5, 'Increase water level by 20, requires pressure >= 2'),
        ('OP_UI_FILL_EXACT_10', 'UI Fill Exact 10', 2, 'Increase water level by 10 to create an unreachable 25 target'),
        ('OP_UI_CALIBRATE',   'UI Calibrate',    8, 'Enum task used to validate mixed enum + numeric planning')
) AS item(code, name, duration_min, description);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT r.id, p.feature_key, p.operator, p.feature_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_UI_FILL_WATER', 'pressure', 'gte', '2'),
        ('OP_UI_CALIBRATE', 'calibration', 'eq', 'off')
) AS p(rule_code, feature_key, operator, feature_value)
ON p.rule_code = r.code;

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type, delta_value)
SELECT r.id, e.feature_key, e.new_value, e.effect_type, e.delta_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_UI_PRESSURIZE', 'pressure', '1', 'increment', 1.00::numeric),
        ('OP_UI_FILL_WATER', 'water_level', '1', 'increment', 20.00::numeric),
        ('OP_UI_FILL_EXACT_10', 'water_level', '1', 'increment', 10.00::numeric),
        ('OP_UI_CALIBRATE', 'calibration', 'on', 'set', NULL::numeric)
) AS e(rule_code, feature_key, new_value, effect_type, delta_value)
ON e.rule_code = r.code;

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT r.id, 'NUMERIC_TECHNICIAN', 1, TRUE
FROM op_rule r
WHERE r.code IN (
    'OP_UI_PRESSURIZE',
    'OP_UI_FILL_WATER',
    'OP_UI_FILL_EXACT_10',
    'OP_UI_CALIBRATE'
);

-- ============================================================
-- 6. States
-- ============================================================

WITH m AS (
    SELECT id FROM machine WHERE code = 'M-NUM-UI-001'
), inserted AS (
    INSERT INTO machine_state (machine_id, state_type, label)
    SELECT m.id, item.state_type, item.label
    FROM m
    CROSS JOIN (
        VALUES
            ('current', 'UI Numeric Current'),
            ('target', 'UI Numeric Target 40'),
            ('target', 'UI Numeric Mixed Target'),
            ('target', 'UI Numeric Unreachable Target')
    ) AS item(state_type, label)
    RETURNING id, label
)
INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value)
SELECT s.id, f.feature_key, f.feature_value
FROM inserted s
JOIN (
    VALUES
        ('UI Numeric Current', 'water_level', '0'),
        ('UI Numeric Current', 'pressure', '0'),
        ('UI Numeric Current', 'calibration', 'off'),

        ('UI Numeric Target 40', 'water_level', '40'),
        ('UI Numeric Target 40', 'pressure', '0'),
        ('UI Numeric Target 40', 'calibration', 'off'),

        ('UI Numeric Mixed Target', 'water_level', '40'),
        ('UI Numeric Mixed Target', 'pressure', '0'),
        ('UI Numeric Mixed Target', 'calibration', 'on'),

        ('UI Numeric Unreachable Target', 'water_level', '25'),
        ('UI Numeric Unreachable Target', 'pressure', '0'),
        ('UI Numeric Unreachable Target', 'calibration', 'off')
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
-- WHERE mt.code = 'NUMERIC_PHASE1_UI'
-- ORDER BY ms.id, mf.feature_key;
