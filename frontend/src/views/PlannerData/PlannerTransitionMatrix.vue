<template>
  <div class="transition-matrix" :class="{ compact }" data-testid="activity-transition-matrix">

    <div class="transition-fields">
      <div class="state-field source-field">
        <div>
          <strong>执行前状态</strong>
          <small>转移条件：执行前成立，完成后失效；可不选或多选。</small>
        </div>
        <el-select
          :model-value="sourceStateIds"
          multiple
          clearable
          filterable
          :disabled="disabled"
          placeholder="无显式 transition"
          data-testid="transition-source-select"
          @update:model-value="$emit('update:sourceStateIds', $event || [])"
        >
          <el-option
            v-for="state in sourceStates"
            :key="state.id"
            :value="state.id"
            :label="stateOptionLabel(state)"
          />
        </el-select>
      </div>

      <div class="transition-arrow" aria-hidden="true">→</div>

      <div class="state-field target-field">
        <div>
          <strong>执行后状态</strong>
          <small>实现效果：系统自动创建并绑定，完成后生效。</small>
        </div>
        <el-input
          :model-value="outputStateName"
          :disabled="disabled"
          placeholder="结果状态名称"
          data-testid="transition-output-name"
          @update:model-value="$emit('update:outputStateName', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sourceStateId: { type: String, default: null },
  sourceStateIds: { type: Array, default: () => [] },
  outputStateId: { type: String, default: null },
  outputStateName: { type: String, default: '' },
  states: { type: Array, default: () => [] },
  activities: { type: Array, default: () => [] },
  legacyTransitions: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

defineEmits(['update:sourceStateIds', 'update:outputStateName'])

const activityById = computed(() => new Map(props.activities.map((item) => [item.id, item])))
const sourceStates = computed(() => props.states.filter((item) => item.id !== props.outputStateId))

function stateOptionLabel(state) {
  const producer = state.source_activity_id
    ? activityById.value.get(state.source_activity_id)
    : props.activities.find((item) => item.output_state_id === state.id)
  return producer ? `${state.name}（${producer.name}）` : state.name
}
</script>

<style scoped>
.transition-matrix{display:grid;gap:14px;width:100%}.transition-fields{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:stretch;gap:12px}.state-field{display:grid;gap:8px;padding:14px;border:1px solid #dbe4f0;border-radius:10px;background:#fff}.state-field strong,.state-field small{display:block}.state-field small{margin-top:2px;color:#64748b}.transition-arrow{align-self:center;color:#0f766e;font-size:22px;font-weight:800}.compact .transition-fields{grid-template-columns:1fr}.compact .transition-arrow{text-align:center;transform:rotate(90deg)}@media(max-width:760px){.transition-fields{grid-template-columns:1fr}.transition-arrow{text-align:center;transform:rotate(90deg)}}
</style>
