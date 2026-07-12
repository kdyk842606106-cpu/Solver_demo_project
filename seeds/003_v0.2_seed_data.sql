-- ============================================================
-- V0.2 Seed Data: Feature Definitions + Repair Operations
-- Idempotent: safe to run multiple times
-- ============================================================

-- ============================================================
-- 1. Feature Definitions (type system)
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('temperature_level', 'enum', '["cold", "warm", "hot"]', NULL, 'Machine temperature level'),
('clean_level', 'enum', '["dirty", "clean"]', NULL, 'Machine cleanliness level'),
('calibration', 'enum', '["off", "on"]', NULL, 'Calibration status'),
('integration_status', 'enum', '["not_integrated", "integrated"]', NULL, 'Integration readiness status'),
('blockage_reason', 'enum', '["none", "hardware_fault", "pending_approval", "material_missing", "power_failure"]', NULL, 'Reason for blockage'),
('pressure_bar', 'number', NULL, 'bar', 'Hydraulic pressure reading'),
('temperature_celsius', 'number', NULL, '°C', 'Temperature in Celsius')
ON CONFLICT (feature_key) DO NOTHING;

-- ============================================================
-- 2. Repair Operations (is_repair = TRUE)
-- Uses upsert to ensure is_repair=TRUE for existing records
-- ============================================================

INSERT INTO op_rule (id, machine_type_id, code, name, duration_min, description, is_active, is_repair) VALUES
(6, 1, 'OP_REPAIR_HARDWARE', 'Repair Hardware Fault', 45, 'Repair hardware fault to restore machine operation', true, true),
(7, 1, 'OP_REPAIR_APPROVAL', 'Resolve Pending Approval', 20, 'Resolve pending approval to allow machine operation', true, true),
(8, 1, 'OP_REPAIR_MATERIAL', 'Supply Missing Material', 30, 'Supply missing material to restore operation', true, true),
(9, 1, 'OP_REPAIR_POWER', 'Restore Power Supply', 15, 'Restore power supply to enable machine operation', true, true)
ON CONFLICT (id) DO UPDATE SET
    code = EXCLUDED.code,
    name = EXCLUDED.name,
    duration_min = EXCLUDED.duration_min,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    is_repair = EXCLUDED.is_repair;

-- ============================================================
-- 3. Repair Operation Preconditions
-- ============================================================

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value) VALUES
(6, 'blockage_reason', 'eq', 'hardware_fault'),
(7, 'blockage_reason', 'eq', 'pending_approval'),
(8, 'blockage_reason', 'eq', 'material_missing'),
(9, 'blockage_reason', 'eq', 'power_failure')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 4. Repair Operation Effects
-- ============================================================

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type) VALUES
(6, 'blockage_reason', 'none', 'set'),
(7, 'blockage_reason', 'none', 'set'),
(8, 'blockage_reason', 'none', 'set'),
(9, 'blockage_reason', 'none', 'set')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 5. Repair Operation Resource Requirements
-- ============================================================

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required) VALUES
(6, 'TECHNICIAN', 1, true),
(7, 'TECHNICIAN', 1, true),
(8, 'TECHNICIAN', 1, true),
(9, 'TECHNICIAN', 1, true)
ON CONFLICT DO NOTHING;

-- ============================================================
-- 6. Add new feature definitions to state_feature_def
-- ============================================================

INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values) VALUES
(1, 'blockage_reason', 'Blockage Reason', 'enum', '["none", "hardware_fault", "pending_approval", "material_missing", "power_failure"]'),
(1, 'pressure_bar', 'Hydraulic Pressure', 'number', NULL)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Reset Sequences
-- ============================================================

SELECT setval('op_rule_id_seq', COALESCE((SELECT MAX(id) FROM op_rule), 0) + 1);
