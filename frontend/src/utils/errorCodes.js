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
}

export function getErrorMessage(errorCode) {
  return ERROR_MESSAGES[errorCode] ?? `操作失败（${errorCode ?? '未知错误'}）`
}
