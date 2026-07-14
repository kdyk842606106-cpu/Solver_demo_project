<!-- VersionHistory.vue — pure component
  Props:
    chain: Array<PlanVersionItem>
    currentId: Number
  Emits:
    diff(baseId, currentId)    点击"与当前对比"
    load(planId)               点击"加载此版本"
-->
<template>
  <el-card v-if="chain.length > 0" class="version-card">
    <template #header>
      <span>版本历史</span>
      <el-tag size="small" style="margin-left:8px">{{ chain.length }} 个版本</el-tag>
    </template>
    <el-timeline>
      <el-timeline-item
        v-for="v in chain"
        :key="v.id"
        :type="v.id === currentId ? 'primary' : 'info'"
        :hollow="v.id !== currentId"
        :timestamp="`v${v.version} · ${replanLabel(v.replan_reason)}`"
        placement="top"
      >
        <div class="version-item">
          <el-tag
            size="small"
            :type="v.id === currentId ? 'primary' : 'info'"
          >
            {{ v.id === currentId ? '当前' : v.status }}
          </el-tag>
          <span v-if="v.total_steps" class="muted" style="margin-left:6px">
            {{ v.total_steps }} 步
          </span>
          <div v-if="v.id !== currentId" class="version-actions">
            <el-button size="small" text @click="$emit('diff', v.id)">与当前对比</el-button>
            <el-button size="small" text @click="$emit('load', v.id)">查看</el-button>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </el-card>
</template>

<script setup>
defineProps({
  chain: { type: Array, default: () => [] },
  currentId: { type: Number, default: null },
})
defineEmits(['diff', 'load'])

const REPLAN_LABELS = {
  initial: '初始计划',
  blockage_strategy_a: '策略A重排',
  blockage_strategy_b: '策略B重排',
  blockage_strategy_ab: '策略AB重排',
  scheduling_rule_exception: '规则例外重排',
}

function replanLabel(reason) {
  return REPLAN_LABELS[reason] ?? reason ?? '初始计划'
}
</script>

<style scoped>
.version-card { margin-bottom: 16px; }
.version-item { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.version-actions { display: flex; gap: 4px; margin-left: auto; }
.muted { color: #64748b; font-size: 12px; }
</style>
