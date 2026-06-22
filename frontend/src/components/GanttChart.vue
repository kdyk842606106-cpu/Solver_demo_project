<!-- GanttChart.vue — pure component, ECharts custom series Gantt
  Props:
    tasks: Array<ScheduleTaskItem>   普通模式数据
    makespan: Number
    criticalPath: Array<string>      op_code list
    diffMode: Boolean                是否对比模式
    diffSteps: Array<PlanDiffStep>   对比模式数据
  Emits: none
-->
<template>
  <div>
    <!-- Legend -->
    <div v-if="hasRoles" class="legend">
      <span v-for="(color, role) in ROLE_COLORS" :key="role" class="legend-item">
        <span class="legend-dot" :style="{ background: color }" />
        {{ ROLE_LABELS[role] }}
      </span>
      <span v-if="diffMode" class="legend-item">
        <span class="legend-dot" style="background:#94a3b8;opacity:.5" />基准计划
      </span>
    </div>
    <div ref="chartEl" :style="{ width: '100%', height: chartHeight + 'px' }" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  makespan: { type: Number, default: 0 },
  criticalPath: { type: Array, default: () => [] },
  diffMode: { type: Boolean, default: false },
  diffSteps: { type: Array, default: () => [] },
  timeMode: { type: String, default: 'minute' },
  dayMinutes: { type: Number, default: 480 },
  labelMode: { type: String, default: 'full' },
})

const ROLE_COLORS = {
  normal: '#0f766e',
  repair: '#dc2626',
  pulled_forward: '#1d4ed8',
  delayed: '#d97706',
}
const ROLE_LABELS = {
  normal: '正常',
  repair: '维修',
  pulled_forward: '提前',
  delayed: '延后',
}

const chartEl = ref(null)
let chart = null

// Compute used roles to decide whether to show legend
const hasRoles = computed(() => {
  if (props.diffMode) return props.diffSteps.some((s) => s.step_role && s.step_role !== 'normal')
  return props.tasks.some((t) => t.step_role && t.step_role !== 'normal')
})

const chartHeight = computed(() => {
  const rows = props.diffMode ? props.diffSteps.length : props.tasks.length
  return Math.max(200, rows * 48 + 60)
})

function buildOption() {
  if (props.diffMode) return buildDiffOption()
  return buildNormalOption()
}

function formatNormalLabel(task, isCriticalPath) {
  if (props.labelMode === 'order-name') {
    const stepNo = task.step_order != null ? `${task.step_order}. ` : ''
    const name = task.display_name ?? task.displayName ?? task.op_rule_name ?? task.op_name ?? task.op_rule_code ?? task.op_code ?? 'UNKNOWN'
    return isCriticalPath ? `★ ${stepNo}${name}` : `${stepNo}${name}`
  }
  if (props.labelMode === 'name') {
    return task.display_name ?? task.displayName ?? task.op_rule_name ?? task.op_name ?? task.op_rule_code ?? task.op_code ?? 'UNKNOWN'
  }
  const stepNo = task.step_order != null ? `${task.step_order}. ` : ''
  const code = task.op_rule_code ?? task.op_code ?? 'UNKNOWN'
  const name = (task.op_rule_name ?? task.op_name ?? '').trim()
  const base = name ? `${stepNo}${code} - ${name}` : `${stepNo}${code}`
  return isCriticalPath ? `★ ${base}` : base
}

function formatDiffLabel(step) {
  if (props.labelMode === 'order-name') {
    const stepNo = step.step_order != null ? `${step.step_order}. ` : ''
    const name = step.display_name ?? step.displayName ?? step.op_name ?? step.op_rule_name ?? step.op_code ?? step.op_rule_code ?? 'UNKNOWN'
    return `${stepNo}${name}`
  }
  if (props.labelMode === 'name') {
    return step.display_name ?? step.displayName ?? step.op_name ?? step.op_rule_name ?? step.op_code ?? step.op_rule_code ?? 'UNKNOWN'
  }
  const prefix = step.base_start == null ? '[新增] ' : ''
  const stepNo = step.step_order != null ? `${step.step_order}. ` : ''
  const code = step.op_code ?? step.op_rule_code ?? 'UNKNOWN'
  const name = (step.op_name ?? step.op_rule_name ?? '').trim()
  const body = name ? `${stepNo}${code} - ${name}` : `${stepNo}${code}`
  return `${prefix}${body}`
}

function buildNormalOption() {
  const sorted = [...props.tasks].sort((a, b) => a.start_min - b.start_min)
  const categories = sorted.map((t) => {
    const isCP = props.criticalPath.includes(t.op_rule_code ?? t.op_code)
    return formatNormalLabel(t, isCP)
  })

  const data = sorted.map((t, i) => {
    const role = t.step_role ?? 'normal'
    const color = ROLE_COLORS[role] ?? ROLE_COLORS.normal
    const isCP = props.criticalPath.includes(t.op_rule_code ?? t.op_code)
    return {
      value: [i, t.start_min, t.end_min],
      itemStyle: {
        color,
        borderColor: isCP ? '#f59e0b' : color,
        borderWidth: isCP ? 2 : 0,
      },
    }
  })

  return makeOption(categories, data, props.makespan)
}

function buildDiffOption() {
  const steps = [...props.diffSteps].sort((a, b) =>
    (a.new_start ?? 9999) - (b.new_start ?? 9999) || a.op_code.localeCompare(b.op_code)
  )
  const categories = steps.map((s) => formatDiffLabel(s))

  const newBars = steps.map((s, i) => {
    if (s.new_start == null) return null
    const role = s.step_role ?? 'normal'
    return {
      value: [i, s.new_start, s.new_end],
      itemStyle: { color: ROLE_COLORS[role] ?? ROLE_COLORS.normal },
    }
  }).filter(Boolean)

  const baseBars = steps.map((s, i) => {
    if (s.base_start == null) return null
    return {
      value: [i, s.base_start, s.base_end],
      itemStyle: { color: 'rgba(148,163,184,0.45)' },
    }
  }).filter(Boolean)

  const maxEnd = Math.max(
    props.makespan,
    ...steps.map((s) => Math.max(s.new_end ?? 0, s.base_end ?? 0))
  )

  return {
    ...makeOption(categories, newBars, maxEnd),
    series: [
      makeSeries(baseBars, '基准'),
      makeSeries(newBars, '新计划'),
    ],
  }
}

function makeSeries(data, name) {
  return {
    type: 'custom',
    name,
    renderItem,
    encode: { x: [1, 2], y: 0 },
    data,
  }
}

function formatTimePoint(value) {
  if (props.timeMode !== 'day') return `${value}m`
  return `D${Math.floor(value / props.dayMinutes) + 1}`
}

function formatTimeRange(start, end) {
  if (props.timeMode !== 'day') {
    return `开始: ${start} min → 结束: ${end} min<br>时长: ${end - start} min`
  }
  const startDay = Math.floor(start / props.dayMinutes) + 1
  const endDay = Math.max(startDay, Math.ceil(end / props.dayMinutes))
  const durationDays = Math.round((end - start) / props.dayMinutes)
  return `开始: D${startDay}<br>结束: D${endDay}<br>工期: ${durationDays} 天`
}

function renderItem(params, api) {
  const categoryIndex = api.value(0)
  const start = api.coord([api.value(1), categoryIndex])
  const end = api.coord([api.value(2), categoryIndex])
  const height = api.size([0, 1])[1] * 0.6

  return {
    type: 'rect',
    shape: {
      x: start[0],
      y: start[1] - height / 2,
      width: Math.max(end[0] - start[0], 2),
      height,
    },
    style: {
      ...api.style(),
      textFill: '#fff',
      fontSize: 11,
    },
  }
}

function makeOption(categories, data, maxTime) {
  return {
    tooltip: {
      formatter: (p) => {
        const [idx, s, e] = p.value
        return `${categories[idx]}<br>${formatTimeRange(s, e)}`
      },
    },
    grid: { left: 160, right: 20, top: 10, bottom: 30 },
    xAxis: {
      min: 0,
      max: maxTime,
      scale: true,
      axisLabel: { formatter: formatTimePoint },
    },
    yAxis: {
      data: categories,
      axisLabel: { width: 150, overflow: 'truncate' },
      inverse: true,
    },
    series: [makeSeries(data, '计划')],
  }
}

function updateChart() {
  if (!chart) return
  chart.setOption(buildOption(), true)
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  updateChart()
})

onBeforeUnmount(() => {
  chart?.dispose()
})

watch(
  () => [props.tasks, props.diffMode, props.diffSteps, props.criticalPath, props.makespan, props.timeMode, props.labelMode],
  () => nextTick(updateChart),
)

// Resize observer
onMounted(() => {
  const ro = new ResizeObserver(() => chart?.resize())
  ro.observe(chartEl.value)
})
</script>

<style scoped>
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #475569;
}
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-dot { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
</style>
