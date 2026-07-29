<!-- BlockageDialog.vue — pure component
  Props:
    modelValue: Boolean       v-model visibility
    task: Object              blocked task {op_rule_code, step_order, ...}
    planId: Number            current candidate_plan_id → becomes parent_plan_id
    machineId: Number
    currentStateId: Number
    targetStateId: Number
  Emits:
    update:modelValue
    replanned(solveResult)
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="标记阻塞并重排"
    width="520px"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <el-form :model="form" label-width="100px">
      <!-- Blocked step (read-only) -->
      <el-form-item label="被阻塞步骤">
        <el-tag type="danger">{{ task?.op_rule_code ?? task?.op_code ?? '—' }}</el-tag>
        <span class="muted" style="margin-left:8px">Step {{ task?.step_order }}</span>
      </el-form-item>

      <!-- Strategy selection -->
      <el-form-item label="处理策略" required>
        <el-radio-group v-model="form.strategy">
          <el-radio value="A">策略 A — 活动提拉（延时执行）</el-radio>
          <el-radio value="B">策略 B — 插入维修序列</el-radio>
          <el-radio value="AB">策略 AB — 两者同时</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- Strategy A: not_before_offset -->
      <el-form-item v-if="strategyHasA" label="最早可执行">
        <el-input-number
          v-model="form.not_before_offset"
          :min="0"
          style="width:160px"
        />
        <span style="margin-left:8px;color:#64748b">分钟后</span>
      </el-form-item>

      <!-- Strategy B: reasons are loaded by the parent and passed into this pure component. -->
      <el-form-item v-if="strategyHasB" label="阻塞原因" required>
        <el-select v-model="form.blockage_reason" placeholder="请选择" style="width:100%">
          <el-option
            v-for="opt in props.blockageReasonOptions"
            :key="opt"
            :value="opt"
            :label="opt"
          />
          <el-option value="__custom__" label="自定义输入…" />
        </el-select>
        <el-input
          v-if="form.blockage_reason === '__custom__'"
          v-model="form.blockage_reason_custom"
          placeholder="输入阻塞原因"
          style="margin-top:8px"
        />
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" />
      </el-form-item>

      <el-form-item label="创建人">
        <el-input v-model="form.created_by" placeholder="可选" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交重排</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { postLayeredSolve, postMaintenanceSolve, postSolve } from '../api/solve'

const props = defineProps({
  modelValue: Boolean,
  task: Object,
  planId: Number,
  machineId: Number,
  currentStateId: Number,
  targetStateId: Number,
  mode: {
    type: String,
    default: 'snapshot',
  },
  objectives: {
    type: Array,
    default: () => [],
  },
  targetStateNodeIds: {
    type: Array,
    default: () => [],
  },
  atomicActivityScopeIds: {
    type: Array,
    default: () => [],
  },
  maintenanceIntentTemplateIds: {
    type: Array,
    default: () => [],
  },
  blockageReasonOptions: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:modelValue', 'replanned', 'adjustment-requested'])

const submitting = ref(false)
const form = ref({
  strategy: 'A',
  not_before_offset: 0,
  blockage_reason: '',
  blockage_reason_custom: '',
  note: '',
  created_by: '',
})

const strategyHasA = computed(() => form.value.strategy === 'A' || form.value.strategy === 'AB')
const strategyHasB = computed(() => form.value.strategy === 'B' || form.value.strategy === 'AB')

function onOpen() {
  // Reset form
  form.value = {
    strategy: 'A',
    not_before_offset: 0,
    blockage_reason: '',
    blockage_reason_custom: '',
    note: '',
    created_by: '',
  }
}

async function submit() {
  if (!props.task) return

  const actualReason =
    form.value.blockage_reason === '__custom__'
      ? form.value.blockage_reason_custom.trim()
      : form.value.blockage_reason

  if (strategyHasB.value && !actualReason) {
    return ElMessage.warning('策略 B/AB 必须选择阻塞原因')
  }

  if (form.value.strategy === 'A') {
    emit('update:modelValue', false)
    emit('adjustment-requested', {
      stepId: props.task.step_id,
      notBeforeMin: form.value.not_before_offset,
    })
    return
  }

  const blockageConstraints = {
    blocked_step_id: props.task.step_id ?? null,
    blocked_op_rule_id: props.task.op_rule_id ?? null,
    strategy: form.value.strategy,
    note: form.value.note.trim() || null,
    created_by: form.value.created_by.trim() || null,
  }
  if (strategyHasA.value) {
    blockageConstraints.strategy_a = { not_before_offset: form.value.not_before_offset }
  }
  if (strategyHasB.value) {
    blockageConstraints.strategy_b = { blockage_reason: actualReason }
  }

  submitting.value = true
  try {
    const basePayload = {
      machine_id: props.machineId,
      current_state_id: props.currentStateId,
      objectives: props.objectives?.length
        ? props.objectives
        : [{ type: 'minimize_makespan', weight: 1.0 }],
      parent_plan_id: props.planId,
      blockage_constraints: blockageConstraints,
    }
    const result = props.mode === 'layered'
      ? await postLayeredSolve({
        ...basePayload,
        target_state_node_ids: props.targetStateNodeIds,
        atomic_activity_scope_ids: props.atomicActivityScopeIds,
      })
      : props.mode === 'maintenance'
        ? await postMaintenanceSolve({
          ...basePayload,
          intent_template_ids: props.maintenanceIntentTemplateIds,
        })
        : await postSolve({
          ...basePayload,
          target_state_id: props.targetStateId,
        })
    if (result.status !== 'done') {
      console.error('[replan failed]', result)
      window.__lastSolveDiagnostics = result.diagnostics ?? result
      ElMessage.error(`${result.error_code}: ${result.error_message}`)
      return
    }
    emit('update:modelValue', false)
    emit('replanned', result)
  } finally {
    submitting.value = false
  }
}
</script>
