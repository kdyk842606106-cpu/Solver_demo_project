-- ============================================================
-- Aircraft Final Assembly Demo Seed (IDs >= 10000)
-- Idempotent: safe to run multiple times before/after solving.
-- This seed mirrors the previous aircraft final-assembly demo line and
-- includes multi-resource requirements for scheduler validation.
-- ============================================================

-- ============================================================
-- 1) Feature definitions
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('afa_prep_done', 'enum', '["false", "true"]'::jsonb, NULL, 'Aircraft final assembly preparation status'),
('afa_fuselage_joined', 'enum', '["false", "true"]'::jsonb, NULL, 'Fuselage section join status'),
('afa_wing_qa_done', 'enum', '["false", "true"]'::jsonb, NULL, 'Wing arrival QA status'),
('afa_wing_joined', 'enum', '["false", "true"]'::jsonb, NULL, 'Wing join status'),
('afa_engine_mounted', 'enum', '["false", "true"]'::jsonb, NULL, 'Engine mount status'),
('afa_avionics_rack_installed', 'enum', '["false", "true"]'::jsonb, NULL, 'Avionics rack installation status'),
('afa_hyd_pipe_installed', 'enum', '["false", "true"]'::jsonb, NULL, 'Hydraulic pipe installation status'),
('afa_avionics_ready', 'enum', '["false", "true"]'::jsonb, NULL, 'Avionics loading status'),
('afa_engine_lines_connected', 'enum', '["false", "true"]'::jsonb, NULL, 'Engine line connection status'),
('afa_power_check', 'enum', '["false", "true"]'::jsonb, NULL, 'Aircraft power check status'),
('afa_ground_test', 'enum', '["false", "true"]'::jsonb, NULL, 'Ground function test status'),
('afa_delivery_ready', 'enum', '["false", "true"]'::jsonb, NULL, 'Delivery readiness status'),
('blockage_reason', 'enum', '["none", "seal_rework", "engine_alignment_fault", "avionics_bus_fault", "hydraulic_leak", "sensor_wiring_error", "power_unit_failure"]'::jsonb, NULL, 'Reason for blockage')
ON CONFLICT (feature_key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    allowed_values = EXCLUDED.allowed_values,
    unit = EXCLUDED.unit,
    description = EXCLUDED.description;

DELETE FROM feature_definition WHERE feature_key = 'afa_blockage_reason';

-- ============================================================
-- 2) Machine type and machine-specific feature definitions
-- ============================================================

INSERT INTO machine_type (id, code, name, description) VALUES
(10000, 'AIRCRAFT_FINAL_ASSEMBLY_10000', 'Aircraft Final Assembly Demo Line', 'Aircraft final assembly demo line with multi-resource scheduling data')
ON CONFLICT (id) DO UPDATE SET
    code = EXCLUDED.code,
    name = EXCLUDED.name,
    description = EXCLUDED.description;

DELETE FROM state_feature_def WHERE machine_type_id = 10000;

INSERT INTO state_feature_def (id, machine_type_id, feature_key, feature_name, value_type, allowed_values) VALUES
(10000, 10000, 'afa_prep_done', 'Preparation Done', 'enum', '["false", "true"]'::jsonb),
(10001, 10000, 'afa_fuselage_joined', 'Fuselage Joined', 'enum', '["false", "true"]'::jsonb),
(10002, 10000, 'afa_wing_qa_done', 'Wing QA Done', 'enum', '["false", "true"]'::jsonb),
(10003, 10000, 'afa_wing_joined', 'Wing Joined', 'enum', '["false", "true"]'::jsonb),
(10004, 10000, 'afa_engine_mounted', 'Engine Mounted', 'enum', '["false", "true"]'::jsonb),
(10005, 10000, 'afa_avionics_rack_installed', 'Avionics Rack Installed', 'enum', '["false", "true"]'::jsonb),
(10006, 10000, 'afa_hyd_pipe_installed', 'Hydraulic Pipe Installed', 'enum', '["false", "true"]'::jsonb),
(10007, 10000, 'afa_avionics_ready', 'Avionics Ready', 'enum', '["false", "true"]'::jsonb),
(10008, 10000, 'afa_engine_lines_connected', 'Engine Lines Connected', 'enum', '["false", "true"]'::jsonb),
(10009, 10000, 'afa_power_check', 'Power Check', 'enum', '["false", "true"]'::jsonb),
(10010, 10000, 'afa_ground_test', 'Ground Function Test', 'enum', '["false", "true"]'::jsonb),
(10011, 10000, 'afa_delivery_ready', 'Delivery Ready', 'enum', '["false", "true"]'::jsonb),
(10012, 10000, 'blockage_reason', 'Blockage Reason', 'enum', '["none", "seal_rework"]'::jsonb)
ON CONFLICT (id) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    feature_key = EXCLUDED.feature_key,
    feature_name = EXCLUDED.feature_name,
    value_type = EXCLUDED.value_type,
    allowed_values = EXCLUDED.allowed_values;

-- ============================================================
-- 3) Machine instance and states
-- ============================================================

INSERT INTO machine (id, machine_type_id, code, name, location) VALUES
(10000, 10000, 'AFA-DEMO-10000', 'Aircraft Final Assembly Station 10000', 'Final Assembly Hall A')
ON CONFLICT (id) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    code = EXCLUDED.code,
    name = EXCLUDED.name,
    location = EXCLUDED.location;

INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(10000, 10000, 'current', 'Aircraft final assembly start state'),
(10001, 10000, 'target', 'Aircraft final assembly delivery-ready target')
ON CONFLICT (id) DO UPDATE SET
    machine_id = EXCLUDED.machine_id,
    state_type = EXCLUDED.state_type,
    label = EXCLUDED.label;

DELETE FROM machine_state_feature WHERE machine_state_id IN (10000, 10001);

INSERT INTO machine_state_feature (id, machine_state_id, feature_key, feature_value) VALUES
(10000, 10000, 'afa_prep_done', 'false'),
(10001, 10000, 'afa_fuselage_joined', 'false'),
(10002, 10000, 'afa_wing_qa_done', 'false'),
(10003, 10000, 'afa_wing_joined', 'false'),
(10004, 10000, 'afa_engine_mounted', 'false'),
(10005, 10000, 'afa_avionics_rack_installed', 'false'),
(10006, 10000, 'afa_hyd_pipe_installed', 'false'),
(10007, 10000, 'afa_avionics_ready', 'false'),
(10008, 10000, 'afa_engine_lines_connected', 'false'),
(10009, 10000, 'afa_power_check', 'false'),
(10010, 10000, 'afa_ground_test', 'false'),
(10011, 10000, 'afa_delivery_ready', 'false'),
(10012, 10000, 'blockage_reason', 'none'),
(10013, 10001, 'afa_prep_done', 'true'),
(10014, 10001, 'afa_fuselage_joined', 'true'),
(10015, 10001, 'afa_wing_qa_done', 'true'),
(10016, 10001, 'afa_wing_joined', 'true'),
(10017, 10001, 'afa_engine_mounted', 'true'),
(10018, 10001, 'afa_avionics_rack_installed', 'true'),
(10019, 10001, 'afa_hyd_pipe_installed', 'true'),
(10020, 10001, 'afa_avionics_ready', 'true'),
(10021, 10001, 'afa_engine_lines_connected', 'true'),
(10022, 10001, 'afa_power_check', 'true'),
(10023, 10001, 'afa_ground_test', 'true'),
(10024, 10001, 'afa_delivery_ready', 'true'),
(10025, 10001, 'blockage_reason', 'none')
ON CONFLICT (id) DO UPDATE SET
    machine_state_id = EXCLUDED.machine_state_id,
    feature_key = EXCLUDED.feature_key,
    feature_value = EXCLUDED.feature_value;

-- ============================================================
-- 4) Resources
-- ============================================================

INSERT INTO resource (id, machine_id, code, name, resource_type, capacity, is_available, meta) VALUES
(10000, 10000, 'BODY-TEAM-10000', 'Body assembly team', 'AFA_ASSEMBLY_TEAM', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10001, 10000, 'AVIONICS-10000', 'Avionics team', 'AFA_AVIONICS_TEAM', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10002, 10000, 'HYD-10000', 'Hydraulic team', 'AFA_HYDRAULIC_TEAM', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10003, 10000, 'POWER-10000', 'Power assembly team', 'AFA_POWER_TEAM', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10004, 10000, 'CRANE-10000', 'Final assembly crane', 'AFA_CRANE', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10005, 10000, 'QA-10000', 'Final assembly QA inspector', 'AFA_QA', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10006, 10000, 'SPACE-BODY-JOIN-10000', 'Body join workspace', 'AFA_SPACE_BODY_JOIN', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10007, 10000, 'SPACE-WING-ROOT-10000', 'Wing root workspace', 'AFA_SPACE_WING_ROOT', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10008, 10000, 'SPACE-AVIONICS-BAY-10000', 'Avionics bay workspace', 'AFA_SPACE_AVIONICS_BAY', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10009, 10000, 'SPACE-ENGINE-PYLON-10000', 'Engine pylon workspace', 'AFA_SPACE_ENGINE_PYLON', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10010, 10000, 'SPACE-HYD-BAY-10000', 'Hydraulic bay workspace', 'AFA_SPACE_HYD_BAY', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb),
(10011, 10000, 'SPACE-FINAL-TEST-10000', 'Final test workspace', 'AFA_SPACE_FINAL_TEST', 1, true, '{"line":"aircraft_final_assembly"}'::jsonb)
ON CONFLICT (id) DO UPDATE SET
    code = EXCLUDED.code,
    machine_id = EXCLUDED.machine_id,
    name = EXCLUDED.name,
    resource_type = EXCLUDED.resource_type,
    capacity = EXCLUDED.capacity,
    is_available = EXCLUDED.is_available,
    meta = EXCLUDED.meta;

-- ============================================================
-- 5) Operation rules
-- ============================================================

INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
(10000, 10000, 'A_PREP', 'Fuselage section join preparation', 480, 'Prepare aircraft body sections for final assembly', true, false),
(10001, 10000, 'B_JOIN_FUSELAGE', 'Join front center rear fuselage', 1440, 'Join major fuselage sections', true, false),
(10002, 10000, 'C_WING_QA', 'Wing arrival QA', 960, 'Inspect wing assemblies before joining', true, false),
(10003, 10000, 'D_JOIN_WING', 'Join wing assemblies', 1440, 'Join wing assemblies to fuselage', true, false),
(10004, 10000, 'E_ENGINE_MOUNT', 'Mount engine', 960, 'Mount engine module on pylon', true, false),
(10005, 10000, 'F_AVIONICS_RACK', 'Install avionics rack', 960, 'Install avionics rack in forward bay', true, false),
(10006, 10000, 'G_HYD_PIPE', 'Lay hydraulic pipes', 1440, 'Install hydraulic pipe routes', true, false),
(10007, 10000, 'H_AVIONICS_LOAD', 'Load avionics equipment', 1440, 'Load and connect avionics equipment', true, false),
(10008, 10000, 'I_ENGINE_LINES', 'Connect engine lines', 960, 'Connect engine power and fluid lines', true, false),
(10009, 10000, 'J_POWER_CHECK', 'Whole-aircraft power check', 960, 'Run whole-aircraft power check', true, false),
(10010, 10000, 'K_GROUND_TEST', 'Ground function test', 960, 'Run ground function test', true, false),
(10011, 10000, 'L_DELIVERY_QA', 'Final delivery QA', 480, 'Final delivery readiness inspection', true, false),
(10012, 10000, 'X_SEAL_REWORK', 'Fuselage seal rework', 960, 'Repair fuselage seal issue after blockage', true, true)
ON CONFLICT (id) DO UPDATE SET
    machine_type_id = EXCLUDED.machine_type_id,
    code = EXCLUDED.code,
    name = EXCLUDED.name,
    duration_min = EXCLUDED.duration_min,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    is_repair = EXCLUDED.is_repair;

DELETE FROM op_rule_precond WHERE op_rule_id BETWEEN 10000 AND 10012;
DELETE FROM op_rule_effect WHERE op_rule_id BETWEEN 10000 AND 10012;
DELETE FROM op_rule_resource_req WHERE op_rule_id BETWEEN 10000 AND 10012;

INSERT INTO op_rule_precond (id, op_rule_id, feature_key, operator, feature_value) VALUES
(10000, 10000, 'afa_prep_done', 'eq', 'false'),
(10001, 10001, 'afa_prep_done', 'eq', 'true'),
(10002, 10001, 'afa_fuselage_joined', 'eq', 'false'),
(10003, 10002, 'afa_prep_done', 'eq', 'true'),
(10004, 10002, 'afa_wing_qa_done', 'eq', 'false'),
(10005, 10003, 'afa_fuselage_joined', 'eq', 'true'),
(10006, 10003, 'afa_wing_qa_done', 'eq', 'true'),
(10007, 10003, 'afa_wing_joined', 'eq', 'false'),
(10008, 10004, 'afa_wing_joined', 'eq', 'true'),
(10009, 10004, 'afa_engine_mounted', 'eq', 'false'),
(10010, 10005, 'afa_wing_joined', 'eq', 'true'),
(10011, 10005, 'afa_avionics_rack_installed', 'eq', 'false'),
(10012, 10006, 'afa_wing_joined', 'eq', 'true'),
(10013, 10006, 'afa_hyd_pipe_installed', 'eq', 'false'),
(10014, 10007, 'afa_avionics_rack_installed', 'eq', 'true'),
(10015, 10007, 'afa_avionics_ready', 'eq', 'false'),
(10016, 10008, 'afa_engine_mounted', 'eq', 'true'),
(10017, 10008, 'afa_hyd_pipe_installed', 'eq', 'true'),
(10018, 10008, 'afa_engine_lines_connected', 'eq', 'false'),
(10019, 10009, 'afa_avionics_ready', 'eq', 'true'),
(10020, 10009, 'afa_engine_lines_connected', 'eq', 'true'),
(10021, 10009, 'afa_power_check', 'eq', 'false'),
(10022, 10010, 'afa_power_check', 'eq', 'true'),
(10023, 10010, 'afa_ground_test', 'eq', 'false'),
(10024, 10011, 'afa_ground_test', 'eq', 'true'),
(10025, 10011, 'afa_delivery_ready', 'eq', 'false'),
(10026, 10012, 'blockage_reason', 'eq', 'seal_rework');

INSERT INTO op_rule_effect (id, op_rule_id, feature_key, new_value, effect_type) VALUES
(10000, 10000, 'afa_prep_done', 'true', 'set'),
(10001, 10001, 'afa_fuselage_joined', 'true', 'set'),
(10002, 10002, 'afa_wing_qa_done', 'true', 'set'),
(10003, 10003, 'afa_wing_joined', 'true', 'set'),
(10004, 10004, 'afa_engine_mounted', 'true', 'set'),
(10005, 10005, 'afa_avionics_rack_installed', 'true', 'set'),
(10006, 10006, 'afa_hyd_pipe_installed', 'true', 'set'),
(10007, 10007, 'afa_avionics_ready', 'true', 'set'),
(10008, 10008, 'afa_engine_lines_connected', 'true', 'set'),
(10009, 10009, 'afa_power_check', 'true', 'set'),
(10010, 10010, 'afa_ground_test', 'true', 'set'),
(10011, 10011, 'afa_delivery_ready', 'true', 'set'),
(10012, 10012, 'blockage_reason', 'none', 'set');

INSERT INTO op_rule_resource_req (id, op_rule_id, resource_type, quantity, is_required) VALUES
(10000, 10000, 'AFA_ASSEMBLY_TEAM', 1, true),
(10001, 10000, 'AFA_SPACE_BODY_JOIN', 1, true),
(10002, 10001, 'AFA_ASSEMBLY_TEAM', 1, true),
(10003, 10001, 'AFA_SPACE_BODY_JOIN', 1, true),
(10004, 10002, 'AFA_QA', 1, true),
(10005, 10003, 'AFA_ASSEMBLY_TEAM', 1, true),
(10006, 10003, 'AFA_CRANE', 1, true),
(10007, 10003, 'AFA_SPACE_WING_ROOT', 1, true),
(10008, 10004, 'AFA_POWER_TEAM', 1, true),
(10009, 10004, 'AFA_CRANE', 1, true),
(10010, 10004, 'AFA_SPACE_ENGINE_PYLON', 1, true),
(10011, 10005, 'AFA_ASSEMBLY_TEAM', 1, true),
(10012, 10005, 'AFA_SPACE_AVIONICS_BAY', 1, true),
(10013, 10006, 'AFA_HYDRAULIC_TEAM', 1, true),
(10014, 10006, 'AFA_SPACE_HYD_BAY', 1, true),
(10015, 10007, 'AFA_AVIONICS_TEAM', 1, true),
(10016, 10007, 'AFA_SPACE_AVIONICS_BAY', 1, true),
(10017, 10008, 'AFA_POWER_TEAM', 1, true),
(10018, 10008, 'AFA_SPACE_ENGINE_PYLON', 1, true),
(10019, 10009, 'AFA_AVIONICS_TEAM', 1, true),
(10020, 10009, 'AFA_QA', 1, true),
(10021, 10009, 'AFA_SPACE_FINAL_TEST', 1, true),
(10022, 10010, 'AFA_AVIONICS_TEAM', 1, true),
(10023, 10010, 'AFA_HYDRAULIC_TEAM', 1, true),
(10024, 10010, 'AFA_SPACE_FINAL_TEST', 1, true),
(10025, 10011, 'AFA_QA', 1, true),
(10026, 10011, 'AFA_SPACE_FINAL_TEST', 1, true),
(10027, 10012, 'AFA_ASSEMBLY_TEAM', 1, true),
(10028, 10012, 'AFA_QA', 1, true),
(10029, 10012, 'AFA_SPACE_AVIONICS_BAY', 1, true);

-- ============================================================
-- 6) Keep sequences above seeded IDs
-- ============================================================

SELECT setval('machine_type_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM machine_type), 1), 10000));
SELECT setval('machine_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM machine), 1), 10000));
SELECT setval('state_feature_def_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM state_feature_def), 1), 10012));
SELECT setval('machine_state_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM machine_state), 1), 10001));
SELECT setval('machine_state_feature_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM machine_state_feature), 1), 10025));
SELECT setval('resource_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM resource), 1), 10011));
SELECT setval('op_rule_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM op_rule), 1), 10012));
SELECT setval('op_rule_precond_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_precond), 1), 10026));
SELECT setval('op_rule_effect_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_effect), 1), 10012));
SELECT setval('op_rule_resource_req_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_resource_req), 1), 10029));
