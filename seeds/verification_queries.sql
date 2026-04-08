-- ============================================================
-- Verification Queries for Seed Data
-- ============================================================
-- Run these queries to verify the seed data is correct
-- ============================================================

-- 1. 查询：当前状态 ID=1 满足哪些工序规则的所有前提条件
-- Query: Which operation rules have all preconditions satisfied by current state (ID=1)?
SELECT 
    op_rule.id, 
    op_rule.code, 
    op_rule.name,
    op_rule.duration_min
FROM op_rule
WHERE op_rule.is_active = TRUE
  AND NOT EXISTS (
    SELECT 1 FROM op_rule_precond p
    WHERE p.op_rule_id = op_rule.id
      AND NOT EXISTS (
        SELECT 1 FROM machine_state_feature f
        WHERE f.machine_state_id = 1
          AND f.feature_key = p.feature_key
          AND f.feature_value = p.feature_value
      )
  )
ORDER BY op_rule.duration_min;

-- Expected result: OP_WARMUP (cold satisfied), OP_CLEANING (dirty satisfied), OP_INSPECT (no preconditions)


-- 2. 查询：哪些工序的 effect 能将 feature_key='temperature_level' 变为 'hot'
-- Query: Which operations can set temperature_level to 'hot'?
SELECT 
    op_rule.id, 
    op_rule.code, 
    op_rule.name, 
    op_rule.duration_min
FROM op_rule
JOIN op_rule_effect e ON e.op_rule_id = op_rule.id
WHERE op_rule.is_active = TRUE
  AND e.feature_key = 'temperature_level'
  AND e.new_value = 'hot'
ORDER BY op_rule.duration_min;

-- Expected result: OP_WARMUP (30 min)


-- 3. 查询：哪些工序的 effect 能将 feature_key='clean_level' 变为 'clean'
-- Query: Which operations can set clean_level to 'clean'?
SELECT 
    op_rule.id, 
    op_rule.code, 
    op_rule.name, 
    op_rule.duration_min
FROM op_rule
JOIN op_rule_effect e ON e.op_rule_id = op_rule.id
WHERE op_rule.is_active = TRUE
  AND e.feature_key = 'clean_level'
  AND e.new_value = 'clean'
ORDER BY op_rule.duration_min;

-- Expected result: OP_CLEANING (20 min)


-- 4. 查询：哪些工序的 effect 能将 feature_key='calibration' 变为 'on'
-- Query: Which operations can set calibration to 'on'?
SELECT 
    op_rule.id, 
    op_rule.code, 
    op_rule.name, 
    op_rule.duration_min
FROM op_rule
JOIN op_rule_effect e ON e.op_rule_id = op_rule.id
WHERE op_rule.is_active = TRUE
  AND e.feature_key = 'calibration'
  AND e.new_value = 'on'
ORDER BY op_rule.duration_min;

-- Expected result: OP_CALIBRATE (15 min)


-- 5. 查询：OP_CALIBRATE 的所有前置条件
-- Query: What are all preconditions for OP_CALIBRATE?
SELECT 
    op_rule.code AS op_code,
    p.feature_key,
    p.operator,
    p.feature_value
FROM op_rule_precond p
JOIN op_rule ON op_rule.id = p.op_rule_id
WHERE op_rule.code = 'OP_CALIBRATE';

-- Expected result: temperature_level=hot, calibration=off


-- 6. 查询：状态差异分析（当前状态 vs 目标状态）
-- Query: State delta analysis (current vs target)
SELECT 
    curr.feature_key,
    curr.feature_value AS current_value,
    targ.feature_value AS target_value
FROM machine_state_feature curr
JOIN machine_state_feature targ ON targ.feature_key = curr.feature_key
WHERE curr.machine_state_id = 1  -- current state
  AND targ.machine_state_id = 2  -- target state
  AND curr.feature_value != targ.feature_value;

-- Expected result:
-- temperature_level: cold → hot
-- clean_level: dirty → clean
-- calibration: off → on


-- 7. 查询：完整的工序规则信息（含前置条件、效果、资源需求）
-- Query: Complete operation rule information
SELECT 
    op_rule.code,
    op_rule.name,
    op_rule.duration_min,
    STRING_AGG(DISTINCT 'precond:' || p.feature_key || '=' || p.feature_value, ', ') AS preconditions,
    STRING_AGG(DISTINCT 'effect:' || e.feature_key || '→' || e.new_value, ', ') AS effects,
    STRING_AGG(DISTINCT r.resource_type || '(' || r.quantity::text || ')', ', ') AS resources
FROM op_rule
LEFT JOIN op_rule_precond p ON p.op_rule_id = op_rule.id
LEFT JOIN op_rule_effect e ON e.op_rule_id = op_rule.id
LEFT JOIN op_rule_resource_req r ON r.op_rule_id = op_rule.id
WHERE op_rule.is_active = TRUE
GROUP BY op_rule.id, op_rule.code, op_rule.name, op_rule.duration_min
ORDER BY op_rule.code;

-- Expected result: All 5 operations with their details
