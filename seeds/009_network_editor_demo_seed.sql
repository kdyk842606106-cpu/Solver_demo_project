-- ============================================================
-- Network Editor Demo Seed
-- Idempotent: rerunning this file replaces only this demo dataset.
--
-- Demo machine type:
--   NETWORK_EDITOR_DEMO_CELL
--
-- What it creates:
--   - machine type + machine instance
--   - state feature definitions
--   - current/target machine state snapshots
--   - resources
--   - state hierarchy with layout metadata
--   - activity hierarchy, atomic activities, package refs with layout metadata
--   - op rules and semantic activity-state bindings
--   - complete activity bindings: every op_rule precondition/effect has a matching
--     Network Editor activity_state_binding row
-- ============================================================

-- ============================================================
-- 0) Clean previous demo rows
-- ============================================================

DELETE FROM activity_state_binding
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM scope_guard_precond
WHERE scope_guard_id IN (
    SELECT sg.id
    FROM scope_guard sg
    JOIN activity_node an ON an.id = sg.activity_node_id
    JOIN machine_type mt ON mt.id = an.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM scope_guard
WHERE activity_node_id IN (
    SELECT an.id
    FROM activity_node an
    JOIN machine_type mt ON mt.id = an.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM maintenance_intent_template
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM op_rule
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM activity_package_atomic_ref
WHERE activity_node_id IN (
    SELECT an.id
    FROM activity_node an
    JOIN machine_type mt ON mt.id = an.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
)
OR atomic_activity_id IN (
    SELECT aa.id
    FROM atomic_activity aa
    JOIN machine_type mt ON mt.id = aa.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM state_node_reference
WHERE state_node_id IN (
    SELECT sn.id
    FROM state_node sn
    JOIN machine_type mt ON mt.id = sn.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
)
OR parent_state_node_id IN (
    SELECT sn.id
    FROM state_node sn
    JOIN machine_type mt ON mt.id = sn.machine_type_id
    WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM atomic_activity
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM activity_node
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM state_node
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM machine_state_feature
WHERE machine_state_id IN (
    SELECT ms.id
    FROM machine_state ms
    JOIN machine m ON m.id = ms.machine_id
    WHERE m.code = 'NED-DEMO-001'
);

DELETE FROM machine_state
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'NED-DEMO-001'
);

DELETE FROM resource
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'NED-DEMO-001'
);

DELETE FROM machine
WHERE code = 'NED-DEMO-001'
OR machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM state_feature_def
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'NETWORK_EDITOR_DEMO_CELL'
);

DELETE FROM machine_type
WHERE code = 'NETWORK_EDITOR_DEMO_CELL';

DELETE FROM feature_definition
WHERE feature_key LIKE 'nedemo_%';

-- ============================================================
-- 1) Feature definitions
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description) VALUES
('nedemo_frame_ready', 'enum', '["false", "true"]'::jsonb, NULL, 'Demo frame readiness'),
('nedemo_module_a_installed', 'enum', '["false", "true"]'::jsonb, NULL, 'Demo module A installation'),
('nedemo_module_b_installed', 'enum', '["false", "true"]'::jsonb, NULL, 'Demo module B installation'),
('nedemo_alignment_done', 'enum', '["false", "true"]'::jsonb, NULL, 'Demo alignment completion'),
('nedemo_test_passed', 'enum', '["false", "true"]'::jsonb, NULL, 'Demo test completion'),
('nedemo_delivery_ready', 'enum', '["false", "true"]'::jsonb, NULL, 'Demo delivery readiness'),
('nedemo_blockage_reason', 'enum', '["none", "alignment_issue"]'::jsonb, NULL, 'Demo blockage reason');

-- ============================================================
-- 2) Machine type, feature defs, machine, resources, snapshots
-- ============================================================

INSERT INTO machine_type (code, name, description) VALUES
(
    'NETWORK_EDITOR_DEMO_CELL',
    'Network Editor Demo Assembly Cell',
    'Demo dataset for loading and editing an existing machine-type network graph'
);

INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
SELECT mt.id, v.feature_key, v.feature_name, 'enum', v.allowed_values::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('nedemo_frame_ready', 'Frame Ready', '["false", "true"]'),
      ('nedemo_module_a_installed', 'Module A Installed', '["false", "true"]'),
      ('nedemo_module_b_installed', 'Module B Installed', '["false", "true"]'),
      ('nedemo_alignment_done', 'Alignment Done', '["false", "true"]'),
      ('nedemo_test_passed', 'Test Passed', '["false", "true"]'),
      ('nedemo_delivery_ready', 'Delivery Ready', '["false", "true"]'),
      ('nedemo_blockage_reason', 'Blockage Reason', '["none", "alignment_issue"]')
) AS v(feature_key, feature_name, allowed_values)
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO machine (machine_type_id, code, name, location)
SELECT mt.id, 'NED-DEMO-001', 'Network Editor Demo Station #1', 'Demo Workshop'
FROM machine_type mt
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO resource (machine_id, code, name, resource_type, capacity, is_available, meta)
SELECT m.id, v.code, v.name, v.resource_type, 1, true, v.meta::jsonb
FROM machine m
CROSS JOIN (
    VALUES
      ('NED-MECH-01', 'Demo Mechanical Team', 'NED_MECH_TEAM', '{"skill":"mechanical"}'),
      ('NED-ELEC-01', 'Demo Electrical Team', 'NED_ELEC_TEAM', '{"skill":"electrical"}'),
      ('NED-QA-01', 'Demo QA Team', 'NED_QA_TEAM', '{"skill":"quality"}')
) AS v(code, name, resource_type, meta)
WHERE m.code = 'NED-DEMO-001';

INSERT INTO machine_state (machine_id, state_type, label)
SELECT m.id, 'current', 'Network Editor demo start state'
FROM machine m
WHERE m.code = 'NED-DEMO-001';

INSERT INTO machine_state (machine_id, state_type, label)
SELECT m.id, 'target', 'Network Editor demo delivery-ready target'
FROM machine m
WHERE m.code = 'NED-DEMO-001';

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value)
SELECT ms.id, v.feature_key, v.feature_value
FROM machine_state ms
JOIN machine m ON m.id = ms.machine_id
CROSS JOIN (
    VALUES
      ('nedemo_frame_ready', 'false'),
      ('nedemo_module_a_installed', 'false'),
      ('nedemo_module_b_installed', 'false'),
      ('nedemo_alignment_done', 'false'),
      ('nedemo_test_passed', 'false'),
      ('nedemo_delivery_ready', 'false'),
      ('nedemo_blockage_reason', 'none')
) AS v(feature_key, feature_value)
WHERE m.code = 'NED-DEMO-001'
  AND ms.state_type = 'current';

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value)
SELECT ms.id, v.feature_key, v.feature_value
FROM machine_state ms
JOIN machine m ON m.id = ms.machine_id
CROSS JOIN (
    VALUES
      ('nedemo_frame_ready', 'true'),
      ('nedemo_module_a_installed', 'true'),
      ('nedemo_module_b_installed', 'true'),
      ('nedemo_alignment_done', 'true'),
      ('nedemo_test_passed', 'true'),
      ('nedemo_delivery_ready', 'true'),
      ('nedemo_blockage_reason', 'none')
) AS v(feature_key, feature_value)
WHERE m.code = 'NED-DEMO-001'
  AND ms.state_type = 'target';

-- ============================================================
-- 3) State hierarchy with Network Editor layout metadata
-- ============================================================

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'S_NED_TARGET_ROOT', 'Demo delivery target', NULL, 'eq', NULL, 'aggregate', 10, true,
       '{"_network_editor_layout":{"x":80,"y":80},"_network_editor_container":{"width":360,"height":560}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'S_NED_START_ROOT', 'Demo start conditions', NULL, 'eq', NULL, 'aggregate', 5, true,
       '{"_network_editor_layout":{"x":80,"y":-360},"_network_editor_container":{"width":340,"height":430}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, start_root.id, 2, v.code, v.name, v.feature_key, 'eq', 'false', 'atomic', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN state_node start_root ON start_root.machine_type_id = mt.id AND start_root.code = 'S_NED_START_ROOT'
CROSS JOIN (
    VALUES
      ('S_NED_FRAME_NOT_READY', 'Frame not ready', 'nedemo_frame_ready', 10, '{"_network_editor_layout":{"x":145,"y":-260}}'),
      ('S_NED_MODULE_A_NOT_INSTALLED', 'Module A not installed', 'nedemo_module_a_installed', 20, '{"_network_editor_layout":{"x":145,"y":-200}}'),
      ('S_NED_MODULE_B_NOT_INSTALLED', 'Module B not installed', 'nedemo_module_b_installed', 30, '{"_network_editor_layout":{"x":145,"y":-140}}'),
      ('S_NED_ALIGNMENT_NOT_DONE', 'Alignment not done', 'nedemo_alignment_done', 40, '{"_network_editor_layout":{"x":145,"y":-80}}'),
      ('S_NED_TEST_NOT_PASSED', 'Test not passed', 'nedemo_test_passed', 50, '{"_network_editor_layout":{"x":145,"y":-20}}'),
      ('S_NED_DELIVERY_NOT_READY', 'Delivery not ready', 'nedemo_delivery_ready', 60, '{"_network_editor_layout":{"x":145,"y":40}}')
) AS v(code, name, feature_key, sort_order, metadata_json)
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, 'S_NED_MECH_DONE', 'Mechanical assembly complete', NULL, 'eq', NULL, 'aggregate', 10, true,
       '{"_network_editor_layout":{"x":130,"y":205},"_network_editor_container":{"width":280,"height":250}}'::jsonb
FROM machine_type mt
JOIN state_node root ON root.machine_type_id = mt.id AND root.code = 'S_NED_TARGET_ROOT'
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, 'S_NED_QA_DONE', 'Quality gate complete', NULL, 'eq', NULL, 'aggregate', 20, true,
       '{"_network_editor_layout":{"x":130,"y":485},"_network_editor_container":{"width":280,"height":230}}'::jsonb
FROM machine_type mt
JOIN state_node root ON root.machine_type_id = mt.id AND root.code = 'S_NED_TARGET_ROOT'
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, mech.id, 3, v.code, v.name, v.feature_key, 'eq', 'true', 'atomic', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN state_node mech ON mech.machine_type_id = mt.id AND mech.code = 'S_NED_MECH_DONE'
CROSS JOIN (
    VALUES
      ('S_NED_FRAME_READY', 'Frame ready', 'nedemo_frame_ready', 10, '{"_network_editor_layout":{"x":170,"y":300}}'),
      ('S_NED_MODULE_A_INSTALLED', 'Module A installed', 'nedemo_module_a_installed', 20, '{"_network_editor_layout":{"x":170,"y":380}}'),
      ('S_NED_MODULE_B_INSTALLED', 'Module B installed', 'nedemo_module_b_installed', 30, '{"_network_editor_layout":{"x":170,"y":460}}')
) AS v(code, name, feature_key, sort_order, metadata_json)
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, qa.id, 3, v.code, v.name, v.feature_key, 'eq', 'true', 'atomic', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN state_node qa ON qa.machine_type_id = mt.id AND qa.code = 'S_NED_QA_DONE'
CROSS JOIN (
    VALUES
      ('S_NED_ALIGNMENT_DONE', 'Alignment done', 'nedemo_alignment_done', 10, '{"_network_editor_layout":{"x":170,"y":585}}'),
      ('S_NED_TEST_PASSED', 'Test passed', 'nedemo_test_passed', 20, '{"_network_editor_layout":{"x":170,"y":665}}'),
      ('S_NED_DELIVERY_READY', 'Delivery ready', 'nedemo_delivery_ready', 30, '{"_network_editor_layout":{"x":170,"y":745}}')
) AS v(code, name, feature_key, sort_order, metadata_json)
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'S_NED_RELEASE_VIEW', 'Release readiness view', NULL, 'eq', NULL, 'aggregate', 30, true,
       '{"_network_editor_layout":{"x":80,"y":820},"_network_editor_container":{"width":320,"height":180}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO state_node_reference (state_node_id, parent_state_node_id, sort_order, is_active, metadata_json)
SELECT child.id, parent.id, 10, true,
       '{"_network_editor_layout":{"x":145,"y":930},"demo_note":"Referenced QA state inside release view"}'::jsonb
FROM state_node child
JOIN machine_type mt ON mt.id = child.machine_type_id
JOIN state_node parent ON parent.machine_type_id = mt.id AND parent.code = 'S_NED_RELEASE_VIEW'
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL'
  AND child.code = 'S_NED_TEST_PASSED';

-- ============================================================
-- 4) Activity hierarchy and atomic activity package refs
-- ============================================================

INSERT INTO activity_node (
    machine_type_id, parent_id, level, code, name,
    description, activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'A_NED_ASSEMBLY_FLOW', 'Demo assembly flow',
       'Top-level network editor demo activity scope', 'normal', 10, true,
       '{"_network_editor_layout":{"x":560,"y":80},"_network_editor_container":{"width":420,"height":760}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO activity_node (
    machine_type_id, parent_id, level, code, name,
    description, activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, v.code, v.name, v.description, 'normal', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN activity_node root ON root.machine_type_id = mt.id AND root.code = 'A_NED_ASSEMBLY_FLOW'
CROSS JOIN (
    VALUES
      ('A_NED_MECH_PACKAGE', 'Mechanical package', 'Install frame and modules', 10,
       '{"_network_editor_layout":{"x":610,"y":205},"_network_editor_container":{"width":340,"height":310}}'),
      ('A_NED_QA_PACKAGE', 'Quality package', 'Align, test, and release', 20,
       '{"_network_editor_layout":{"x":610,"y":560},"_network_editor_container":{"width":340,"height":340}}')
) AS v(code, name, description, sort_order, metadata_json)
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO atomic_activity (
    machine_type_id, code, name, description,
    activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, v.code, v.name, v.description, 'normal', v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
CROSS JOIN (
    VALUES
      ('AA_NED_INSTALL_FRAME', 'Install frame', 'Install and lock the base frame', 10, '{"library_note":"Reusable mechanical capability"}'),
      ('AA_NED_INSTALL_MODULE_A', 'Install module A', 'Install module A after frame readiness', 20, '{"library_note":"Reusable module installation"}'),
      ('AA_NED_INSTALL_MODULE_B', 'Install module B', 'Install module B after frame readiness', 30, '{"library_note":"Reusable module installation"}'),
      ('AA_NED_ALIGN_SYSTEM', 'Align system', 'Align the assembled modules', 40, '{"library_note":"Reusable QA capability"}'),
      ('AA_NED_RUN_TEST', 'Run integration test', 'Run final network integration test', 50, '{"library_note":"Reusable test capability"}'),
      ('AA_NED_RELEASE', 'Release to delivery', 'Mark the cell as delivery ready', 60, '{"library_note":"Reusable release capability"}')
) AS v(code, name, description, sort_order, metadata_json)
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO activity_package_atomic_ref (activity_node_id, atomic_activity_id, sort_order, is_active, metadata_json)
SELECT pkg.id, aa.id, v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN activity_node pkg ON pkg.machine_type_id = mt.id AND pkg.code = 'A_NED_MECH_PACKAGE'
JOIN atomic_activity aa ON aa.machine_type_id = mt.id
JOIN (
    VALUES
      ('AA_NED_INSTALL_FRAME', 10, '{"_network_editor_layout":{"x":660,"y":300},"instance_note":"Frame install in mechanical package"}'),
      ('AA_NED_INSTALL_MODULE_A', 20, '{"_network_editor_layout":{"x":660,"y":380},"instance_note":"Module A install in mechanical package"}'),
      ('AA_NED_INSTALL_MODULE_B', 30, '{"_network_editor_layout":{"x":660,"y":460},"instance_note":"Module B install in mechanical package"}')
) AS v(atomic_code, sort_order, metadata_json) ON v.atomic_code = aa.code
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO activity_package_atomic_ref (activity_node_id, atomic_activity_id, sort_order, is_active, metadata_json)
SELECT pkg.id, aa.id, v.sort_order, true, v.metadata_json::jsonb
FROM machine_type mt
JOIN activity_node pkg ON pkg.machine_type_id = mt.id AND pkg.code = 'A_NED_QA_PACKAGE'
JOIN atomic_activity aa ON aa.machine_type_id = mt.id
JOIN (
    VALUES
      ('AA_NED_ALIGN_SYSTEM', 10, '{"_network_editor_layout":{"x":660,"y":650},"instance_note":"Alignment in QA package"}'),
      ('AA_NED_RUN_TEST', 20, '{"_network_editor_layout":{"x":660,"y":730},"instance_note":"Integration test in QA package"}'),
      ('AA_NED_RELEASE', 30, '{"_network_editor_layout":{"x":660,"y":810},"instance_note":"Release in QA package"}')
) AS v(atomic_code, sort_order, metadata_json) ON v.atomic_code = aa.code
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

-- ============================================================
-- 5) Operation rules
-- ============================================================

INSERT INTO op_rule (
    machine_type_id, activity_node_id, atomic_activity_id, code, name,
    duration_min, description, is_active, is_repair
)
SELECT mt.id, NULL, aa.id, v.code, v.name, v.duration_min, v.description, true, false
FROM machine_type mt
JOIN atomic_activity aa ON aa.machine_type_id = mt.id
JOIN (
    VALUES
      ('AA_NED_INSTALL_FRAME', 'OP_NED_INSTALL_FRAME', 'Install frame operation', 60, 'Turns frame_ready to true'),
      ('AA_NED_INSTALL_MODULE_A', 'OP_NED_INSTALL_MODULE_A', 'Install module A operation', 45, 'Turns module_a_installed to true'),
      ('AA_NED_INSTALL_MODULE_B', 'OP_NED_INSTALL_MODULE_B', 'Install module B operation', 45, 'Turns module_b_installed to true'),
      ('AA_NED_ALIGN_SYSTEM', 'OP_NED_ALIGN_SYSTEM', 'Align system operation', 50, 'Turns alignment_done to true'),
      ('AA_NED_RUN_TEST', 'OP_NED_RUN_TEST', 'Run integration test operation', 40, 'Turns test_passed to true'),
      ('AA_NED_RELEASE', 'OP_NED_RELEASE', 'Release operation', 30, 'Turns delivery_ready to true')
) AS v(atomic_code, code, name, duration_min, description) ON v.atomic_code = aa.code
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT r.id, v.feature_key, 'eq', v.feature_value
FROM op_rule r
JOIN (
    VALUES
      ('OP_NED_INSTALL_FRAME', 'nedemo_frame_ready', 'false'),
      ('OP_NED_INSTALL_MODULE_A', 'nedemo_frame_ready', 'true'),
      ('OP_NED_INSTALL_MODULE_A', 'nedemo_module_a_installed', 'false'),
      ('OP_NED_INSTALL_MODULE_B', 'nedemo_frame_ready', 'true'),
      ('OP_NED_INSTALL_MODULE_B', 'nedemo_module_b_installed', 'false'),
      ('OP_NED_ALIGN_SYSTEM', 'nedemo_module_a_installed', 'true'),
      ('OP_NED_ALIGN_SYSTEM', 'nedemo_module_b_installed', 'true'),
      ('OP_NED_ALIGN_SYSTEM', 'nedemo_alignment_done', 'false'),
      ('OP_NED_RUN_TEST', 'nedemo_alignment_done', 'true'),
      ('OP_NED_RUN_TEST', 'nedemo_test_passed', 'false'),
      ('OP_NED_RELEASE', 'nedemo_test_passed', 'true'),
      ('OP_NED_RELEASE', 'nedemo_delivery_ready', 'false')
) AS v(rule_code, feature_key, feature_value) ON v.rule_code = r.code
JOIN machine_type mt ON mt.id = r.machine_type_id
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT r.id, v.feature_key, 'true', 'set'
FROM op_rule r
JOIN (
    VALUES
      ('OP_NED_INSTALL_FRAME', 'nedemo_frame_ready'),
      ('OP_NED_INSTALL_MODULE_A', 'nedemo_module_a_installed'),
      ('OP_NED_INSTALL_MODULE_B', 'nedemo_module_b_installed'),
      ('OP_NED_ALIGN_SYSTEM', 'nedemo_alignment_done'),
      ('OP_NED_RUN_TEST', 'nedemo_test_passed'),
      ('OP_NED_RELEASE', 'nedemo_delivery_ready')
) AS v(rule_code, feature_key) ON v.rule_code = r.code
JOIN machine_type mt ON mt.id = r.machine_type_id
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT r.id, v.resource_type, 1, true
FROM op_rule r
JOIN (
    VALUES
      ('OP_NED_INSTALL_FRAME', 'NED_MECH_TEAM'),
      ('OP_NED_INSTALL_MODULE_A', 'NED_MECH_TEAM'),
      ('OP_NED_INSTALL_MODULE_B', 'NED_ELEC_TEAM'),
      ('OP_NED_ALIGN_SYSTEM', 'NED_QA_TEAM'),
      ('OP_NED_RUN_TEST', 'NED_QA_TEAM'),
      ('OP_NED_RELEASE', 'NED_QA_TEAM')
) AS v(rule_code, resource_type) ON v.rule_code = r.code
JOIN machine_type mt ON mt.id = r.machine_type_id
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

-- ============================================================
-- 6) Network editor semantic bindings
-- ============================================================

INSERT INTO activity_state_binding (
    machine_type_id, activity_node_id, atomic_activity_id, op_rule_id, state_node_id,
    binding_role, binding_type, coverage_policy, covered_leaf_state_ids, coverage_status,
    is_inherited, is_active, metadata_json
)
SELECT mt.id, NULL, aa.id, r.id, sn.id,
       v.binding_role, 'atomic_state', 'snapshot', jsonb_build_array(sn.id), 'complete',
       false, true, '{"demo_seed":true}'::jsonb
FROM machine_type mt
JOIN atomic_activity aa ON aa.machine_type_id = mt.id
JOIN op_rule r ON r.machine_type_id = mt.id
JOIN state_node sn ON sn.machine_type_id = mt.id
JOIN (
    VALUES
      ('AA_NED_INSTALL_FRAME', 'OP_NED_INSTALL_FRAME', 'S_NED_FRAME_READY', 'output'),
      ('AA_NED_INSTALL_FRAME', 'OP_NED_INSTALL_FRAME', 'S_NED_FRAME_NOT_READY', 'input'),
      ('AA_NED_INSTALL_MODULE_A', 'OP_NED_INSTALL_MODULE_A', 'S_NED_FRAME_READY', 'input'),
      ('AA_NED_INSTALL_MODULE_A', 'OP_NED_INSTALL_MODULE_A', 'S_NED_MODULE_A_NOT_INSTALLED', 'input'),
      ('AA_NED_INSTALL_MODULE_A', 'OP_NED_INSTALL_MODULE_A', 'S_NED_MODULE_A_INSTALLED', 'output'),
      ('AA_NED_INSTALL_MODULE_B', 'OP_NED_INSTALL_MODULE_B', 'S_NED_FRAME_READY', 'input'),
      ('AA_NED_INSTALL_MODULE_B', 'OP_NED_INSTALL_MODULE_B', 'S_NED_MODULE_B_NOT_INSTALLED', 'input'),
      ('AA_NED_INSTALL_MODULE_B', 'OP_NED_INSTALL_MODULE_B', 'S_NED_MODULE_B_INSTALLED', 'output'),
      ('AA_NED_ALIGN_SYSTEM', 'OP_NED_ALIGN_SYSTEM', 'S_NED_MODULE_A_INSTALLED', 'input'),
      ('AA_NED_ALIGN_SYSTEM', 'OP_NED_ALIGN_SYSTEM', 'S_NED_MODULE_B_INSTALLED', 'input'),
      ('AA_NED_ALIGN_SYSTEM', 'OP_NED_ALIGN_SYSTEM', 'S_NED_ALIGNMENT_NOT_DONE', 'input'),
      ('AA_NED_ALIGN_SYSTEM', 'OP_NED_ALIGN_SYSTEM', 'S_NED_ALIGNMENT_DONE', 'output'),
      ('AA_NED_RUN_TEST', 'OP_NED_RUN_TEST', 'S_NED_ALIGNMENT_DONE', 'input'),
      ('AA_NED_RUN_TEST', 'OP_NED_RUN_TEST', 'S_NED_TEST_NOT_PASSED', 'input'),
      ('AA_NED_RUN_TEST', 'OP_NED_RUN_TEST', 'S_NED_TEST_PASSED', 'output'),
      ('AA_NED_RELEASE', 'OP_NED_RELEASE', 'S_NED_TEST_PASSED', 'input'),
      ('AA_NED_RELEASE', 'OP_NED_RELEASE', 'S_NED_DELIVERY_NOT_READY', 'input'),
      ('AA_NED_RELEASE', 'OP_NED_RELEASE', 'S_NED_DELIVERY_READY', 'output')
) AS v(atomic_code, rule_code, state_code, binding_role)
  ON v.atomic_code = aa.code
 AND v.rule_code = r.code
 AND v.state_code = sn.code
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

INSERT INTO activity_state_binding (
    machine_type_id, activity_node_id, atomic_activity_id, op_rule_id, state_node_id,
    binding_role, binding_type, coverage_policy, covered_leaf_state_ids, coverage_status,
    is_inherited, is_active, metadata_json
)
SELECT mt.id, an.id, NULL, NULL, sn.id,
       v.binding_role, 'state_package', 'snapshot',
       CASE
           WHEN sn.code = 'S_NED_START_ROOT' THEN jsonb_build_array(
               frame_not_ready.id,
               module_a_not_installed.id,
               module_b_not_installed.id,
               alignment_not_done.id,
               test_not_passed.id,
               delivery_not_ready.id
           )
           WHEN sn.code = 'S_NED_TARGET_ROOT' THEN jsonb_build_array(frame.id, module_a.id, module_b.id, alignment.id, test_passed.id, delivery.id)
           WHEN sn.code = 'S_NED_MECH_DONE' THEN jsonb_build_array(frame.id, module_a.id, module_b.id)
           WHEN sn.code = 'S_NED_QA_DONE' THEN jsonb_build_array(alignment.id, test_passed.id, delivery.id)
           ELSE jsonb_build_array()
       END,
       'complete', false, true, '{"demo_seed":true,"binding_scope":"package"}'::jsonb
FROM machine_type mt
JOIN activity_node an ON an.machine_type_id = mt.id
JOIN state_node sn ON sn.machine_type_id = mt.id
JOIN state_node frame_not_ready ON frame_not_ready.machine_type_id = mt.id AND frame_not_ready.code = 'S_NED_FRAME_NOT_READY'
JOIN state_node module_a_not_installed ON module_a_not_installed.machine_type_id = mt.id AND module_a_not_installed.code = 'S_NED_MODULE_A_NOT_INSTALLED'
JOIN state_node module_b_not_installed ON module_b_not_installed.machine_type_id = mt.id AND module_b_not_installed.code = 'S_NED_MODULE_B_NOT_INSTALLED'
JOIN state_node alignment_not_done ON alignment_not_done.machine_type_id = mt.id AND alignment_not_done.code = 'S_NED_ALIGNMENT_NOT_DONE'
JOIN state_node test_not_passed ON test_not_passed.machine_type_id = mt.id AND test_not_passed.code = 'S_NED_TEST_NOT_PASSED'
JOIN state_node delivery_not_ready ON delivery_not_ready.machine_type_id = mt.id AND delivery_not_ready.code = 'S_NED_DELIVERY_NOT_READY'
JOIN state_node frame ON frame.machine_type_id = mt.id AND frame.code = 'S_NED_FRAME_READY'
JOIN state_node module_a ON module_a.machine_type_id = mt.id AND module_a.code = 'S_NED_MODULE_A_INSTALLED'
JOIN state_node module_b ON module_b.machine_type_id = mt.id AND module_b.code = 'S_NED_MODULE_B_INSTALLED'
JOIN state_node alignment ON alignment.machine_type_id = mt.id AND alignment.code = 'S_NED_ALIGNMENT_DONE'
JOIN state_node test_passed ON test_passed.machine_type_id = mt.id AND test_passed.code = 'S_NED_TEST_PASSED'
JOIN state_node delivery ON delivery.machine_type_id = mt.id AND delivery.code = 'S_NED_DELIVERY_READY'
JOIN (
    VALUES
      ('A_NED_ASSEMBLY_FLOW', 'S_NED_START_ROOT', 'context_input'),
      ('A_NED_ASSEMBLY_FLOW', 'S_NED_TARGET_ROOT', 'declared_output'),
      ('A_NED_MECH_PACKAGE', 'S_NED_START_ROOT', 'context_input'),
      ('A_NED_MECH_PACKAGE', 'S_NED_MECH_DONE', 'declared_output'),
      ('A_NED_QA_PACKAGE', 'S_NED_MECH_DONE', 'context_input'),
      ('A_NED_QA_PACKAGE', 'S_NED_QA_DONE', 'declared_output')
) AS v(activity_code, state_code, binding_role)
  ON v.activity_code = an.code
 AND v.state_code = sn.code
WHERE mt.code = 'NETWORK_EDITOR_DEMO_CELL';

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
SELECT setval(pg_get_serial_sequence('state_node_reference', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM state_node_reference), 1), 1), true);
SELECT setval(pg_get_serial_sequence('activity_node', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM activity_node), 1), 1), true);
SELECT setval(pg_get_serial_sequence('atomic_activity', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM atomic_activity), 1), 1), true);
SELECT setval(pg_get_serial_sequence('activity_package_atomic_ref', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM activity_package_atomic_ref), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule_precond', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_precond), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule_effect', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_effect), 1), 1), true);
SELECT setval(pg_get_serial_sequence('op_rule_resource_req', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM op_rule_resource_req), 1), 1), true);
SELECT setval(pg_get_serial_sequence('activity_state_binding', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM activity_state_binding), 1), 1), true);
