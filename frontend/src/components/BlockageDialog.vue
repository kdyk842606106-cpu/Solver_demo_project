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

      <!-- Strategy B: blockage_reason (dynamic from API, ANCHOR constraint 6) -->
      <el-form-item v-if="strategyHasB" label="阻塞原因" required>
        <el-select v-model="form.blockage_reason" placeholder="请选择" style="width:100%">
          <el-option
            v-for="opt in blockageReasonOptions"
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
import { getFeatureDefinitions } from '../api/masterData'
import { postSolve } from '../api/solve'

const props = defineProps({
  modelValue: Boolean,
  task: Object,
  planId: Number,
  machineId: Number,
  currentStateId: Number,
  targetStateId: Number,
})

const emit = defineEmits(['update:modelValue', 'replanned'])

const submitting = ref(false)
const blockageReasonOptions = ref([])

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

// Load blockage_reason options dynamically from feature_definition (ANCHOR constraint 6)
async function onOpen() {
  try {
    const defs = await getFeatureDefinitions()
    const brDef = defs.find((d) => d.feature_key === 'blockage_reason')
    blockageReasonOptions.value = Array.isArray(brDef?.allowed_values) ? brDef.allowed_values : []
  } catch {
    blockageReasonOptions.value = []
  }
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

  const blockageConstraints = {
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
    const result = await postSolve({
      machine_id: props.machineId,
      current_state_id: props.currentStateId,
      target_state_id: props.targetStateId,
      objectives: [{ type: 'minimize_makespan', weight: 1.0 }],
      parent_plan_id: props.planId,
      blockage_constraints: blockageConstraints,
    })
    if (result.status !== 'done') {
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
