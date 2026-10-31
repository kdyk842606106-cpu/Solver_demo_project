<template>
  <div class="delete-effect-selector" data-testid="activity-delete-effects">
    <p>活动完成后使所选状态失效；这些状态无须在执行前成立。</p>
    <el-select :model-value="modelValue" multiple clearable filterable :disabled="disabled"
      placeholder="选择要破坏的原子状态（可为空）" style="width:100%"
      @update:model-value="$emit('update:modelValue', $event)">
      <el-option-group v-for="group in groups" :key="group.name" :label="group.name">
        <el-option v-for="state in group.states" :key="state.id" :value="state.id" :label="state.label"
          :disabled="excludedStateIds.includes(state.id)" />
      </el-option-group>
    </el-select>
    <small>活动包仅用于分类；每次绑定保存具体原子状态。</small>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  modelValue: { type: Array, default: () => [] }, states: { type: Array, default: () => [] },
  activities: { type: Array, default: () => [] }, statePackages: { type: Array, default: () => [] },
  statePackageMemberships: { type: Array, default: () => [] }, excludedStateIds: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
const groups = computed(() => {
  const packages = new Map(props.statePackages.map((p) => [p.id, p.name]))
  const statePackage = new Map(props.statePackageMemberships.map((m) => [m.state_id, packages.get(m.state_package_id)]))
  const owners = new Map(props.activities.map((a) => [a.output_state_id, a.name]))
  const result = new Map()
  for (const state of props.states) {
    const name = statePackage.get(state.id) || '其他原子状态'
    if (!result.has(name)) result.set(name, [])
    const owner = owners.get(state.id)
    result.get(name).push({ ...state, label: owner ? `${state.name}（${owner}）` : state.name })
  }
  return [...result].map(([name, states]) => ({ name, states }))
})
</script>

<style scoped>
.delete-effect-selector{display:grid;gap:12px}.delete-effect-selector p,.delete-effect-selector small{margin:0;color:#64748b}
</style>
