-- ============================================================
-- V0.2 Seed Data: Feature Definitions + Repair Operations
-- ============================================================

-- ============================================================
-- 1. Feature Definitions (type system)
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('temperature_level', 'enum', '["cold", "warm", "hot"]', NULL, 'Machine temperature level'),
('clean_level', 'enum', '["dirty", "clean"]', NULL, 'Machine cleanliness level'),
('calibration', 'enum', '["off", "on"]', NULL, 'Calibration status'),
('integration_status', 'enum', '["not_integrated", "integrated"]', NULL, 'Integration readiness status'),
('blockage_reason', 'enum', '["hardware_fault", "pending_approval", "material_missing", "power_failure"]', NULL, 'Reason for blockage'),
('pressure_bar', 'number', NULL, 'bar', 'Hydraulic pressure reading'),
('temperature_celsius', 'number', NULL, '°C', 'Temperature in Celsius');

-- ============================================================
-- 2. Repair Operations (is_repair = TRUE)
-- ============================================================

-- OP_REPAIR_HARDWARE: Fix hardware fault
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
(6, 1, 'OP_REPAIR_HARDWARE', 'Repair Hardware Fault', 45, 'Repair hardware fault to restore machine operation', true, true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(6, 'blockage_reason', 'eq', 'hardware_fault');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type) VALUES
(6, 'blockage_reason', 'none', 'set');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(6, 'TECHNICIAN', 1, true);


-- OP_REPAIR_APPROVAL: Pending approval resolution
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
(7, 1, 'OP_REPAIR_APPROVAL', 'Resolve Pending Approval', 20, 'Resolve pending approval to allow machine operation', true, true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(7, 'blockage_reason', 'eq', 'pending_approval');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type) VALUES
(7, 'blockage_reason', 'none', 'set');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(7, 'TECHNICIAN', 1, true);


-- OP_REPAIR_MATERIAL: Material missing resolution
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
(8, 1, 'OP_REPAIR_MATERIAL', 'Supply Missing Material', 30, 'Supply missing material to restore operation', true, true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(8, 'blockage_reason', 'eq', 'material_missing');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type) VALUES
(8, 'blockage_reason', 'none', 'set');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(8, 'TECHNICIAN', 1, true);


-- OP_REPAIR_POWER: Power failure resolution
INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
(9, 1, 'OP_REPAIR_POWER', 'Restore Power Supply', 15, 'Restore power supply to enable machine operation', true, true);

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(9, 'blockage_reason', 'eq', 'power_failure');

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type) VALUES
(9, 'blockage_reason', 'none', 'set');

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(9, 'TECHNICIAN', 1, true);

-- ============================================================
-- 3. Add new feature definitions to state_feature_def
-- ============================================================

INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values) VALUES
(1, 'blockage_reason', 'Blockage Reason', 'enum', '["hardware_fault", "pending_approval", "material_missing", "power_failure"]'),
(1, 'pressure_bar', 'Hydraulic Pressure', 'number', NULL);

-- ============================================================
-- Reset Sequences
-- ============================================================

SELECT setval('op_rule_id_seq', (SELECT MAX(id) FROM op_rule));