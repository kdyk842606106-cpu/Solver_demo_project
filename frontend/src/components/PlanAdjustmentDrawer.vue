<template>
  <el-drawer
    :model-value="modelValue"
    title="计划调整 / 重排"
    size="720px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-alert
      title="本次范围由计划师显式选择；范围外活动仅在必要时移动，并优先保持稳定。"
      type="info"
      :closable="false"
      show-icon
    />

    <section class="drawer-section">
      <div class="section-title">
        <span>待调整范围（{{ tasks.length }} 个活动）</span>
        <el-button text type="primary" @click="$emit('edit-scope')">返回修改范围</el-button>
      </div>
      <div class="task-tags">
        <el-tag v-for="task in tasks" :key="task.step_id" size="small">
          {{ task.step_order }}. {{ task.op_rule_code }}
        </el-tag>
      </div>
    </section>

    <section class="drawer-section">
      <div class="section-title">新增调整约束</div>
      <el-form label-width="110px">
        <el-form-item label="约束类型">
          <el-select v-model="draft.type" style="width: 100%">
            <el-option value="not_before" label="不得早于开始（not_before）" />
            <el-option value="finish_not_after" label="不得晚于完成" />
            <el-option value="fixed_start" label="固定开始" />
            <el-option value="freeze" label="保持基线时间" />
            <el-option value="priority" label="软性优先级" />
            <el-option value="precedence" label="新增先后关系" />
          </el-select>
        </el-form-item>
        <template v-if="isTimeConstraint">
          <el-form-item v-if="calendarEnabled" label="时间输入">
            <el-radio-group v-model="draft.time_input_mode">
              <el-radio value="minute">计划分钟</el-radio>
              <el-radio value="absolute">绝对日期时间</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="draft.time_input_mode === 'minute'" label="计划坐标">
            <el-input-number v-model="draft.value_min" :min="0" style="width: 200px" />
            <span class="muted">分钟</span>
          </el-form-item>
          <el-form-item v-else label="日期时间">
            <el-date-picker
              v-model="draft.value_at"
              type="datetime"
              format="YYYY-MM-DD HH:mm"
              placeholder="选择带时区的计划时间"
              style="width: 260px"
            />
            <span class="muted">{{ timezone }}</span>
          </el-form-item>
        </template>
        <el-form-item v-if="draft.type === 'priority'" label="优先级">
          <el-radio-group v-model="draft.value">
            <el-radio value="high">高</el-radio>
            <el-radio value="normal">普通</el-radio>
            <el-radio value="low">低</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="draft.type === 'precedence'">
          <el-form-item label="前序活动">
            <el-select v-model="draft.predecessor_step_id" style="width: 100%">
              <el-option v-for="task in tasks" :key="task.step_id" :value="task.step_id" :label="taskLabel(task)" />
            </el-select>
          </el-form-item>
          <el-form-item label="后序活动">
            <el-select v-model="draft.successor_step_id" style="width: 100%">
              <el-option v-for="task in tasks" :key="task.step_id" :value="task.step_id" :label="taskLabel(task)" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item v-else label="作用活动">
          <el-select v-model="draft.step_ids" multiple collapse-tags style="width: 100%">
            <el-option v-for="task in tasks" :key="task.step_id" :value="task.step_id" :label="taskLabel(task)" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" plain @click="addConstraint">加入约束清单</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="constraints" size="small" border empty-text="尚未添加约束">
        <el-table-column label="类型" width="150">
          <template #default="{ row }">{{ constraintLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="内容">
          <template #default="{ row }">{{ constraintSummary(row) }}</template>
        </el-table-column>
        <el-table-column width="80" label="操作">
          <template #default="{ $index }"><el-button text type="danger" @click="removeConstraint($index)">删除</el-button></template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="previewFeedback"
        class="preview-feedback"
        :title="previewFeedback.message"
        :type="previewFeedback.type"
        :closable="false"
        show-icon
      />
    </section>

    <section v-if="preview" class="drawer-section">
      <div class="section-title">候选计划影响</div>
      <el-alert
        v-if="preview.status === 'infeasible'"
        title="当前约束无可行排程；调整草稿已保留，未生成候选计划。"
        type="error"
        :closable="false"
        show-icon
      />
      <template v-else>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="基线工期">{{ preview.summary?.base_makespan_min }}m</el-descriptions-item>
          <el-descriptions-item label="候选工期">{{ preview.summary?.candidate_makespan_min }}m</el-descriptions-item>
          <el-descriptions-item label="范围内变化">{{ preview.summary?.scope_changed_task_count }} 个</el-descriptions-item>
          <el-descriptions-item label="范围外变化">{{ preview.summary?.outside_changed_task_count }} 个</el-descriptions-item>
          <el-descriptions-item label="范围内总位移">{{ preview.summary?.scope_total_shift_min }}m</el-descriptions-item>
          <el-descriptions-item label="范围外总位移">{{ preview.summary?.outside_total_shift_min }}m</el-descriptions-item>
        </el-descriptions>
        <el-table :data="changedDiffs" size="small" border max-height="280" style="margin-top: 12px">
          <el-table-column prop="step_order" label="步骤" width="70" />
          <el-table-column prop="op_rule_code" label="活动" min-width="150" />
          <el-table-column label="范围" width="80">
            <template #default="{ row }">{{ row.in_scope ? '范围内' : '范围外' }}</template>
          </el-table-column>
          <el-table-column prop="base_start_min" label="原开始" width="90" />
          <el-table-column prop="new_start_min" label="新开始" width="90" />
          <el-table-column prop="shift_min" label="位移" width="80" />
        </el-table>
      </template>
    </section>

    <template #footer>
      <div class="footer-actions">
        <el-button @click="cancel">取消调整</el-button>
        <el-button
          type="primary"
          plain
          :disabled="!adjustmentId || !tasks.length || confirming"
          :loading="previewing"
          @click="saveAndPreview"
        >保存并试算</el-button>
        <el-button
          type="primary"
          :disabled="preview?.status !== 'preview_ready'"
          :loading="confirming"
          @click="confirm"
        >确认候选为新基线</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  cancelPlanAdjustment,
  confirmPlanAdjustment,
  previewPlanAdjustment,
  updatePlanAdjustment,
} from '../api/solve'

const props = defineProps({
  modelValue: Boolean,
  adjustmentId: Number,
  tasks: { type: Array, default: () => [] },
  initialConstraints: { type: Array, default: () => [] },
  calendarEnabled: Boolean,
  scheduleStartAt: { type: String, default: '' },
  timezone: { type: String, default: 'Asia/Shanghai' },
})
const emit = defineEmits(['update:modelValue', 'edit-scope', 'confirmed', 'cancelled'])

const constraints = ref([])
const preview = ref(null)
const previewing = ref(false)
const confirming = ref(false)
const previewFeedback = ref(null)
const draft = reactive({
  type: 'not_before',
  step_ids: [],
  value_min: 0,
  value: 'normal',
  predecessor_step_id: null,
  successor_step_id: null,
  time_input_mode: 'minute',
  value_at: '',
})

const isTimeConstraint = computed(() => ['not_before', 'finish_not_after', 'fixed_start'].includes(draft.type))
const changedDiffs = computed(() => (preview.value?.task_diffs || []).filter((item) => item.changed))

watch(() => props.tasks, (items) => {
  const valid = new Set(items.map((item) => item.step_id))
  draft.step_ids = draft.step_ids.filter((id) => valid.has(id))
  if (!draft.step_ids.length) draft.step_ids = [...valid]
}, { immediate: true, deep: true })

watch(() => props.adjustmentId, () => {
  constraints.value = props.initialConstraints.map((item) => ({ ...item }))
  preview.value = null
  previewFeedback.value = props.adjustmentId
    ? null
    : { type: 'error', message: '调整单上下文已失效，请返回计划结果重新发起调整。' }
})

function constraintStepIds(item) {
  if (item.type === 'precedence') {
    return [item.predecessor_step_id, item.successor_step_id]
  }
  return item.step_ids || []
}

function taskLabel(task) {
  return `${task.step_order}. ${task.op_rule_code} - ${task.op_rule_name || ''}`
}

function constraintLabel(type) {
  return {
    not_before: 'not_before',
    finish_not_after: '不得晚于完成',
    fixed_start: '固定开始',
    freeze: '保持基线时间',
    priority: '软性优先级',
    precedence: '新增先后关系',
  }[type] || type
}

function constraintSummary(item) {
  if (item.type === 'precedence') return `${item.predecessor_step_id} → ${item.successor_step_id}`
  if (item.type === 'priority') return `${item.step_ids.length} 个活动 / ${item.value}`
  if (item.value_min != null) return `${item.step_ids.length} 个活动 / ${item.value_min}m`
  if (item.value_at) return `${item.step_ids.length} 个活动 / ${item.value_at}`
  return `${item.step_ids.length} 个活动`
}

function addConstraint() {
  if (draft.type === 'precedence') {
    if (!draft.predecessor_step_id || !draft.successor_step_id || draft.predecessor_step_id === draft.successor_step_id) {
      return ElMessage.warning('请选择两个不同的前后序活动')
    }
    constraints.value.push({
      type: 'precedence',
      predecessor_step_id: draft.predecessor_step_id,
      successor_step_id: draft.successor_step_id,
    })
  } else {
    if (!draft.step_ids.length) return ElMessage.warning('请选择约束作用活动')
    const item = { type: draft.type, step_ids: [...draft.step_ids] }
    if (isTimeConstraint.value && draft.time_input_mode === 'absolute') {
      if (!draft.value_at) return ElMessage.warning('请选择绝对日期时间')
      item.value_at = new Date(draft.value_at).toISOString()
      item.timezone = props.timezone
    } else if (isTimeConstraint.value) {
      item.value_min = draft.value_min
    }
    if (draft.type === 'priority') item.value = draft.value
    constraints.value.push(item)
  }
  preview.value = null
  previewFeedback.value = null
}

function previewErrorMessage(error) {
  return error?.message || '候选计划试算失败，请检查调整约束后重试。'
}

function removeConstraint(index) {
  constraints.value.splice(index, 1)
  preview.value = null
  previewFeedback.value = null
}

async function saveAndPreview() {
  if (!props.adjustmentId) {
    previewFeedback.value = { type: 'error', message: '调整单上下文已失效，请返回计划结果重新发起调整。' }
    return ElMessage.error(previewFeedback.value.message)
  }
  preview.value = null
  previewFeedback.value = { type: 'info', message: '正在保存调整约束并试算候选计划，请稍候…' }
  previewing.value = true
  try {
    const scopeIds = new Set(props.tasks.map((item) => item.step_id))
    const invalid = constraints.value.filter((item) =>
      constraintStepIds(item).some((stepId) => !scopeIds.has(stepId)),
    )
    if (invalid.length) {
      await ElMessageBox.confirm(
        `修改后的范围已排除 ${invalid.length} 条约束所引用的活动。继续将明确删除这些约束。`,
        '确认范围与约束变更',
        { type: 'warning', confirmButtonText: '删除并继续', cancelButtonText: '返回检查' },
      )
      constraints.value = constraints.value.filter((item) => !invalid.includes(item))
    }
    await updatePlanAdjustment(props.adjustmentId, {
      scope_step_ids: props.tasks.map((item) => item.step_id),
      constraints: constraints.value,
      remove_inherited_constraint_ids: [],
    })
    preview.value = await previewPlanAdjustment(props.adjustmentId)
    if (preview.value.status === 'preview_ready') {
      previewFeedback.value = { type: 'success', message: '候选计划试算完成，可以查看影响并确认新基线。' }
      ElMessage.success('候选计划试算完成')
    } else if (preview.value.status === 'infeasible') {
      previewFeedback.value = { type: 'error', message: '当前约束无可行排程；调整草稿已保留。' }
      ElMessage.warning('当前约束无可行排程')
    } else {
      previewFeedback.value = { type: 'warning', message: `试算已返回状态：${preview.value.status || '未知'}` }
    }
  } catch (error) {
    if (error === 'cancel' || error === 'close') {
      previewFeedback.value = { type: 'info', message: '已取消本次试算，调整约束草稿仍保留。' }
      return
    }
    previewFeedback.value = { type: 'error', message: previewErrorMessage(error) }
  } finally {
    previewing.value = false
  }
}

async function confirm() {
  confirming.value = true
  try {
    await confirmPlanAdjustment(props.adjustmentId)
    emit('confirmed', {
      candidatePlanId: preview.value?.candidate_plan_id,
      solveRequestId: preview.value?.summary?.candidate_solve_request_id,
    })
    emit('update:modelValue', false)
  } finally {
    confirming.value = false
  }
}

async function cancel() {
  await ElMessageBox.confirm('取消后将保留已生成的历史候选，但本调整单不可继续编辑。', '取消计划调整')
  await cancelPlanAdjustment(props.adjustmentId)
  emit('cancelled')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.drawer-section { margin-top: 20px; }
.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-weight: 600; }
.task-tags { display: flex; flex-wrap: wrap; gap: 6px; max-height: 120px; overflow: auto; }
.muted { margin-left: 8px; color: #64748b; }
.preview-feedback { margin-top: 12px; }
.footer-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
