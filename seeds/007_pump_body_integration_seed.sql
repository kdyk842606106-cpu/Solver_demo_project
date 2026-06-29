-- ============================================================
-- V0.2 Seed Data: Pump Body Mechanical Integration Scenario
-- Idempotent: safe to run multiple times
-- Includes normal assembly + repair operations
-- Cleanliness constraint: enum generation chain ensures two
--   cleaning steps are inserted by the Planner.
-- ============================================================

BEGIN;

-- ============================================================
-- 0) Idempotent cleanup for pump seed
-- ============================================================

DELETE FROM machine_state_feature
WHERE machine_state_id IN (
    SELECT id FROM machine_state
    WHERE machine_id IN (
        SELECT id FROM machine WHERE code = 'PMP-BDY-001'
    )
);

DELETE FROM machine_state
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'PMP-BDY-001'
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code LIKE 'OP_PMP_%'
);

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code LIKE 'OP_PMP_%'
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code LIKE 'OP_PMP_%'
);

DELETE FROM op_rule
WHERE code LIKE 'OP_PMP_%';

DELETE FROM resource
WHERE code LIKE 'PMP-%';

DELETE FROM machine
WHERE code = 'PMP-BDY-001';

DELETE FROM state_feature_def
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'
);

DELETE FROM machine_type
WHERE code = 'PUMP_BODY_INTEGRATION';

DELETE FROM feature_definition
WHERE feature_key LIKE 'pump_%';

-- ============================================================
-- 1) Feature Definitions (system-level)
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('pump_casing_status', 'enum', '["pending", "installed"]', NULL, 'Pump casing installation status'),
('pump_impeller_status', 'enum', '["pending", "installed"]', NULL, 'Pump impeller installation status'),
('pump_shaft_status', 'enum', '["pending", "installed"]', NULL, 'Pump shaft assembly installation status'),
('pump_seal_status', 'enum', '["pending", "installed"]', NULL, 'Pump mechanical seal installation status'),
('pump_bearing_status', 'enum', '["pending", "installed"]', NULL, 'Pump bearing housing installation status'),
('pump_coupling_status', 'enum', '["pending", "installed"]', NULL, 'Pump drive coupling installation status'),
('pump_cooling_jacket_status', 'enum', '["pending", "installed"]', NULL, 'Pump cooling jacket installation status'),
('pump_vibration_sensor_status', 'enum', '["pending", "installed"]', NULL, 'Pump vibration sensor installation status'),
('pump_lubrication_line_status', 'enum', '["pending", "connected"]', NULL, 'Pump lubrication line connection status'),
('pump_cleanliness_generation', 'enum', '["gen_0", "gen_1", "gen_2"]', NULL, 'Chamber cleanliness generation: gen_0=initial, gen_1=after first clean, gen_2=after second clean'),
('pump_integration_test_status', 'enum', '["pending", "passed"]', NULL, 'Pump final integration test status'),
('pump_blockage_reason', 'enum', '["none", "seal_misalignment", "bearing_overheat", "coupling_runout", "cooling_leak", "sensor_wiring_error"]', NULL, 'Reason for blockage')
ON CONFLICT (feature_key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    allowed_values = EXCLUDED.allowed_values,
    unit = EXCLUDED.unit,
    description = EXCLUDED.description;

-- ============================================================
-- 2) Machine Type + State Feature Definitions
-- ============================================================

INSERT INTO machine_type (code, name, description) VALUES
('PUMP_BODY_INTEGRATION', 'Pump Body Mechanical Integration Cell', 'Pump body mechanical integration scenario with cleanliness and resource constraints')
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description;

DELETE FROM state_feature_def
WHERE machine_type_id = (SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION')
  AND feature_key LIKE 'pump_%';

INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
SELECT
    mt.id,
    v.feature_key,
    v.feature_name,
    v.value_type,
    v.allowed_values::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('pump_casing_status', 'Pump Casing Status', 'enum', '["pending", "installed"]'),
      ('pump_impeller_status', 'Pump Impeller Status', 'enum', '["pending", "installed"]'),
      ('pump_shaft_status', 'Pump Shaft Status', 'enum', '["pending", "installed"]'),
      ('pump_seal_status', 'Pump Seal Status', 'enum', '["pending", "installed"]'),
      ('pump_bearing_status', 'Pump Bearing Status', 'enum', '["pending", "installed"]'),
      ('pump_coupling_status', 'Pump Coupling Status', 'enum', '["pending", "installed"]'),
      ('pump_cooling_jacket_status', 'Cooling Jacket Status', 'enum', '["pending", "installed"]'),
      ('pump_vibration_sensor_status', 'Vibration Sensor Status', 'enum', '["pending", "installed"]'),
      ('pump_lubrication_line_status', 'Lubrication Line Status', 'enum', '["pending", "connected"]'),
      ('pump_cleanliness_generation', 'Chamber Cleanliness Generation', 'enum', '["gen_0", "gen_1", "gen_2"]'),
      ('pump_integration_test_status', 'Integration Test Status', 'enum', '["pending", "passed"]'),
      ('pump_blockage_reason', 'Blockage Reason', 'enum', '["none", "seal_misalignment", "bearing_overheat", "coupling_runout", "cooling_leak", "sensor_wiring_error"]')
) AS v(feature_key, feature_name, value_type, allowed_values)
WHERE mt.code = 'PUMP_BODY_INTEGRATION';

-- ============================================================
-- 3) Machine Instance + State Definitions
-- ============================================================

INSERT INTO machine (code, machine_type_id, name, location) VALUES
(
    'PMP-BDY-001',
    (SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'),
    'Pump Body Assembly Station #1',
    'Workshop B - Precision Assembly Line'
)
ON CONFLICT (code) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    name = EXCLUDED.name,
    location = EXCLUDED.location;

INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(
    8101,
    (SELECT id FROM machine WHERE code = 'PMP-BDY-001'),
    'current',
    'Pump Body Assembly Start State'
),
(
    8102,
    (SELECT id FROM machine WHERE code = 'PMP-BDY-001'),
    'target',
    'Pump Body Assembly Ready for Delivery'
)
ON CONFLICT (id) DO UPDATE SET
    machine_id = EXCLUDED.machine_id,
    state_type = EXCLUDED.state_type,
    label = EXCLUDED.label;

DELETE FROM machine_state_feature WHERE machine_state_id IN (8101, 8102);

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
-- Current state: all pending, cleanliness gen_0
(8101, 'pump_casing_status', 'pending'),
(8101, 'pump_impeller_status', 'pending'),
(8101, 'pump_shaft_status', 'pending'),
(8101, 'pump_seal_status', 'pending'),
(8101, 'pump_bearing_status', 'pending'),
(8101, 'pump_coupling_status', 'pending'),
(8101, 'pump_cooling_jacket_status', 'pending'),
(8101, 'pump_vibration_sensor_status', 'pending'),
(8101, 'pump_lubrication_line_status', 'pending'),
(8101, 'pump_cleanliness_generation', 'gen_0'),
(8101, 'pump_integration_test_status', 'pending'),
(8101, 'pump_blockage_reason', 'none'),
-- Target state: all installed/connected/passed, cleanliness gen_2
(8102, 'pump_casing_status', 'installed'),
(8102, 'pump_impeller_status', 'installed'),
(8102, 'pump_shaft_status', 'installed'),
(8102, 'pump_seal_status', 'installed'),
(8102, 'pump_bearing_status', 'installed'),
(8102, 'pump_coupling_status', 'installed'),
(8102, 'pump_cooling_jacket_status', 'installed'),
(8102, 'pump_vibration_sensor_status', 'installed'),
(8102, 'pump_lubrication_line_status', 'connected'),
(8102, 'pump_cleanliness_generation', 'gen_2'),
(8102, 'pump_integration_test_status', 'passed'),
(8102, 'pump_blockage_reason', 'none');

-- ============================================================
-- 4) Resource Definitions
-- ============================================================

INSERT INTO resource (machine_id, code, name, resource_type, capacity, is_available, meta) VALUES
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-MEA-01', 'Pump Mechanical Team A', 'PUMP_MECH_TEAM_A', 1, true, '{"skill":"casing_impeller_bearing"}'),
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-MEB-01', 'Pump Mechanical Team B', 'PUMP_MECH_TEAM_B', 1, true, '{"skill":"shaft_seal_coupling"}'),
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-PRS-01', 'Pump Precision Instrument Team', 'PUMP_PRECISION_TEAM', 1, true, '{"skill":"sensor_integration_test"}'),
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-COL-01', 'Pump Cooling System Tech', 'PUMP_COOLING_TECH', 1, true, '{"skill":"cooling_lubrication"}'),
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-CLN-01', 'Pump Chamber Cleaning Crew', 'PUMP_CLEANING_CREW', 1, true, '{"skill":"chamber_cleaning"}'),
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-QA-01', 'Pump QA Inspector', 'PUMP_QA_INSPECTOR', 1, true, '{"skill":"final_test"}'),
((SELECT id FROM machine WHERE code = 'PMP-BDY-001'), 'PMP-RPR-01', 'Pump Repair Team', 'PUMP_REPAIR_TEAM', 1, true, '{"skill":"fault_recovery"}')
ON CONFLICT (code) DO UPDATE SET
    machine_id = EXCLUDED.machine_id,
    name = EXCLUDED.name,
    resource_type = EXCLUDED.resource_type,
    capacity = EXCLUDED.capacity,
    is_available = EXCLUDED.is_available,
    meta = EXCLUDED.meta;

-- ============================================================
-- 5) Operation Rules (normal + repair)
--    Normal >= 10, Repair >= 5
-- ============================================================

INSERT INTO op_rule (machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
-- Main line normal operations (9)
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_810_INSTALL_CASING', 'Install Pump Casing', 90, 'Main line: install pump outer casing frame', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_820_INSTALL_IMPELLER', 'Install Impeller', 75, 'Main line: install impeller after casing', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_830_INSTALL_SHAFT', 'Install Shaft Assembly', 85, 'Main line: install shaft assembly after impeller', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_835_CLEAN_CHAMBER_FIRST', 'First Chamber Cleaning', 40, 'Main line gate: clean chamber after shaft assembly', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_840_INSTALL_SEAL', 'Install Mechanical Seal', 70, 'Main line precision step: install mechanical seal after first clean', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_850_INSTALL_BEARING', 'Install Bearing Housing', 80, 'Main line: install bearing housing after seal', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_855_CLEAN_CHAMBER_SECOND', 'Second Chamber Cleaning', 40, 'Main line gate: second clean after coupling before test', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_860_INSTALL_COUPLING', 'Install Drive Coupling', 60, 'Main line: install drive coupling after bearing', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_890_INTEGRATION_TEST', 'Final Integration Test', 50, 'Main line final step: full integration acceptance test', true, false),
-- Branch normal operations (3)
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_870_INSTALL_COOLING', 'Install Cooling Jacket', 55, 'Branch: install cooling jacket after casing', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_880_INSTALL_VIBRATION', 'Install Vibration Sensor', 35, 'Branch: install vibration sensor after impeller', true, false),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_885_CONNECT_LUBRICATION', 'Connect Lubrication Lines', 45, 'Branch: connect lubrication lines after bearing', true, false),
-- Repair operations (5)
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_9R0_REPAIR_SEAL', 'Repair Seal Misalignment', 50, 'Repair seal misalignment fault when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_9R1_REPAIR_BEARING', 'Repair Bearing Overheat', 60, 'Repair bearing overheating fault when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_9R2_REPAIR_COUPLING', 'Repair Coupling Runout', 45, 'Repair coupling runout fault when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_9R3_REPAIR_COOLING', 'Repair Cooling Leak', 40, 'Repair cooling system leak when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'PUMP_BODY_INTEGRATION'), 'OP_PMP_9R4_REPAIR_SENSOR', 'Repair Sensor Wiring Error', 30, 'Repair sensor wiring error when blocked', true, true)
ON CONFLICT (code) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    name = EXCLUDED.name,
    duration_min = EXCLUDED.duration_min,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    is_repair = EXCLUDED.is_repair;

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code LIKE 'OP_PMP_%'
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code LIKE 'OP_PMP_%'
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code LIKE 'OP_PMP_%'
);

-- ============================================================
-- 6) Preconditions
-- ============================================================

-- Main line preconditions
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_casing_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_810_INSTALL_CASING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_casing_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_820_INSTALL_IMPELLER';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_impeller_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_820_INSTALL_IMPELLER';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_impeller_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_830_INSTALL_SHAFT';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_shaft_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_830_INSTALL_SHAFT';

-- Clean 1: requires shaft installed (to place it after shaft) and gen_0 (to prevent it appearing after later cleans)
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_shaft_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_835_CLEAN_CHAMBER_FIRST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cleanliness_generation', 'eq', 'gen_0' FROM op_rule WHERE code = 'OP_PMP_835_CLEAN_CHAMBER_FIRST';

-- Seal: precision assembly, requires gen_1 (clean environment after first clean)
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_shaft_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_840_INSTALL_SEAL';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_seal_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_840_INSTALL_SEAL';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cleanliness_generation', 'eq', 'gen_1' FROM op_rule WHERE code = 'OP_PMP_840_INSTALL_SEAL';

-- Bearing: precision assembly, requires gen_1
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_seal_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_850_INSTALL_BEARING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_bearing_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_850_INSTALL_BEARING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cleanliness_generation', 'eq', 'gen_1' FROM op_rule WHERE code = 'OP_PMP_850_INSTALL_BEARING';

-- Coupling: requires gen_1
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_bearing_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_860_INSTALL_COUPLING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_coupling_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_860_INSTALL_COUPLING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cleanliness_generation', 'eq', 'gen_1' FROM op_rule WHERE code = 'OP_PMP_860_INSTALL_COUPLING';

-- Clean 2: requires coupling installed and gen_1
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_coupling_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_855_CLEAN_CHAMBER_SECOND';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cleanliness_generation', 'eq', 'gen_1' FROM op_rule WHERE code = 'OP_PMP_855_CLEAN_CHAMBER_SECOND';

-- Integration test: requires all major components + gen_2 (clean environment for test)
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_coupling_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cooling_jacket_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_vibration_sensor_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_lubrication_line_status', 'eq', 'connected' FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cleanliness_generation', 'eq', 'gen_2' FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_integration_test_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';

-- Branch preconditions
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_casing_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_870_INSTALL_COOLING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_cooling_jacket_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_870_INSTALL_COOLING';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_impeller_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_880_INSTALL_VIBRATION';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_vibration_sensor_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_880_INSTALL_VIBRATION';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_bearing_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_PMP_885_CONNECT_LUBRICATION';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_lubrication_line_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_PMP_885_CONNECT_LUBRICATION';

-- Repair preconditions
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_blockage_reason', 'eq', 'seal_misalignment' FROM op_rule WHERE code = 'OP_PMP_9R0_REPAIR_SEAL';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_blockage_reason', 'eq', 'bearing_overheat' FROM op_rule WHERE code = 'OP_PMP_9R1_REPAIR_BEARING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_blockage_reason', 'eq', 'coupling_runout' FROM op_rule WHERE code = 'OP_PMP_9R2_REPAIR_COUPLING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_blockage_reason', 'eq', 'cooling_leak' FROM op_rule WHERE code = 'OP_PMP_9R3_REPAIR_COOLING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'pump_blockage_reason', 'eq', 'sensor_wiring_error' FROM op_rule WHERE code = 'OP_PMP_9R4_REPAIR_SENSOR';

-- ============================================================
-- 7) Effects
-- ============================================================

-- Main line: set installed status + advance cleanliness generation
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type, delta_value)
SELECT r.id, e.feature_key, e.new_value, e.effect_type, e.delta_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_PMP_810_INSTALL_CASING', 'pump_casing_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_820_INSTALL_IMPELLER', 'pump_impeller_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_830_INSTALL_SHAFT', 'pump_shaft_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_835_CLEAN_CHAMBER_FIRST', 'pump_cleanliness_generation', 'gen_1', 'set', NULL::numeric),
        ('OP_PMP_840_INSTALL_SEAL', 'pump_seal_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_850_INSTALL_BEARING', 'pump_bearing_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_860_INSTALL_COUPLING', 'pump_coupling_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_855_CLEAN_CHAMBER_SECOND', 'pump_cleanliness_generation', 'gen_2', 'set', NULL::numeric),
        ('OP_PMP_890_INTEGRATION_TEST', 'pump_integration_test_status', 'passed', 'set', NULL::numeric)
) AS e(rule_code, feature_key, new_value, effect_type, delta_value)
ON e.rule_code = r.code;

-- Branch: set installed/connected status (no cleanliness impact)
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type, delta_value)
SELECT r.id, e.feature_key, e.new_value, e.effect_type, e.delta_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_PMP_870_INSTALL_COOLING', 'pump_cooling_jacket_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_880_INSTALL_VIBRATION', 'pump_vibration_sensor_status', 'installed', 'set', NULL::numeric),
        ('OP_PMP_885_CONNECT_LUBRICATION', 'pump_lubrication_line_status', 'connected', 'set', NULL::numeric)
) AS e(rule_code, feature_key, new_value, effect_type, delta_value)
ON e.rule_code = r.code;

-- Repair: clear blockage_reason
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type, delta_value)
SELECT r.id, e.feature_key, e.new_value, e.effect_type, e.delta_value
FROM op_rule r
JOIN (
    VALUES
        ('OP_PMP_9R0_REPAIR_SEAL', 'pump_blockage_reason', 'none', 'set', NULL::numeric),
        ('OP_PMP_9R1_REPAIR_BEARING', 'pump_blockage_reason', 'none', 'set', NULL::numeric),
        ('OP_PMP_9R2_REPAIR_COUPLING', 'pump_blockage_reason', 'none', 'set', NULL::numeric),
        ('OP_PMP_9R3_REPAIR_COOLING', 'pump_blockage_reason', 'none', 'set', NULL::numeric),
        ('OP_PMP_9R4_REPAIR_SENSOR', 'pump_blockage_reason', 'none', 'set', NULL::numeric)
) AS e(rule_code, feature_key, new_value, effect_type, delta_value)
ON e.rule_code = r.code;

-- ============================================================
-- 8) Resource Requirements
-- ============================================================

-- Main line resources
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_MECH_TEAM_A', 1, true FROM op_rule WHERE code = 'OP_PMP_810_INSTALL_CASING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_MECH_TEAM_A', 1, true FROM op_rule WHERE code = 'OP_PMP_820_INSTALL_IMPELLER';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_MECH_TEAM_B', 1, true FROM op_rule WHERE code = 'OP_PMP_830_INSTALL_SHAFT';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_CLEANING_CREW', 1, true FROM op_rule WHERE code = 'OP_PMP_835_CLEAN_CHAMBER_FIRST';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_MECH_TEAM_B', 1, true FROM op_rule WHERE code = 'OP_PMP_840_INSTALL_SEAL';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_MECH_TEAM_A', 1, true FROM op_rule WHERE code = 'OP_PMP_850_INSTALL_BEARING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_CLEANING_CREW', 1, true FROM op_rule WHERE code = 'OP_PMP_855_CLEAN_CHAMBER_SECOND';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_MECH_TEAM_B', 1, true FROM op_rule WHERE code = 'OP_PMP_860_INSTALL_COUPLING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_QA_INSPECTOR', 1, true FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_PRECISION_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_890_INTEGRATION_TEST';

-- Branch resources
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_COOLING_TECH', 1, true FROM op_rule WHERE code = 'OP_PMP_870_INSTALL_COOLING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_PRECISION_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_880_INSTALL_VIBRATION';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_COOLING_TECH', 1, true FROM op_rule WHERE code = 'OP_PMP_885_CONNECT_LUBRICATION';

-- Repair resources
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_9R0_REPAIR_SEAL';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_9R1_REPAIR_BEARING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_9R2_REPAIR_COUPLING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_9R3_REPAIR_COOLING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'PUMP_REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_PMP_9R4_REPAIR_SENSOR';

-- ============================================================
-- 9) Reset Sequences
-- ============================================================

SELECT setval('machine_type_id_seq', COALESCE((SELECT MAX(id) FROM machine_type), 1));
SELECT setval('machine_id_seq', COALESCE((SELECT MAX(id) FROM machine), 1));
SELECT setval('state_feature_def_id_seq', COALESCE((SELECT MAX(id) FROM state_feature_def), 1));
SELECT setval('machine_state_id_seq', COALESCE((SELECT MAX(id) FROM machine_state), 1));
SELECT setval('resource_id_seq', COALESCE((SELECT MAX(id) FROM resource), 1));
SELECT setval('op_rule_id_seq', COALESCE((SELECT MAX(id) FROM op_rule), 1));

COMMIT;

-- ============================================================
-- Optional verification queries
-- ============================================================
-- SELECT mt.code, m.code, ms.id, ms.label, mf.feature_key, mf.feature_value
-- FROM machine_type mt
-- JOIN machine m ON m.machine_type_id = mt.id
-- JOIN machine_state ms ON ms.machine_id = m.id
-- JOIN machine_state_feature mf ON mf.machine_state_id = ms.id
-- WHERE mt.code = 'PUMP_BODY_INTEGRATION'
-- ORDER BY ms.id, mf.feature_key;
--
-- SELECT r.code, r.name, r.duration_min, r.is_repair,
--        COUNT(DISTINCT p.id) AS preconds,
--        COUNT(DISTINCT e.id) AS effects,
--        COUNT(DISTINCT rq.id) AS resources
-- FROM op_rule r
-- LEFT JOIN op_rule_precond p ON p.op_rule_id = r.id
-- LEFT JOIN op_rule_effect e ON e.op_rule_id = r.id
-- LEFT JOIN op_rule_resource_req rq ON rq.op_rule_id = r.id
-- WHERE r.code LIKE 'OP_PMP_%'
-- GROUP BY r.id, r.code, r.name, r.duration_min, r.is_repair
-- ORDER BY r.code;
