-- ============================================================
-- Expanded Seed Data: Complete State Space + New Operations
-- ============================================================
--
-- Adds 6 new states (completing all 12 combinations of 3 features)
-- Adds 7 new operation rules (enabling transitions between any states)
-- Changes existing states to state_type='target' so all 12 are selectable
--
-- Feature space: temperature_level(cold/warm/hot) x clean_level(dirty/clean) x calibration(off/on)
-- ============================================================

-- ============================================================
-- 0. Change existing state 1 from 'current' to 'target' so it is selectable
-- ============================================================

UPDATE machine_state SET state_type = 'target', label = 'Cold Standby' WHERE id = 1;

-- ============================================================
-- 1. New Machine States (IDs 7-12) — fill the missing 6 of 12 combinations
-- ============================================================

-- State 7: cold / dirty / on
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(7, 1, 'target', 'Cold Dirty Calibrated');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(7, 'temperature_level', 'cold'),
(7, 'clean_level', 'dirty'),
(7, 'calibration', 'on');

-- State 8: cold / clean / on
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(8, 1, 'target', 'Cold Clean Calibrated');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(8, 'temperature_level', 'cold'),
(8, 'clean_level', 'clean'),
(8, 'calibration', 'on');

-- State 9: warm / dirty / off
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(9, 1, 'target', 'Warm Standby');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(9, 'temperature_level', 'warm'),
(9, 'clean_level', 'dirty'),
(9, 'calibration', 'off');

-- State 10: warm / dirty / on
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(10, 1, 'target', 'Warm Dirty Calibrated');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(10, 'temperature_level', 'warm'),
(10, 'clean_level', 'dirty'),
(10, 'calibration', 'on');

-- State 11: warm / clean / off
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(11, 1, 'target', 'Warm Clean Standby');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(11, 'temperature_level', 'warm'),
(11, 'clean_level', 'clean'),
(11, 'calibration', 'off');

-- State 12: warm / clean / on
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(12, 1, 'target', 'Warm Clean Calibrated');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(12, 'temperature_level', 'warm'),
(12, 'clean_level', 'clean'),
(12, 'calibration', 'on');

-- ============================================================
-- 2. New Operation Rules (IDs 6-12)
-- ============================================================

-- OP_PREHEAT: cold -> warm (15 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(6, 1, 'OP_PREHEAT', 'Preheat Machine', 15, 'Partially heat up machine from cold to warm', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(6, 'temperature_level', 'eq', 'cold');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(6, 'temperature_level', 'warm');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(6, 'TECHNICIAN', 1, true);


-- OP_BOOST: warm -> hot (20 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(7, 1, 'OP_BOOST', 'Boost to Hot', 20, 'Heat up machine from warm to full operating temperature', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(7, 'temperature_level', 'eq', 'warm');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(7, 'temperature_level', 'hot');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(7, 'TECHNICIAN', 1, true);


-- OP_PARTIAL_COOL: hot -> warm (15 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(8, 1, 'OP_PARTIAL_COOL', 'Partial Cool Down', 15, 'Cool down machine from hot to warm', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(8, 'temperature_level', 'eq', 'hot');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(8, 'temperature_level', 'warm');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(8, 'TECHNICIAN', 1, true);


-- OP_COOL_FROM_WARM: warm -> cold (15 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(9, 1, 'OP_COOL_FROM_WARM', 'Cool From Warm', 15, 'Cool down machine from warm to cold', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(9, 'temperature_level', 'eq', 'warm');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(9, 'temperature_level', 'cold');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(9, 'TECHNICIAN', 1, true);


-- OP_QUICK_RINSE: dirty -> clean when hot (10 min, CLEANER)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(10, 1, 'OP_QUICK_RINSE', 'Quick Rinse', 10, 'Fast cleaning when machine is hot', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(10, 'clean_level', 'eq', 'dirty'),
(10, 'temperature_level', 'eq', 'hot');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(10, 'clean_level', 'clean');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(10, 'CLEANER', 1, true);


-- OP_DECALIBRATE: on -> off (5 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(11, 1, 'OP_DECALIBRATE', 'Reset Calibration', 5, 'Reset calibration to off state', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(11, 'calibration', 'eq', 'on');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(11, 'calibration', 'off');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(11, 'TECHNICIAN', 1, true);


-- OP_WARM_CALIBRATE: warm + off -> on (25 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(12, 1, 'OP_WARM_CALIBRATE', 'Warm Calibrate', 25, 'Calibrate machine at warm temperature (slower)', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(12, 'temperature_level', 'eq', 'warm'),
(12, 'calibration', 'eq', 'off');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(12, 'calibration', 'on');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(12, 'TECHNICIAN', 1, true);


-- ============================================================
-- 3. Reset Sequences
-- ============================================================

SELECT setval('machine_state_id_seq', (SELECT MAX(id) FROM machine_state));
SELECT setval('op_rule_id_seq', (SELECT MAX(id) FROM op_rule));
