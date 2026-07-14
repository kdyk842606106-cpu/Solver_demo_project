-- ============================================================
-- Mechanical Integration State Continuity Seed
-- Idempotent: rerunning this file replaces only this validation dataset.
--
-- Dataset:
--   machine type: MECH_INTEGRATION_CONTINUITY
--   machine:      MI-CONT-001
--
-- Purpose:
--   Validate state-package continuity scheduling with a mechanical integration
--   business shape. The top target package has two child state packages and four
--   independent mechanical tasks share one resource so the continuity soft
--   objectives can compact tasks by target state package.
-- ============================================================

-- ============================================================
-- 0) Clean previous validation rows
-- ============================================================

DELETE FROM activity_state_binding
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM maintenance_intent_template
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM schedule_result
WHERE solve_request_id IN (
    SELECT sr.id
    FROM solve_request sr
    JOIN machine m ON m.id = sr.machine_id
    WHERE m.code = 'MI-CONT-001'
);

DELETE FROM candidate_plan_step
WHERE candidate_plan_id IN (
    SELECT cp.id
    FROM candidate_plan cp
    JOIN solve_request sr ON sr.id = cp.solve_request_id
    JOIN machine m ON m.id = sr.machine_id
    WHERE m.code = 'MI-CONT-001'
);

DELETE FROM candidate_plan
WHERE solve_request_id IN (
    SELECT sr.id
    FROM solve_request sr
    JOIN machine m ON m.id = sr.machine_id
    WHERE m.code = 'MI-CONT-001'
);

DELETE FROM solve_request
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'MI-CONT-001'
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM op_rule
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM activity_package_atomic_ref
WHERE activity_node_id IN (
    SELECT an.id
    FROM activity_node an
    JOIN machine_type mt ON mt.id = an.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
)
OR atomic_activity_id IN (
    SELECT aa.id
    FROM atomic_activity aa
    JOIN machine_type mt ON mt.id = aa.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM state_node_reference
WHERE state_node_id IN (
    SELECT sn.id
    FROM state_node sn
    JOIN machine_type mt ON mt.id = sn.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
)
OR parent_state_node_id IN (
    SELECT sn.id
    FROM state_node sn
    JOIN machine_type mt ON mt.id = sn.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM atomic_activity
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM activity_node
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM state_node
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM machine_state_feature
WHERE machine_state_id IN (
    SELECT ms.id
    FROM machine_state ms
    JOIN machine m ON m.id = ms.machine_id
    WHERE m.code = 'MI-CONT-001'
);

DELETE FROM machine_state
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'MI-CONT-001'
);

DELETE FROM resource
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'MI-CONT-001'
);

DELETE FROM machine
WHERE code = 'MI-CONT-001'
OR machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM state_feature_def
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_CONTINUITY'
);

DELETE FROM machine_type
WHERE code = 'MECH_INTEGRATION_CONTINUITY';

DELETE FROM feature_definition
WHERE feature_key LIKE 'mechint_%';

-- ============================================================
-- 1) Feature definitions
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('mechint_base_frame_status', 'enum', '["pending", "installed"]'::jsonb, NULL, 'Base frame installation status'),
('mechint_column_alignment_status', 'enum', '["pending", "aligned"]'::jsonb, NULL, 'Column alignment status'),
('mechint_atmospheric_arm_status', 'enum', '["pending", "installed"]'::jsonb, NULL, 'Atmospheric arm installation status'),
('mechint_vacuum_arm_status', 'enum', '["pending", "installed"]'::jsonb, NULL, 'Vacuum arm installation status');

INSERT INTO machine_type (code, name, description, scheduling_config) VALUES
(
    'MECH_INTEGRATION_CONTINUITY',
    'Mechanical Integration Continuity Cell',
    'Validation dataset for state-package continuity scheduling',
    '{
      "responsible_subsystems": [
        {"code": "STRUCTURE", "name": "Structure subsystem"},
        {"code": "TRANSFER", "name": "Transfer subsystem"}
      ],
      "rules": [
        {
          "code": "SUBSYSTEM_CONTINUITY",
          "name": "Responsible subsystem continuity",
          "type": "group_continuity",
          "enabled": true,
          "activation_mode": "optional",
          "selector": {"match": "all"},
          "enforcement": {"mode": "soft", "priority": 1, "overridable": false},
          "parameters": {"group_by": "responsible_subsystem"}
        }
      ]
    }'::jsonb
);

INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
SELECT mt.id, v.feature_key, v.feature_name, 'enum', v.allowed_values::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('mechint_base_frame_status', 'Base Frame Status', '["pending", "installed"]'),
      ('mechint_column_alignment_status', 'Column Alignment Status', '["pending", "aligned"]'),
      ('mechint_atmospheric_arm_status', 'Atmospheric Arm Status', '["pending", "installed"]'),
      ('mechint_vacuum_arm_status', 'Vacuum Arm Status', '["pending", "installed"]')
) AS v(feature_key, feature_name, allowed_values)
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

-- ============================================================
-- 2) Machine, resources, and current snapshot
-- ============================================================

INSERT INTO machine (machine_type_id, code, name, location)
SELECT mt.id, 'MI-CONT-001', 'Mechanical Integration Continuity Station #1', 'Validation Workshop'
FROM machine_type mt
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO resource (machine_id, code, name, resource_type, capacity, is_available, meta)
SELECT m.id, 'MI-MECH-TEAM-01', 'Mechanical Integration Team', 'MECH_INT_TEAM', 1, true, '{"skill":"mechanical_integration"}'::jsonb
FROM machine m
WHERE m.code = 'MI-CONT-001';

INSERT INTO machine_state (machine_id, state_type, label)
SELECT m.id, 'current', 'Mechanical integration continuity start'
FROM machine m
WHERE m.code = 'MI-CONT-001';

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value)
SELECT ms.id, v.feature_key, v.feature_value
FROM machine_state ms
JOIN machine m ON m.id = ms.machine_id
CROSS JOIN (
    VALUES
      ('mechint_base_frame_status', 'pending'),
      ('mechint_column_alignment_status', 'pending'),
      ('mechint_atmospheric_arm_status', 'pending'),
      ('mechint_vacuum_arm_status', 'pending')
) AS v(feature_key, feature_value)
WHERE m.code = 'MI-CONT-001'
  AND ms.state_type = 'current';

-- ============================================================
-- 3) Target state package tree
-- ============================================================

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'MECH_INTEGRATION_COMPLETE', 'Mechanical Integration Complete',
       NULL, 'eq', NULL, 'aggregate', 10, true,
       '{"_network_editor_layout":{"x":80,"y":80},"_network_editor_container":{"width":380,"height":460}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, v.code, v.name, NULL, 'eq', NULL, 'aggregate', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN state_node root ON root.machine_type_id = mt.id AND root.code = 'MECH_INTEGRATION_COMPLETE'
CROSS JOIN (
    VALUES
      ('STRUCTURE_ASSEMBLY_COMPLETE', 'Structure Assembly Complete', 10,
       '{"_network_editor_layout":{"x":130,"y":190},"_network_editor_container":{"width":300,"height":180}}'),
      ('TRANSFER_MECHANISM_READY', 'Transfer Mechanism Ready', 20,
       '{"_network_editor_layout":{"x":130,"y":410},"_network_editor_container":{"width":300,"height":180}}')
) AS v(code, name, sort_order, metadata_json)
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, pkg.id, 3, v.code, v.name, v.feature_key, 'eq', v.target_value, 'atomic', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('STRUCTURE_ASSEMBLY_COMPLETE', 'BASE_FRAME_INSTALLED', 'Base Frame Installed', 'mechint_base_frame_status', 'installed', 10,
       '{"_network_editor_layout":{"x":170,"y":270}}'),
      ('STRUCTURE_ASSEMBLY_COMPLETE', 'COLUMN_ALIGNED', 'Column Aligned', 'mechint_column_alignment_status', 'aligned', 20,
       '{"_network_editor_layout":{"x":170,"y":330}}'),
      ('TRANSFER_MECHANISM_READY', 'ATMOSPHERIC_ARM_INSTALLED', 'Atmospheric Arm Installed', 'mechint_atmospheric_arm_status', 'installed', 10,
       '{"_network_editor_layout":{"x":170,"y":490}}'),
      ('TRANSFER_MECHANISM_READY', 'VACUUM_ARM_INSTALLED', 'Vacuum Arm Installed', 'mechint_vacuum_arm_status', 'installed', 20,
       '{"_network_editor_layout":{"x":170,"y":550}}')
) AS v(parent_code, code, name, feature_key, target_value, sort_order, metadata_json)
JOIN state_node pkg ON pkg.machine_type_id = mt.id AND pkg.code = v.parent_code
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

-- ============================================================
-- 4) Activity package tree and atomic activities
-- ============================================================

INSERT INTO activity_node (
    machine_type_id, parent_id, level, code, name,
    description, activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'MECH_INTEGRATION_ACT', 'Mechanical Integration',
       'Top-level mechanical integration activity scope', 'normal', 10, true,
       '{"_network_editor_layout":{"x":560,"y":80},"_network_editor_container":{"width":400,"height":520}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO activity_node (
    machine_type_id, parent_id, level, code, name,
    description, activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, v.code, v.name, v.description, 'normal', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN activity_node root ON root.machine_type_id = mt.id AND root.code = 'MECH_INTEGRATION_ACT'
CROSS JOIN (
    VALUES
      ('STRUCTURE_ASSEMBLY_ACT', 'Structure Assembly', 'Install base frame and align column', 10,
       '{"_network_editor_layout":{"x":610,"y":190},"_network_editor_container":{"width":320,"height":200}}'),
      ('TRANSFER_MECHANISM_ACT', 'Transfer Mechanism Assembly', 'Install atmospheric and vacuum transfer arms', 20,
       '{"_network_editor_layout":{"x":610,"y":430},"_network_editor_container":{"width":320,"height":200}}')
) AS v(code, name, description, sort_order, metadata_json)
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO atomic_activity (
    machine_type_id, code, name, description,
    activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, v.code, v.name, v.description, 'normal', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('INSTALL_BASE_FRAME', 'Install Base Frame', 'Install the mechanical base frame', 10, '{"continuity_seed":true,"responsible_subsystem":"STRUCTURE"}'),
      ('ALIGN_COLUMN', 'Align Column', 'Align and lock the vertical column', 20, '{"continuity_seed":true,"responsible_subsystem":"STRUCTURE"}'),
      ('INSTALL_ATM_ARM', 'Install Atmospheric Arm', 'Install the atmospheric transfer arm', 30, '{"continuity_seed":true,"responsible_subsystem":"TRANSFER"}'),
      ('INSTALL_VAC_ARM', 'Install Vacuum Arm', 'Install the vacuum transfer arm', 40, '{"continuity_seed":true,"responsible_subsystem":"TRANSFER"}')
) AS v(code, name, description, sort_order, metadata_json)
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO activity_package_atomic_ref (activity_node_id, atomic_activity_id, sort_order, is_active, metadata_json)
SELECT pkg.id, aa.id, v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('STRUCTURE_ASSEMBLY_ACT', 'INSTALL_BASE_FRAME', 10, '{"_network_editor_layout":{"x":660,"y":270}}'),
      ('STRUCTURE_ASSEMBLY_ACT', 'ALIGN_COLUMN', 20, '{"_network_editor_layout":{"x":660,"y":330}}'),
      ('TRANSFER_MECHANISM_ACT', 'INSTALL_ATM_ARM', 10, '{"_network_editor_layout":{"x":660,"y":510}}'),
      ('TRANSFER_MECHANISM_ACT', 'INSTALL_VAC_ARM', 20, '{"_network_editor_layout":{"x":660,"y":570}}')
) AS v(package_code, atomic_code, sort_order, metadata_json)
JOIN activity_node pkg ON pkg.machine_type_id = mt.id AND pkg.code = v.package_code
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = v.atomic_code
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

-- ============================================================
-- 5) Operation rules and solve-relevant effects/resources
-- ============================================================

INSERT INTO op_rule (
    machine_type_id, activity_node_id, atomic_activity_id, code, name,
    duration_min, description, is_active, is_repair
)
SELECT mt.id, NULL, aa.id, v.rule_code, v.rule_name, 10, v.description, true, false
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('INSTALL_BASE_FRAME', 'RULE_INSTALL_BASE_FRAME', 'Install base frame', 'Achieves BASE_FRAME_INSTALLED'),
      ('ALIGN_COLUMN', 'RULE_ALIGN_COLUMN', 'Align column', 'Achieves COLUMN_ALIGNED'),
      ('INSTALL_ATM_ARM', 'RULE_INSTALL_ATM_ARM', 'Install atmospheric arm', 'Achieves ATMOSPHERIC_ARM_INSTALLED'),
      ('INSTALL_VAC_ARM', 'RULE_INSTALL_VAC_ARM', 'Install vacuum arm', 'Achieves VACUUM_ARM_INSTALLED')
) AS v(atomic_code, rule_code, rule_name, description)
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = v.atomic_code
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT r.id, v.feature_key, v.new_value, 'set'
FROM op_rule r
JOIN machine_type mt ON mt.id = r.machine_type_id
JOIN (
    VALUES
      ('RULE_INSTALL_BASE_FRAME', 'mechint_base_frame_status', 'installed'),
      ('RULE_ALIGN_COLUMN', 'mechint_column_alignment_status', 'aligned'),
      ('RULE_INSTALL_ATM_ARM', 'mechint_atmospheric_arm_status', 'installed'),
      ('RULE_INSTALL_VAC_ARM', 'mechint_vacuum_arm_status', 'installed')
) AS v(rule_code, feature_key, new_value) ON v.rule_code = r.code
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT r.id, 'MECH_INT_TEAM', 1, true
FROM op_rule r
JOIN machine_type mt ON mt.id = r.machine_type_id
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

-- ============================================================
-- 6) Minimal semantic bindings for Network Editor visibility
-- ============================================================

INSERT INTO activity_state_binding (
    machine_type_id, activity_node_id, atomic_activity_id, op_rule_id, state_node_id,
    binding_role, binding_type, coverage_policy, covered_leaf_state_ids, coverage_status,
    is_inherited, is_active, metadata_json
)
SELECT mt.id, NULL, aa.id, r.id, sn.id,
       'output', 'atomic_state', 'snapshot', jsonb_build_array(sn.id), 'complete',
       false, true, '{"continuity_seed":true}'::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('INSTALL_BASE_FRAME', 'RULE_INSTALL_BASE_FRAME', 'BASE_FRAME_INSTALLED'),
      ('ALIGN_COLUMN', 'RULE_ALIGN_COLUMN', 'COLUMN_ALIGNED'),
      ('INSTALL_ATM_ARM', 'RULE_INSTALL_ATM_ARM', 'ATMOSPHERIC_ARM_INSTALLED'),
      ('INSTALL_VAC_ARM', 'RULE_INSTALL_VAC_ARM', 'VACUUM_ARM_INSTALLED')
) AS v(atomic_code, rule_code, state_code)
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = v.atomic_code
JOIN op_rule r ON r.machine_type_id = mt.id AND r.code = v.rule_code
JOIN state_node sn ON sn.machine_type_id = mt.id AND sn.code = v.state_code
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

INSERT INTO activity_state_binding (
    machine_type_id, activity_node_id, atomic_activity_id, op_rule_id, state_node_id,
    binding_role, binding_type, coverage_policy, covered_leaf_state_ids, coverage_status,
    is_inherited, is_active, metadata_json
)
SELECT mt.id, an.id, NULL, NULL, sn.id,
       v.binding_role, 'state_package', 'snapshot',
       CASE
           WHEN sn.code = 'MECH_INTEGRATION_COMPLETE' THEN jsonb_build_array(base.id, col.id, atm.id, vac.id)
           WHEN sn.code = 'STRUCTURE_ASSEMBLY_COMPLETE' THEN jsonb_build_array(base.id, col.id)
           WHEN sn.code = 'TRANSFER_MECHANISM_READY' THEN jsonb_build_array(atm.id, vac.id)
           ELSE jsonb_build_array()
       END,
       'complete', false, true, '{"continuity_seed":true,"binding_scope":"package"}'::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('MECH_INTEGRATION_ACT', 'MECH_INTEGRATION_COMPLETE', 'declared_output'),
      ('STRUCTURE_ASSEMBLY_ACT', 'STRUCTURE_ASSEMBLY_COMPLETE', 'declared_output'),
      ('TRANSFER_MECHANISM_ACT', 'TRANSFER_MECHANISM_READY', 'declared_output')
) AS v(activity_code, state_code, binding_role)
JOIN activity_node an ON an.machine_type_id = mt.id AND an.code = v.activity_code
JOIN state_node sn ON sn.machine_type_id = mt.id AND sn.code = v.state_code
JOIN state_node base ON base.machine_type_id = mt.id AND base.code = 'BASE_FRAME_INSTALLED'
JOIN state_node col ON col.machine_type_id = mt.id AND col.code = 'COLUMN_ALIGNED'
JOIN state_node atm ON atm.machine_type_id = mt.id AND atm.code = 'ATMOSPHERIC_ARM_INSTALLED'
JOIN state_node vac ON vac.machine_type_id = mt.id AND vac.code = 'VACUUM_ARM_INSTALLED'
WHERE mt.code = 'MECH_INTEGRATION_CONTINUITY';

-- ============================================================
-- 7) Keep PostgreSQL sequences above seeded rows
-- ============================================================

SELECT setval(pg_get_serial_sequence('machine_type', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM machine_type), 1), 1), true);
SELECT setval(pg_get_serial_sequence('machine', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM machine), 1), 1), true);
SELECT setval(pg_get_serial_sequence('state_feature_def', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM state_feature_def), 1), 1), true);
SELECT setval(pg_get_serial_sequence('machine_state', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM machine_state), 1), 1), true);
SELECT setval(pg_get_serial_sequence('machine_state_feature', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM machine_state_feature), 1), 1), true);
SELECT setval(pg_get_serial_sequence('resource', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM resource), 1), 1), true);
SELECT setval(pg_get_serial_sequence('state_node', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM state_node), 1), 1), true);
SELECT setval(pg_get_serial_sequence('activity_node', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM activity_node), 1), 1), true);
SELECT setval(pg_get_serial_sequence('atomic_activity', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM atomic_activity), 1), 1), true);
SELECT setval(pg_get_serial_sequence('activity_package_atomic_ref', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM activity_package_atomic_ref), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule_precond', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_precond), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule_effect', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_effect), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule_resource_req', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_resource_req), 1), 1), true);
SELECT setval(pg_get_serial_sequence('activity_state_binding', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM activity_state_binding), 1), 1), true);
