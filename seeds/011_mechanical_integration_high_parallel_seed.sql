-- ============================================================
-- Mechanical Integration High-Parallel Seed
-- Idempotent: rerunning this file replaces only this validation dataset.
--
-- Dataset:
--   machine type: MECH_INTEGRATION_HIGH_PARALLEL
--   machine:      MI-HP-001
--
-- Purpose:
--   Materialize a 36-atomic-activity mechanical integration sequence with
--   real op_rule preconditions/effects so the planner derives a parallel DAG,
--   then show a resource bottleneck through one shared precision rig.
-- ============================================================

-- ============================================================
-- 0) Clean previous validation rows
-- ============================================================

DELETE FROM activity_state_binding
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM maintenance_intent_template
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DROP TABLE IF EXISTS mi_hp_solve_request_cleanup;
CREATE TEMP TABLE mi_hp_solve_request_cleanup (
    solve_request_id integer PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO mi_hp_solve_request_cleanup (solve_request_id)
WITH RECURSIVE solve_tree(id) AS (
    SELECT sr.id
    FROM solve_request sr
    JOIN machine m ON m.id = sr.machine_id
    WHERE m.code = 'MI-HP-001'
    UNION
    SELECT child.id
    FROM solve_request child
    JOIN candidate_plan parent_plan ON parent_plan.id = child.parent_plan_id
    JOIN solve_tree parent_request ON parent_request.id = parent_plan.solve_request_id
)
SELECT id FROM solve_tree;

DELETE FROM schedule_result
WHERE solve_request_id IN (SELECT solve_request_id FROM mi_hp_solve_request_cleanup);

DELETE FROM candidate_plan_step
WHERE candidate_plan_id IN (
    SELECT cp.id FROM candidate_plan cp
    WHERE cp.solve_request_id IN (SELECT solve_request_id FROM mi_hp_solve_request_cleanup)
);

UPDATE solve_request
SET parent_plan_id = NULL
WHERE id IN (SELECT solve_request_id FROM mi_hp_solve_request_cleanup);

DELETE FROM candidate_plan
WHERE solve_request_id IN (
    SELECT solve_request_id FROM mi_hp_solve_request_cleanup
);

DELETE FROM solve_request
WHERE id IN (SELECT solve_request_id FROM mi_hp_solve_request_cleanup);

DELETE FROM op_rule_resource_req
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM op_rule_precond
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM op_rule_effect
WHERE op_rule_id IN (
    SELECT r.id
    FROM op_rule r
    JOIN machine_type mt ON mt.id = r.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM op_rule
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM activity_package_atomic_ref
WHERE activity_node_id IN (
    SELECT an.id
    FROM activity_node an
    JOIN machine_type mt ON mt.id = an.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
)
OR atomic_activity_id IN (
    SELECT aa.id
    FROM atomic_activity aa
    JOIN machine_type mt ON mt.id = aa.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM state_node_reference
WHERE state_node_id IN (
    SELECT sn.id
    FROM state_node sn
    JOIN machine_type mt ON mt.id = sn.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
)
OR parent_state_node_id IN (
    SELECT sn.id
    FROM state_node sn
    JOIN machine_type mt ON mt.id = sn.machine_type_id
    WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM atomic_activity
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM activity_node
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM state_node
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM machine_state_feature
WHERE machine_state_id IN (
    SELECT ms.id
    FROM machine_state ms
    JOIN machine m ON m.id = ms.machine_id
    WHERE m.code = 'MI-HP-001'
);

DELETE FROM machine_state
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'MI-HP-001'
);

DELETE FROM resource
WHERE machine_id IN (
    SELECT id FROM machine WHERE code = 'MI-HP-001'
);

DELETE FROM machine
WHERE code = 'MI-HP-001'
OR machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM state_feature_def
WHERE machine_type_id IN (
    SELECT id FROM machine_type WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL'
);

DELETE FROM machine_type
WHERE code = 'MECH_INTEGRATION_HIGH_PARALLEL';

DELETE FROM feature_definition
WHERE feature_key LIKE 'mi_hp_mi_a%_done';

-- ============================================================
-- 1) Scenario tables
-- ============================================================

DROP TABLE IF EXISTS mi_hp_package_plan;
CREATE TEMP TABLE mi_hp_package_plan (
    activity_code text PRIMARY KEY,
    activity_name text NOT NULL,
    state_code text NOT NULL,
    state_name text NOT NULL,
    sort_order integer NOT NULL
) ON COMMIT DROP;

INSERT INTO mi_hp_package_plan (activity_code, activity_name, state_code, state_name, sort_order) VALUES
('MI_HP_PREP_ACT', '集成准备', 'MI_HP_PREP_READY', '集成准备完成', 10),
('MI_HP_STRUCTURE_ACT', '结构装配', 'MI_HP_STRUCTURE_DONE', '结构装配完成', 20),
('MI_HP_TRANSFER_ACT', '传动机构装配', 'MI_HP_TRANSFER_READY', '传动机构就绪', 30),
('MI_HP_UTILITY_ACT', '管路电气连接', 'MI_HP_UTILITY_CONNECTED', '管路电气连接完成', 40),
('MI_HP_DEBUG_ACT', '调试校准', 'MI_HP_DEBUG_DONE', '调试校准完成', 50),
('MI_HP_ACCEPTANCE_ACT', '验收释放', 'MI_HP_ACCEPTED', '机械集成验收完成', 60);

DROP TABLE IF EXISTS mi_hp_resource_plan;
CREATE TEMP TABLE mi_hp_resource_plan (
    resource_type text PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    capacity integer NOT NULL
) ON COMMIT DROP;

INSERT INTO mi_hp_resource_plan (resource_type, code, name, capacity) VALUES
('PROCESS_ENGINEER', 'MI-HP-PE-01', '工艺工程师', 1),
('SAFETY_OFFICER', 'MI-HP-SAFE-01', '安全员', 1),
('LOGISTICS', 'MI-HP-LOG-01', '物流员', 1),
('MECH_A', 'MI-HP-MECH-A', '机械组A', 1),
('MECH_B', 'MI-HP-MECH-B', '机械组B', 1),
('METROLOGY', 'MI-HP-MET-01', '计量员', 2),
('CONTROL', 'MI-HP-CTRL-01', '控制组', 1),
('QA', 'MI-HP-QA-01', '质检组', 1),
('PIPE_TEAM', 'MI-HP-PIPE-01', '管路组', 2),
('ELECTRICAL', 'MI-HP-ELEC-01', '电气组', 1),
('PRECISION_RIG', 'MI-HP-RIG-01', '精密校准工装', 1);

DROP TABLE IF EXISTS mi_hp_activity_plan;
CREATE TEMP TABLE mi_hp_activity_plan (
    seq integer PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    package_code text NOT NULL,
    effect_name text NOT NULL,
    resource_type text NOT NULL,
    duration_min integer NOT NULL
) ON COMMIT DROP;

INSERT INTO mi_hp_activity_plan (seq, code, name, package_code, effect_name, resource_type, duration_min) VALUES
(1, 'MI_A001', '确认工单与版本', 'MI_HP_PREP_ACT', '工单已确认', 'PROCESS_ENGINEER', 10),
(2, 'MI_A002', '执行断电挂牌', 'MI_HP_PREP_ACT', '安全隔离完成', 'SAFETY_OFFICER', 15),
(3, 'MI_A003', '清点机械物料', 'MI_HP_PREP_ACT', '机械物料齐套', 'LOGISTICS', 20),
(4, 'MI_A004', '校验安装工具', 'MI_HP_PREP_ACT', '工具可用', 'MECH_A', 15),
(5, 'MI_A005', '复核测量基准', 'MI_HP_PREP_ACT', '测量基准可用', 'METROLOGY', 15),
(6, 'MI_A006', '加载控制基线', 'MI_HP_PREP_ACT', '控制基线就绪', 'CONTROL', 20),
(7, 'MI_A007', '清洁安装基准面', 'MI_HP_PREP_ACT', '基准面洁净', 'MECH_A', 20),
(8, 'MI_A008', '关键件来料复检', 'MI_HP_PREP_ACT', '关键件合格', 'QA', 25),
(9, 'MI_A009', '标定安装基准线', 'MI_HP_STRUCTURE_ACT', '基准线完成', 'METROLOGY', 20),
(10, 'MI_A010', '安装底座框架', 'MI_HP_STRUCTURE_ACT', '底座已安装', 'MECH_A', 30),
(11, 'MI_A011', '安装左侧立柱', 'MI_HP_STRUCTURE_ACT', '左立柱已安装', 'MECH_A', 25),
(12, 'MI_A012', '安装右侧立柱', 'MI_HP_STRUCTURE_ACT', '右立柱已安装', 'MECH_B', 25),
(13, 'MI_A013', '校正左侧立柱', 'MI_HP_STRUCTURE_ACT', '左立柱合格', 'METROLOGY', 20),
(14, 'MI_A014', '校正右侧立柱', 'MI_HP_STRUCTURE_ACT', '右立柱合格', 'METROLOGY', 20),
(15, 'MI_A015', '安装横梁组件', 'MI_HP_STRUCTURE_ACT', '横梁已安装', 'MECH_A', 30),
(16, 'MI_A016', '调整导轨直线度', 'MI_HP_STRUCTURE_ACT', '导轨直线度合格', 'METROLOGY', 25),
(17, 'MI_A017', '锁紧结构连接件', 'MI_HP_STRUCTURE_ACT', '结构装配完成', 'MECH_B', 15),
(18, 'MI_A018', '安装大气臂基座', 'MI_HP_TRANSFER_ACT', '大气臂基座已安装', 'MECH_A', 25),
(19, 'MI_A019', '安装真空臂基座', 'MI_HP_TRANSFER_ACT', '真空臂基座已安装', 'MECH_B', 25),
(20, 'MI_A020', '安装大气臂本体', 'MI_HP_TRANSFER_ACT', '大气臂已安装', 'MECH_A', 35),
(21, 'MI_A021', '安装真空臂本体', 'MI_HP_TRANSFER_ACT', '真空臂已安装', 'MECH_B', 35),
(22, 'MI_A022', '调整大气臂限位', 'MI_HP_TRANSFER_ACT', '大气臂限位合格', 'MECH_A', 20),
(23, 'MI_A023', '调整真空臂限位', 'MI_HP_TRANSFER_ACT', '真空臂限位合格', 'MECH_B', 20),
(24, 'MI_A024', '安装驱动电机', 'MI_HP_TRANSFER_ACT', '驱动电机已安装', 'MECH_A', 25),
(25, 'MI_A025', '安装减速器与联轴器', 'MI_HP_TRANSFER_ACT', '传动链已连接', 'MECH_B', 25),
(26, 'MI_A026', '调整同轴度与张力', 'MI_HP_TRANSFER_ACT', '传动机构就绪', 'METROLOGY', 30),
(27, 'MI_A027', '安装真空管路', 'MI_HP_UTILITY_ACT', '真空管路已安装', 'PIPE_TEAM', 30),
(28, 'MI_A028', '安装气路与冷却管路', 'MI_HP_UTILITY_ACT', '辅助管路已安装', 'PIPE_TEAM', 30),
(29, 'MI_A029', '安装电缆拖链', 'MI_HP_UTILITY_ACT', '拖链已安装', 'ELECTRICAL', 25),
(30, 'MI_A030', '连接传感器线缆', 'MI_HP_UTILITY_ACT', '传感器已连接', 'ELECTRICAL', 30),
(31, 'MI_A031', '接入控制柜接口', 'MI_HP_UTILITY_ACT', '控制接口已接入', 'ELECTRICAL', 25),
(32, 'MI_A032', '执行管路泄漏检查', 'MI_HP_DEBUG_ACT', '管路检查通过', 'QA', 25),
(33, 'MI_A033', '执行 I/O 点检', 'MI_HP_DEBUG_ACT', 'I/O 点检通过', 'CONTROL', 30),
(34, 'MI_A034', '执行单轴点动测试', 'MI_HP_DEBUG_ACT', '单轴运动通过', 'CONTROL', 30),
(35, 'MI_A035', '执行双臂互锁与循环测试', 'MI_HP_ACCEPTANCE_ACT', '双臂循环通过', 'CONTROL', 45),
(36, 'MI_A036', '完成机械集成验收', 'MI_HP_ACCEPTANCE_ACT', '机械集成完成', 'QA', 20);

DROP TABLE IF EXISTS mi_hp_dependency_plan;
CREATE TEMP TABLE mi_hp_dependency_plan (
    activity_code text NOT NULL,
    dep_code text NOT NULL
) ON COMMIT DROP;

INSERT INTO mi_hp_dependency_plan (activity_code, dep_code) VALUES
('MI_A002', 'MI_A001'),
('MI_A003', 'MI_A001'),
('MI_A004', 'MI_A001'),
('MI_A005', 'MI_A001'),
('MI_A006', 'MI_A001'),
('MI_A007', 'MI_A002'),
('MI_A007', 'MI_A004'),
('MI_A008', 'MI_A003'),
('MI_A008', 'MI_A005'),
('MI_A009', 'MI_A005'),
('MI_A009', 'MI_A007'),
('MI_A010', 'MI_A008'),
('MI_A010', 'MI_A009'),
('MI_A011', 'MI_A010'),
('MI_A012', 'MI_A010'),
('MI_A013', 'MI_A011'),
('MI_A014', 'MI_A012'),
('MI_A015', 'MI_A013'),
('MI_A015', 'MI_A014'),
('MI_A016', 'MI_A015'),
('MI_A017', 'MI_A016'),
('MI_A018', 'MI_A017'),
('MI_A019', 'MI_A017'),
('MI_A020', 'MI_A018'),
('MI_A021', 'MI_A019'),
('MI_A022', 'MI_A020'),
('MI_A023', 'MI_A021'),
('MI_A024', 'MI_A022'),
('MI_A024', 'MI_A023'),
('MI_A025', 'MI_A022'),
('MI_A025', 'MI_A023'),
('MI_A026', 'MI_A024'),
('MI_A026', 'MI_A025'),
('MI_A027', 'MI_A018'),
('MI_A027', 'MI_A019'),
('MI_A028', 'MI_A018'),
('MI_A028', 'MI_A019'),
('MI_A029', 'MI_A017'),
('MI_A030', 'MI_A022'),
('MI_A030', 'MI_A023'),
('MI_A030', 'MI_A029'),
('MI_A031', 'MI_A006'),
('MI_A031', 'MI_A029'),
('MI_A031', 'MI_A030'),
('MI_A032', 'MI_A027'),
('MI_A032', 'MI_A028'),
('MI_A033', 'MI_A031'),
('MI_A034', 'MI_A026'),
('MI_A034', 'MI_A032'),
('MI_A034', 'MI_A033'),
('MI_A035', 'MI_A034'),
('MI_A036', 'MI_A035');

DROP TABLE IF EXISTS mi_hp_extra_resource_req_plan;
CREATE TEMP TABLE mi_hp_extra_resource_req_plan (
    activity_code text NOT NULL,
    resource_type text NOT NULL
) ON COMMIT DROP;

INSERT INTO mi_hp_extra_resource_req_plan (activity_code, resource_type) VALUES
('MI_A013', 'PRECISION_RIG'),
('MI_A014', 'PRECISION_RIG'),
('MI_A016', 'PRECISION_RIG'),
('MI_A026', 'PRECISION_RIG');

-- ============================================================
-- 2) Machine type, state dimensions, machine, resources
-- ============================================================

INSERT INTO feature_definition (feature_key, value_type, allowed_values, unit, description)
SELECT 'mi_hp_' || lower(code) || '_done',
       'enum',
       '["false","true"]'::jsonb,
       NULL,
       effect_name
FROM mi_hp_activity_plan;

INSERT INTO machine_type (code, name, description) VALUES
(
    'MECH_INTEGRATION_HIGH_PARALLEL',
    'Mechanical Integration High-Parallel Cell',
    '36-activity high-parallel mechanical integration validation dataset'
);

INSERT INTO state_feature_def (machine_type_id, feature_key, feature_name, value_type, allowed_values)
SELECT mt.id,
       'mi_hp_' || lower(item.code) || '_done',
       item.effect_name,
       'enum',
       '["false","true"]'::jsonb
FROM machine_type mt
CROSS JOIN mi_hp_activity_plan item
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO machine (machine_type_id, code, name, location)
SELECT mt.id, 'MI-HP-001', 'Mechanical Integration High-Parallel Station #1', 'Validation Workshop'
FROM machine_type mt
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO resource (machine_id, code, name, resource_type, capacity, is_available, meta)
SELECT m.id, rp.code, rp.name, rp.resource_type, rp.capacity, true, jsonb_build_object('seed', '011_high_parallel')
FROM machine m
CROSS JOIN mi_hp_resource_plan rp
WHERE m.code = 'MI-HP-001';

INSERT INTO machine_state (machine_id, state_type, label)
SELECT m.id, 'current', 'Mechanical integration high-parallel start'
FROM machine m
WHERE m.code = 'MI-HP-001';

INSERT INTO machine_state_feature (machine_state_id, feature_key, feature_value)
SELECT ms.id, 'mi_hp_' || lower(item.code) || '_done', 'false'
FROM machine_state ms
JOIN machine m ON m.id = ms.machine_id
CROSS JOIN mi_hp_activity_plan item
WHERE m.code = 'MI-HP-001'
  AND ms.state_type = 'current';

-- ============================================================
-- 3) Target state tree
-- ============================================================

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'MI_HP_COMPLETE', '机械集成高并行完成',
       NULL, 'eq', NULL, 'aggregate', 10, true,
       '{"_network_editor_layout":{"x":80,"y":80},"_network_editor_container":{"width":520,"height":760}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, pp.state_code, pp.state_name,
       NULL, 'eq', NULL, 'aggregate', pp.sort_order, true,
       jsonb_build_object('_network_editor_layout', jsonb_build_object('x', 130, 'y', 120 + pp.sort_order * 9))
FROM machine_type mt
JOIN state_node root ON root.machine_type_id = mt.id AND root.code = 'MI_HP_COMPLETE'
JOIN mi_hp_package_plan pp ON true
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO state_node (
    machine_type_id, parent_id, level, code, name,
    feature_key, operator, target_value, state_kind, sort_order, is_active, metadata_json
)
SELECT mt.id, pkg_state.id, 3,
       'STATE_' || item.code || '_DONE',
       item.effect_name,
       'mi_hp_' || lower(item.code) || '_done',
       'eq',
       'true',
       'atomic',
       item.seq,
       true,
       jsonb_build_object('_network_editor_layout', jsonb_build_object('x', 170, 'y', 150 + item.seq * 36))
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
JOIN mi_hp_package_plan pp ON pp.activity_code = item.package_code
JOIN state_node pkg_state ON pkg_state.machine_type_id = mt.id AND pkg_state.code = pp.state_code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

-- ============================================================
-- 4) Activity packages and atomic activities
-- ============================================================

INSERT INTO activity_node (
    machine_type_id, parent_id, level, code, name,
    description, activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, NULL, 1, 'MI_HP_ACT', '机械集成高并行',
       'Top-level high-parallel mechanical integration activity scope',
       'normal', 10, true,
       '{"_network_editor_layout":{"x":720,"y":80},"_network_editor_container":{"width":460,"height":760}}'::jsonb
FROM machine_type mt
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO activity_node (
    machine_type_id, parent_id, level, code, name,
    description, activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, root.id, 2, pp.activity_code, pp.activity_name,
       pp.activity_name,
       'normal',
       pp.sort_order,
       true,
       jsonb_build_object('_network_editor_layout', jsonb_build_object('x', 770, 'y', 120 + pp.sort_order * 9))
FROM machine_type mt
JOIN activity_node root ON root.machine_type_id = mt.id AND root.code = 'MI_HP_ACT'
JOIN mi_hp_package_plan pp ON true
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO atomic_activity (
    machine_type_id, code, name, description,
    activity_category, sort_order, is_active, metadata_json
)
SELECT mt.id, item.code, item.name, item.effect_name,
       'normal',
       item.seq,
       true,
       jsonb_build_object('seed', '011_high_parallel')
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO activity_package_atomic_ref (activity_node_id, atomic_activity_id, sort_order, is_active, metadata_json)
SELECT pkg.id, aa.id, item.seq, true,
       jsonb_build_object('_network_editor_layout', jsonb_build_object('x', 820, 'y', 150 + item.seq * 36))
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
JOIN activity_node pkg ON pkg.machine_type_id = mt.id AND pkg.code = item.package_code
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = item.code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

-- ============================================================
-- 5) Operation rules and solver semantics
-- ============================================================

INSERT INTO op_rule (
    machine_type_id, activity_node_id, atomic_activity_id, code, name,
    duration_min, description, is_active, is_repair
)
SELECT mt.id, NULL, aa.id,
       'RULE_' || item.code,
       item.name,
       item.duration_min,
       item.effect_name,
       true,
       false
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = item.code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO op_rule_precond (op_rule_id, feature_key, operator, feature_value)
SELECT rule.id,
       'mi_hp_' || lower(dep.dep_code) || '_done',
       'eq',
       'true'
FROM machine_type mt
JOIN mi_hp_dependency_plan dep ON true
JOIN op_rule rule ON rule.machine_type_id = mt.id AND rule.code = 'RULE_' || dep.activity_code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO op_rule_effect (op_rule_id, feature_key, new_value, effect_type)
SELECT rule.id,
       'mi_hp_' || lower(item.code) || '_done',
       'true',
       'set'
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
JOIN op_rule rule ON rule.machine_type_id = mt.id AND rule.code = 'RULE_' || item.code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT rule.id, item.resource_type, 1, true
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
JOIN op_rule rule ON rule.machine_type_id = mt.id AND rule.code = 'RULE_' || item.code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO op_rule_resource_req (op_rule_id, resource_type, quantity, is_required)
SELECT rule.id, extra.resource_type, 1, true
FROM machine_type mt
JOIN mi_hp_extra_resource_req_plan extra ON true
JOIN op_rule rule ON rule.machine_type_id = mt.id AND rule.code = 'RULE_' || extra.activity_code
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

-- ============================================================
-- 6) Network Editor semantic bindings for inputs and outputs
-- ============================================================

INSERT INTO activity_state_binding (
    machine_type_id, activity_node_id, atomic_activity_id, op_rule_id, state_node_id,
    binding_role, binding_type, coverage_policy, covered_leaf_state_ids, coverage_status,
    is_inherited, is_active, metadata_json
)
SELECT mt.id, NULL, aa.id, rule.id, sn.id,
       'output', 'atomic_state', 'snapshot', jsonb_build_array(sn.id), 'complete',
       false, true, jsonb_build_object('seed', '011_high_parallel')
FROM machine_type mt
JOIN mi_hp_activity_plan item ON true
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = item.code
JOIN op_rule rule ON rule.machine_type_id = mt.id AND rule.code = 'RULE_' || item.code
JOIN state_node sn ON sn.machine_type_id = mt.id AND sn.code = 'STATE_' || item.code || '_DONE'
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

INSERT INTO activity_state_binding (
    machine_type_id, activity_node_id, atomic_activity_id, op_rule_id, state_node_id,
    binding_role, binding_type, coverage_policy, covered_leaf_state_ids, coverage_status,
    is_inherited, is_active, metadata_json
)
SELECT mt.id, NULL, aa.id, rule.id, dep_state.id,
       'input', 'atomic_state', 'snapshot', jsonb_build_array(dep_state.id), 'complete',
       false, true, jsonb_build_object('seed', '011_high_parallel')
FROM machine_type mt
JOIN mi_hp_dependency_plan dep ON true
JOIN atomic_activity aa ON aa.machine_type_id = mt.id AND aa.code = dep.activity_code
JOIN op_rule rule ON rule.machine_type_id = mt.id AND rule.code = 'RULE_' || dep.activity_code
JOIN state_node dep_state ON dep_state.machine_type_id = mt.id AND dep_state.code = 'STATE_' || dep.dep_code || '_DONE'
WHERE mt.code = 'MECH_INTEGRATION_HIGH_PARALLEL';

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
