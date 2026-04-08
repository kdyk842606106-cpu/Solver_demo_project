-- ============================================================
-- Seed Data for State-Driven Process Planning System
-- MVP Demo: CNC Lathe Machine State Transition Scenario
-- ============================================================
-- 
-- Scenario: CNC Lathe needs to transition from "Cold Standby" to "Ready for Production"
-- 
-- Current State: temperature_level=cold, clean_level=dirty, calibration=off
-- Target State:  temperature_level=hot, clean_level=clean, calibration=on
-- 
-- Operations:
--   1. OP_WARMUP:    cold → hot (30 min, needs TECHNICIAN)
--   2. OP_CLEANING:  dirty → clean (20 min, needs CLEANER)
--   3. OP_CALIBRATE: off → on (15 min, needs TECHNICIAN, requires hot)
--   4. OP_COOLDOWN:  hot → cold (25 min, needs TECHNICIAN)
--   5. OP_INSPECT:   no state change (10 min, needs INSPECTOR)
-- 
-- RAG Construction:
--   - OP_WARMUP: precondition cold (satisfied by current state) → no predecessor
--   - OP_CLEANING: precondition dirty (satisfied by current state) → no predecessor
--   - OP_CALIBRATE: precondition hot (needs OP_WARMUP's effect) → depends on OP_WARMUP
--   - OP_WARMUP and OP_CLEANING can run in parallel (no mutual dependency)
-- 
-- ============================================================

-- ============================================================
-- 1. Machine Type
-- ============================================================

INSERT INTO machine_type (id, code, name, description) VALUES
(1, 'CNC_LATHE', 'CNC Lathe', 'Computer Numerical Control Lathe Machine');

-- ============================================================
-- 2. State Feature Definitions
-- ============================================================

INSERT INTO state_feature_def (id, machine_type_id, feature_key, feature_name, value_type, allowed_values) VALUES
(1, 1, 'temperature_level', 'Temperature Level', 'enum', '["cold", "warm", "hot"]'),
(2, 1, 'clean_level', 'Clean Level', 'enum', '["dirty", "clean"]'),
(3, 1, 'calibration', 'Calibration Status', 'enum', '["off", "on"]');

-- ============================================================
-- 3. Machine Instance
-- ============================================================

INSERT INTO machine (id, machine_type_id, code, name, location) VALUES
(1, 1, 'M-001', 'Main CNC Lathe', 'Workshop A');

-- ============================================================
-- 4. Machine States (Current + Target)
-- ============================================================

-- Current State: Cold Standby (cold, dirty, not calibrated)
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(1, 1, 'current', 'Cold Standby State');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(1, 'temperature_level', 'cold'),
(1, 'clean_level', 'dirty'),
(1, 'calibration', 'off');

-- Target State: Ready for Production (hot, clean, calibrated)
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(2, 1, 'target', 'Ready for Production');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(2, 'temperature_level', 'hot'),
(2, 'clean_level', 'clean'),
(2, 'calibration', 'on');

-- Target State: Hot Standby (hot, dirty, off) — only warmup needed
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(3, 1, 'target', 'Hot Standby');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(3, 'temperature_level', 'hot'),
(3, 'clean_level', 'dirty'),
(3, 'calibration', 'off');

-- Target State: Clean Standby (cold, clean, off) — only cleaning needed
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(4, 1, 'target', 'Clean Standby');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(4, 'temperature_level', 'cold'),
(4, 'clean_level', 'clean'),
(4, 'calibration', 'off');

-- Target State: Hot Clean (hot, clean, off) — warmup + cleaning parallel
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(5, 1, 'target', 'Hot Clean');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(5, 'temperature_level', 'hot'),
(5, 'clean_level', 'clean'),
(5, 'calibration', 'off');

-- Target State: Hot Calibrated (hot, dirty, on) — warmup → calibrate chain
INSERT INTO machine_state (id, machine_id, state_type, label) VALUES
(6, 1, 'target', 'Hot Calibrated');

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value) VALUES
(6, 'temperature_level', 'hot'),
(6, 'clean_level', 'dirty'),
(6, 'calibration', 'on');

-- ============================================================
-- 5. Resources (3 types)
-- ============================================================

INSERT INTO resource (id, code, name, resource_type, capacity, is_available, meta) VALUES
(1, 'TECH-01', 'Technician Alice', 'TECHNICIAN', 1, true, '{"skills": ["lathe", "mill", "calibration"]}'),
(2, 'TECH-02', 'Technician Bob', 'TECHNICIAN', 1, true, '{"skills": ["lathe", "cleaning"]}'),
(3, 'CLEAN-01', 'Cleaning Robot', 'CLEANER', 1, true, '{"type": "automated"}');

-- ============================================================
-- 6. Operation Rules (5 rules with preconditions, effects, and resource requirements)
-- ============================================================

-- OP_WARMUP: cold → hot (30 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(1, 1, 'OP_WARMUP', 'Warm Up Machine', 30, 'Heat up the machine from cold to operating temperature', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(1, 'temperature_level', 'eq', 'cold');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(1, 'temperature_level', 'hot');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(1, 'TECHNICIAN', 1, true);


-- OP_CLEANING: dirty → clean (20 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(2, 1, 'OP_CLEANING', 'Clean Machine', 20, 'Clean the machine from dirty to clean state', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(2, 'clean_level', 'eq', 'dirty');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(2, 'clean_level', 'clean');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(2, 'CLEANER', 1, true);


-- OP_CALIBRATE: off → on (15 min, requires hot)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(3, 1, 'OP_CALIBRATE', 'Calibrate Machine', 15, 'Calibrate the machine sensors and alignment', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(3, 'temperature_level', 'eq', 'hot'),
(3, 'calibration', 'eq', 'off');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(3, 'calibration', 'on');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(3, 'TECHNICIAN', 1, true);


-- OP_COOLDOWN: hot → cold (25 min)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(4, 1, 'OP_COOLDOWN', 'Cool Down Machine', 25, 'Cool down the machine from hot to cold state', true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(4, 'temperature_level', 'eq', 'hot');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value) VALUES
(4, 'temperature_level', 'cold');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(4, 'TECHNICIAN', 1, true);


-- OP_INSPECT: no state change (10 min, for testing)
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active) VALUES
(5, 1, 'OP_INSPECT', 'Inspect Machine', 10, 'Perform routine inspection without state change', true);

-- No preconditions for inspection (can be done anytime)
-- No effects for inspection (no state change)

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(5, 'TECHNICIAN', 1, true);


-- ============================================================
-- Reset Sequences (for PostgreSQL)
-- ============================================================

SELECT setval('machine_type_id_seq', (SELECT MAX(id) FROM machine_type));
SELECT setval('machine_id_seq', (SELECT MAX(id) FROM machine));
SELECT setval('state_feature_def_id_seq', (SELECT MAX(id) FROM state_feature_def));
SELECT setval('machine_state_id_seq', (SELECT MAX(id) FROM machine_state));
SELECT setval('op_rule_id_seq', (SELECT MAX(id) FROM op_rule));
SELECT setval('resource_id_seq', (SELECT MAX(id) FROM resource));
