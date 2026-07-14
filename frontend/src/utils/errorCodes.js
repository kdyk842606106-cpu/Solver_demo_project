// error_code → Chinese message map (ANCHOR 约束 10)
export const ERROR_MESSAGES = {
  SOLVE_NO_SOLUTION: '无法找到满足约束的求解方案，请检查规则库或放宽约束',
  SOLVE_CYCLE_DETECTED: '工序规则中存在循环依赖，请检查规则库',
  SOLVE_INVALID_MACHINE: '指定的设备不存在',
  SOLVE_INVALID_STATE: '起点状态或目标状态无效',
  SOLVE_SCHEDULER_FAILED: '排程求解失败，CP-SAT 无解',
  PLAN_NOT_SCHEDULED: '该计划尚未生成排程结果',
  PLAN_NOT_FOUND: '计划不存在',
  STATE_NOT_FOUND: '状态记录不存在',
  MACHINE_NOT_FOUND: '设备不存在',
  RULE_NOT_FOUND: '工序规则不存在',
  RESOURCE_NOT_FOUND: '资源不存在',
  FEATURE_NOT_FOUND: '特征定义不存在',
  DUPLICATE_CODE: '编码已存在，请使用不同的编码',
  VALIDATION_ERROR: '请求参数校验失败',
  SYSTEM_DEFAULT_CALENDAR_REQUIRED: '系统必须保留一个启用的默认工作日历，请先将其他日历设为默认',
  DEFAULT_WORK_CALENDAR_MISSING: '当前没有可用的机器默认日历或系统默认日历',
  CALENDAR_REVISION_NOT_FOUND: '该工作日历没有可用版本',
  CALENDAR_START_REQUIRED: '计划开始时间必须填写，并精确到分钟',
  CALENDAR_CONTIGUOUS_WINDOW_TOO_SHORT: '没有足够长的连续允许时段，活动不能跨关闭或禁止班次暂停后续作',
  SCHEDULING_SHIFT_METADATA_REQUIRED: '班次限制规则要求工作日历窗口配置 shift code',
  SCHEDULING_RULE_CONFIG_INVALID: '排期规则配置无效',
  SCHEDULING_RULE_UNKNOWN_TYPE: '排期规则类型尚未注册',
  SCHEDULING_RULE_REFERENCE_INVALID: '排期规则引用了不存在的资源、状态维度或 shift code',
  SCHEDULING_RULE_OVERRIDE_INITIAL_SOLVE_FORBIDDEN: '规则例外只能在求解后针对具体任务申请',
  SCHEDULING_RULE_OVERRIDE_INVALID: '规则例外缺少活动、规则或原因',
  SCHEDULING_RULE_OVERRIDE_NOT_ALLOWED: '该必选规则不允许例外',
  RESPONSIBLE_SUBSYSTEM_INVALID: '原子活动责任子系统不在当前机器类型配置中',
  RESPONSIBLE_SUBSYSTEM_IN_USE: '责任子系统仍被原子活动引用，不能删除',
  STEP_OUTSIDE_CHANGE_SCOPE: '调整约束引用了待调整范围之外的活动，请返回检查范围或删除对应约束',
  STEP_OUTSIDE_BASELINE: '调整约束引用的活动不属于当前计划基线，请重新发起计划调整',
  ADJUSTMENT_NOT_PREVIEWABLE: '当前调整单状态不允许试算，请重新发起计划调整',
  ADJUSTMENT_STALE: '计划基线已发生变化，请基于最新基线重新发起调整',
}

export function getErrorMessage(errorCode) {
  return ERROR_MESSAGES[errorCode] ?? `操作失败（${errorCode ?? '未知错误'}）`
}
