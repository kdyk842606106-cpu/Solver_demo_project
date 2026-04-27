-- ============================================================
-- V0.2 Seed Data: Aircraft Final Assembly Integration Scenario
-- Idempotent: safe to run multiple times
-- Includes normal assembly + repair operations
-- ============================================================

BEGIN;

-- ============================================================
-- 1) Feature Definitions (system-level)
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('fuselage_status', 'enum', '["pending", "installed"]', NULL, 'Fuselage installation status'),
('left_wing_status', 'enum', '["pending", "installed"]', NULL, 'Left wing installation status'),
('right_wing_status', 'enum', '["pending", "installed"]', NULL, 'Right wing installation status'),
('engine_status', 'enum', '["pending", "installed"]', NULL, 'Engine installation status'),
('avionics_status', 'enum', '["pending", "installed"]', NULL, 'Avionics hardware installation status'),
('avionics_program_status', 'enum', '["pending", "done"]', NULL, 'Avionics software programming status'),
('landing_gear_status', 'enum', '["pending", "installed"]', NULL, 'Landing gear installation status'),
('fuel_line_status', 'enum', '["pending", "connected"]', NULL, 'Fuel line connection status'),
('hydraulic_status', 'enum', '["pending", "calibrated"]', NULL, 'Hydraulic calibration status'),
('power_status', 'enum', '["pending", "ready"]', NULL, 'Power-on readiness status'),
('integration_test_status', 'enum', '["pending", "passed"]', NULL, 'Integration test status'),
('blockage_reason', 'enum', '["none", "engine_alignment_fault", "avionics_bus_fault", "hydraulic_leak", "sensor_wiring_error", "power_unit_failure"]', NULL, 'Reason for blockage')
ON CONFLICT (feature_key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    allowed_values = EXCLUDED.allowed_values,
    unit = EXCLUDED.unit,
    description = EXCLUDED.description;

-- ============================================================
-- 2) Machine Type + State Feature Definitions
-- ============================================================

INSERT INTO machine_type (code, name, description) VALUES
('AIRCRAFT_FINAL_ASSEMBLY', 'Aircraft Final Assembly Cell', 'Aircraft final assembly mechanical integration scenario')
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description;

DELETE FROM state_feature_def
WHERE machine_type_id = (SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY')
  AND feature_key IN (
      'fuselage_status',
      'left_wing_status',
      'right_wing_status',
      'engine_status',
      'avionics_status',
      'avionics_program_status',
      'landing_gear_status',
      'fuel_line_status',
      'hydraulic_status',
      'power_status',
      'integration_test_status',
      'blockage_reason'
  );

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
      ('fuselage_status', 'Fuselage Status', 'enum', '["pending", "installed"]'),
      ('left_wing_status', 'Left Wing Status', 'enum', '["pending", "installed"]'),
      ('right_wing_status', 'Right Wing Status', 'enum', '["pending", "installed"]'),
      ('engine_status', 'Engine Status', 'enum', '["pending", "installed"]'),
      ('avionics_status', 'Avionics Status', 'enum', '["pending", "installed"]'),
      ('avionics_program_status', 'Avionics Program Status', 'enum', '["pending", "done"]'),
      ('landing_gear_status', 'Landing Gear Status', 'enum', '["pending", "installed"]'),
      ('fuel_line_status', 'Fuel Line Status', 'enum', '["pending", "connected"]'),
      ('hydraulic_status', 'Hydraulic Status', 'enum', '["pending", "calibrated"]'),
      ('power_status', 'Power Status', 'enum', '["pending", "ready"]'),
      ('integration_test_status', 'Integration Test Status', 'enum', '["pending", "passed"]'),
      ('blockage_reason', 'Blockage Reason', 'enum', '["none", "engine_alignment_fault", "avionics_bus_fault", "hydraulic_leak", "sensor_wiring_error", "power_unit_failure"]')
) AS v(feature_key, feature_name, value_type, allowed_values)
WHERE mt.code = 'AIRCRAFT_FINAL_ASSEMBLY';

-- ============================================================
-- 3) Machine Instance + State Definitions
-- ============================================================

INSERT INTO machine (code, machine_type_id, name, location) VALUES
(
    'AFA-001',
    (SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'),
    'Aircraft Assembly Station #1',
    'Hangar A - Final Assembly Line'
)
ON CONFLICT (code) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    name = EXCLUDED.name,
    location = EXCLUDED.location;

INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(
    2001,
    (SELECT id FROM machine WHERE code = 'AFA-001'),
    'current',
    'Aircraft Assembly Start State'
),
(
    2002,
    (SELECT id FROM machine WHERE code = 'AFA-001'),
    'target',
    'Aircraft Assembly Ready for Delivery'
)
ON CONFLICT (id) DO UPDATE SET
    machine_id = EXCLUDED.machine_id,
    state_type = EXCLUDED.state_type,
    label = EXCLUDED.label;

DELETE FROM machine_state_feature WHERE machine_state_id IN (2001, 2002);

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
-- Current state
(2001, 'fuselage_status', 'pending'),
(2001, 'left_wing_status', 'pending'),
(2001, 'right_wing_status', 'pending'),
(2001, 'engine_status', 'pending'),
(2001, 'avionics_status', 'pending'),
(2001, 'avionics_program_status', 'pending'),
(2001, 'landing_gear_status', 'pending'),
(2001, 'fuel_line_status', 'pending'),
(2001, 'hydraulic_status', 'pending'),
(2001, 'power_status', 'pending'),
(2001, 'integration_test_status', 'pending'),
(2001, 'blockage_reason', 'none'),
-- Target state
(2002, 'fuselage_status', 'installed'),
(2002, 'left_wing_status', 'installed'),
(2002, 'right_wing_status', 'installed'),
(2002, 'engine_status', 'installed'),
(2002, 'avionics_status', 'installed'),
(2002, 'avionics_program_status', 'done'),
(2002, 'landing_gear_status', 'installed'),
(2002, 'fuel_line_status', 'connected'),
(2002, 'hydraulic_status', 'calibrated'),
(2002, 'power_status', 'ready'),
(2002, 'integration_test_status', 'passed'),
(2002, 'blockage_reason', 'none');

-- ============================================================
-- 4) Resource Definitions
-- ============================================================

INSERT INTO resource (code, name, resource_type, capacity, is_available, meta) VALUES
('AF-STR-01', 'Structure Team A', 'STRUCTURE_TEAM', 1, true, '{"skill":"fuselage_wing_install"}'),
('AF-ENG-01', 'Engine Team A', 'ENGINE_TEAM', 1, true, '{"skill":"engine_mount"}'),
('AF-AVI-01', 'Avionics Team A', 'AVIONICS_TEAM', 1, true, '{"skill":"avionics_install_program"}'),
('AF-HYD-01', 'Hydraulic Team A', 'HYDRAULIC_TEAM', 1, true, '{"skill":"hydraulic_landing_gear"}'),
('AF-QA-01', 'QA Inspector A', 'QA_INSPECTOR', 1, true, '{"skill":"integration_test"}'),
('AF-RPR-01', 'Repair Team A', 'REPAIR_TEAM', 1, true, '{"skill":"fault_recovery"}')
ON CONFLICT (code) DO UPDATE SET
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
-- Main line + branch normal operations (11)
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INSTALL_FUSELAGE', 'Install Fuselage Frame', 120, 'Main line start: install fuselage frame', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INSTALL_ENGINE', 'Install Engine Module', 90, 'Main line: install engine after fuselage', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_CONNECT_FUEL_LINE', 'Connect Fuel Line', 45, 'Main line: connect fuel lines after engine install', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INSTALL_LEFT_WING', 'Install Left Wing', 80, 'Parallel branch: left wing installation', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INSTALL_RIGHT_WING', 'Install Right Wing', 80, 'Parallel branch: right wing installation', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INSTALL_AVIONICS', 'Install Avionics Hardware', 70, 'Branch: avionics hardware installation', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_PROGRAM_AVIONICS', 'Program Avionics Software', 60, 'Branch: avionics software programming', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INSTALL_LANDING_GEAR', 'Install Landing Gear', 75, 'Parallel branch: landing gear installation', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_CALIBRATE_HYDRAULIC', 'Calibrate Hydraulic System', 40, 'Branch merge prep: hydraulic calibration', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_POWER_ON_CHECK', 'Power-On Readiness Check', 30, 'Main line to final test: verify power readiness', true, false),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_INTEGRATION_TEST', 'Run Final Integration Test', 50, 'Main line final step: full integration acceptance', true, false),
-- Repair operations (5)
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_REPAIR_ENGINE_ALIGNMENT', 'Repair Engine Alignment Fault', 55, 'Repair engine alignment fault when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_REPAIR_AVIONICS_BUS', 'Repair Avionics Bus Fault', 45, 'Repair avionics data bus fault when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_REPAIR_HYDRAULIC_LEAK', 'Repair Hydraulic Leak', 60, 'Repair hydraulic leakage when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_REPAIR_SENSOR_WIRING', 'Repair Sensor Wiring Error', 35, 'Repair sensor wiring issue when blocked', true, true),
((SELECT id FROM machine_type WHERE code = 'AIRCRAFT_FINAL_ASSEMBLY'), 'OP_AIR_REPAIR_POWER_UNIT', 'Repair Power Unit Failure', 50, 'Repair power unit failure when blocked', true, true)
ON CONFLICT (code) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    name = EXCLUDED.name,
    duration_min = EXCLUDED.duration_min,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    is_repair = EXCLUDED.is_repair;

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_AIR_INSTALL_FUSELAGE',
        'OP_AIR_INSTALL_ENGINE',
        'OP_AIR_CONNECT_FUEL_LINE',
        'OP_AIR_INSTALL_LEFT_WING',
        'OP_AIR_INSTALL_RIGHT_WING',
        'OP_AIR_INSTALL_AVIONICS',
        'OP_AIR_PROGRAM_AVIONICS',
        'OP_AIR_INSTALL_LANDING_GEAR',
        'OP_AIR_CALIBRATE_HYDRAULIC',
        'OP_AIR_POWER_ON_CHECK',
        'OP_AIR_INTEGRATION_TEST',
        'OP_AIR_REPAIR_ENGINE_ALIGNMENT',
        'OP_AIR_REPAIR_AVIONICS_BUS',
        'OP_AIR_REPAIR_HYDRAULIC_LEAK',
        'OP_AIR_REPAIR_SENSOR_WIRING',
        'OP_AIR_REPAIR_POWER_UNIT'
    )
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_AIR_INSTALL_FUSELAGE',
        'OP_AIR_INSTALL_ENGINE',
        'OP_AIR_CONNECT_FUEL_LINE',
        'OP_AIR_INSTALL_LEFT_WING',
        'OP_AIR_INSTALL_RIGHT_WING',
        'OP_AIR_INSTALL_AVIONICS',
        'OP_AIR_PROGRAM_AVIONICS',
        'OP_AIR_INSTALL_LANDING_GEAR',
        'OP_AIR_CALIBRATE_HYDRAULIC',
        'OP_AIR_POWER_ON_CHECK',
        'OP_AIR_INTEGRATION_TEST',
        'OP_AIR_REPAIR_ENGINE_ALIGNMENT',
        'OP_AIR_REPAIR_AVIONICS_BUS',
        'OP_AIR_REPAIR_HYDRAULIC_LEAK',
        'OP_AIR_REPAIR_SENSOR_WIRING',
        'OP_AIR_REPAIR_POWER_UNIT'
    )
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT id FROM op_rule WHERE code IN (
        'OP_AIR_INSTALL_FUSELAGE',
        'OP_AIR_INSTALL_ENGINE',
        'OP_AIR_CONNECT_FUEL_LINE',
        'OP_AIR_INSTALL_LEFT_WING',
        'OP_AIR_INSTALL_RIGHT_WING',
        'OP_AIR_INSTALL_AVIONICS',
        'OP_AIR_PROGRAM_AVIONICS',
        'OP_AIR_INSTALL_LANDING_GEAR',
        'OP_AIR_CALIBRATE_HYDRAULIC',
        'OP_AIR_POWER_ON_CHECK',
        'OP_AIR_INTEGRATION_TEST',
        'OP_AIR_REPAIR_ENGINE_ALIGNMENT',
        'OP_AIR_REPAIR_AVIONICS_BUS',
        'OP_AIR_REPAIR_HYDRAULIC_LEAK',
        'OP_AIR_REPAIR_SENSOR_WIRING',
        'OP_AIR_REPAIR_POWER_UNIT'
    )
);

-- Preconditions
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuselage_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INSTALL_FUSELAGE';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuselage_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INSTALL_ENGINE';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'engine_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INSTALL_ENGINE';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'engine_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_CONNECT_FUEL_LINE';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuel_line_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_CONNECT_FUEL_LINE';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuselage_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INSTALL_LEFT_WING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'left_wing_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INSTALL_LEFT_WING';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuselage_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INSTALL_RIGHT_WING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'right_wing_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INSTALL_RIGHT_WING';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuselage_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INSTALL_AVIONICS';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'avionics_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INSTALL_AVIONICS';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'avionics_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_PROGRAM_AVIONICS';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'avionics_program_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_PROGRAM_AVIONICS';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuselage_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INSTALL_LANDING_GEAR';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'landing_gear_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INSTALL_LANDING_GEAR';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'landing_gear_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_CALIBRATE_HYDRAULIC';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'hydraulic_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_CALIBRATE_HYDRAULIC';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'fuel_line_status', 'eq', 'connected' FROM op_rule WHERE code = 'OP_AIR_POWER_ON_CHECK';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'avionics_program_status', 'eq', 'done' FROM op_rule WHERE code = 'OP_AIR_POWER_ON_CHECK';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'hydraulic_status', 'eq', 'calibrated' FROM op_rule WHERE code = 'OP_AIR_POWER_ON_CHECK';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'power_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_POWER_ON_CHECK';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'engine_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'left_wing_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'right_wing_status', 'eq', 'installed' FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'power_status', 'eq', 'ready' FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'integration_test_status', 'eq', 'pending' FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'blockage_reason', 'eq', 'engine_alignment_fault' FROM op_rule WHERE code = 'OP_AIR_REPAIR_ENGINE_ALIGNMENT';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'blockage_reason', 'eq', 'avionics_bus_fault' FROM op_rule WHERE code = 'OP_AIR_REPAIR_AVIONICS_BUS';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'blockage_reason', 'eq', 'hydraulic_leak' FROM op_rule WHERE code = 'OP_AIR_REPAIR_HYDRAULIC_LEAK';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'blockage_reason', 'eq', 'sensor_wiring_error' FROM op_rule WHERE code = 'OP_AIR_REPAIR_SENSOR_WIRING';
INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT id, 'blockage_reason', 'eq', 'power_unit_failure' FROM op_rule WHERE code = 'OP_AIR_REPAIR_POWER_UNIT';

-- Effects
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'fuselage_status', 'installed', 'set' FROM op_rule WHERE code = 'OP_AIR_INSTALL_FUSELAGE';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'engine_status', 'installed', 'set' FROM op_rule WHERE code = 'OP_AIR_INSTALL_ENGINE';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'fuel_line_status', 'connected', 'set' FROM op_rule WHERE code = 'OP_AIR_CONNECT_FUEL_LINE';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'left_wing_status', 'installed', 'set' FROM op_rule WHERE code = 'OP_AIR_INSTALL_LEFT_WING';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'right_wing_status', 'installed', 'set' FROM op_rule WHERE code = 'OP_AIR_INSTALL_RIGHT_WING';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'avionics_status', 'installed', 'set' FROM op_rule WHERE code = 'OP_AIR_INSTALL_AVIONICS';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'avionics_program_status', 'done', 'set' FROM op_rule WHERE code = 'OP_AIR_PROGRAM_AVIONICS';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'landing_gear_status', 'installed', 'set' FROM op_rule WHERE code = 'OP_AIR_INSTALL_LANDING_GEAR';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'hydraulic_status', 'calibrated', 'set' FROM op_rule WHERE code = 'OP_AIR_CALIBRATE_HYDRAULIC';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'power_status', 'ready', 'set' FROM op_rule WHERE code = 'OP_AIR_POWER_ON_CHECK';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'integration_test_status', 'passed', 'set' FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'blockage_reason', 'none', 'set' FROM op_rule WHERE code = 'OP_AIR_REPAIR_ENGINE_ALIGNMENT';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'blockage_reason', 'none', 'set' FROM op_rule WHERE code = 'OP_AIR_REPAIR_AVIONICS_BUS';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'blockage_reason', 'none', 'set' FROM op_rule WHERE code = 'OP_AIR_REPAIR_HYDRAULIC_LEAK';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'blockage_reason', 'none', 'set' FROM op_rule WHERE code = 'OP_AIR_REPAIR_SENSOR_WIRING';
INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT id, 'blockage_reason', 'none', 'set' FROM op_rule WHERE code = 'OP_AIR_REPAIR_POWER_UNIT';

-- Resource requirements
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'STRUCTURE_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_INSTALL_FUSELAGE';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'ENGINE_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_INSTALL_ENGINE';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'ENGINE_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_CONNECT_FUEL_LINE';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'STRUCTURE_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_INSTALL_LEFT_WING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'STRUCTURE_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_INSTALL_RIGHT_WING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'AVIONICS_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_INSTALL_AVIONICS';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'AVIONICS_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_PROGRAM_AVIONICS';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'HYDRAULIC_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_INSTALL_LANDING_GEAR';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'HYDRAULIC_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_CALIBRATE_HYDRAULIC';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'QA_INSPECTOR', 1, true FROM op_rule WHERE code = 'OP_AIR_POWER_ON_CHECK';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'QA_INSPECTOR', 1, true FROM op_rule WHERE code = 'OP_AIR_INTEGRATION_TEST';

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_REPAIR_ENGINE_ALIGNMENT';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_REPAIR_AVIONICS_BUS';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_REPAIR_HYDRAULIC_LEAK';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_REPAIR_SENSOR_WIRING';
INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT id, 'REPAIR_TEAM', 1, true FROM op_rule WHERE code = 'OP_AIR_REPAIR_POWER_UNIT';

-- ============================================================
-- 6) Reset Sequences
-- ============================================================

SELECT setval('machine_type_id_seq', COALESCE((SELECT MAX(id) FROM machine_type), 1));
SELECT setval('machine_id_seq', COALESCE((SELECT MAX(id) FROM machine), 1));
SELECT setval('state_feature_def_id_seq', COALESCE((SELECT MAX(id) FROM state_feature_def), 1));
SELECT setval('machine_state_id_seq', COALESCE((SELECT MAX(id) FROM machine_state), 1));
SELECT setval('resource_id_seq', COALESCE((SELECT MAX(id) FROM resource), 1));
SELECT setval('op_rule_id_seq', COALESCE((SELECT MAX(id) FROM op_rule), 1));

COMMIT;
