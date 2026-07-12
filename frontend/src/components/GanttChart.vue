<!-- GanttChart.vue — pure component, ECharts custom series Gantt
  Props:
    tasks: Array<ScheduleTaskItem>   普通模式数据
    laneMode: Boolean                是否按状态包泳道展示
    laneGroups: Array<StateLane>     状态包泳道数据
    makespan: Number
    criticalPath: Array<string>      op_code list
    diffMode: Boolean                是否对比模式
    diffSteps: Array<PlanDiffStep>   对比模式数据
  Emits: none
-->
<template>
  <div>
    <div v-if="laneMode && laneGroups.length" class="lane-summary" data-testid="state-lane-summary">
      <span
        v-for="(group, index) in laneGroups"
        :key="group.key ?? group.state_group_id ?? index"
        class="lane-summary-item"
        :style="{ borderColor: laneColor(index) }"
      >
        <span class="lane-summary-code">{{ stateGroupLabel(group) }}</span>
        <span class="lane-summary-meta">{{ group.tasks?.length ?? group.task_count ?? 0 }} 个任务</span>
      </span>
    </div>

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
  laneMode: { type: Boolean, default: false },
  laneGroups: { type: Array, default: () => [] },
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
const LANE_COLORS = ['#0f766e', '#2563eb', '#7c3aed', '#b45309', '#be123c', '#0369a1', '#4d7c0f', '#9333ea']

const chartEl = ref(null)
let chart = null
let resizeObserver = null

const activeTasks = computed(() => {
  if (!props.laneMode) return props.tasks
  return props.laneGroups.flatMap((group) => group.tasks ?? [])
})

const hasRoles = computed(() => {
  if (props.diffMode) return props.diffSteps.some((s) => s.step_role && s.step_role !== 'normal')
  return activeTasks.value.some((t) => t.step_role && t.step_role !== 'normal')
})

const laneRows = computed(() => {
  const rows = []
  props.laneGroups.forEach((group, groupIndex) => {
    const color = laneColor(groupIndex)
    rows.push({
      type: 'lane',
      group,
      groupIndex,
      color,
      label: stateGroupTitle(group),
    })
    ;(group.tasks ?? []).forEach((task) => {
      const isCP = isCriticalPath(task)
      rows.push({
        type: 'task',
        group,
        groupIndex,
        color,
        task,
        label: `  ${formatNormalLabel(task, isCP)}`,
      })
    })
  })
  return rows
})

const chartHeight = computed(() => {
  const rows = props.diffMode
    ? props.diffSteps.length
    : props.laneMode
      ? laneRows.value.length
      : props.tasks.length
  return Math.max(220, rows * 42 + 70)
})

function buildOption() {
  if (props.diffMode) return buildDiffOption()
  if (props.laneMode) return buildLaneOption()
  return buildNormalOption()
}

function laneColor(index) {
  return LANE_COLORS[index % LANE_COLORS.length]
}

function stateGroupLabel(group) {
  return group?.state_group_code || group?.state_group_name || group?.key || '未归属状态包'
}

function stateGroupTitle(group) {
  const label = stateGroupLabel(group)
  const taskCount = group?.tasks?.length ?? group?.task_count ?? 0
  const name = group?.state_group_name && group.state_group_name !== label ? ` ${group.state_group_name}` : ''
  return `${label}${name} (${taskCount} 个任务)`
}

function stateGroupPathLabel(task, fallbackGroup) {
  const path = Array.isArray(task?.state_group_path) && task.state_group_path.length
    ? task.state_group_path
    : Array.isArray(task?.state_continuity_groups)
      ? task.state_continuity_groups
      : fallbackGroup?.state_group_path ?? []
  if (!path.length) return stateGroupLabel(fallbackGroup)
  return path.map((group) => stateGroupLabel(group)).join(' / ')
}

function isCriticalPath(task) {
  return props.criticalPath.includes(task.op_rule_code ?? task.op_code)
}

function formatNormalLabel(task, isCritical) {
  if (props.labelMode === 'order-name') {
    const stepNo = task.step_order != null ? `${task.step_order}. ` : ''
    const name = task.display_name ?? task.displayName ?? task.op_rule_name ?? task.op_name ?? task.op_rule_code ?? task.op_code ?? 'UNKNOWN'
    return isCritical ? `★ ${stepNo}${name}` : `${stepNo}${name}`
  }
  if (props.labelMode === 'name') {
    return task.display_name ?? task.displayName ?? task.op_rule_name ?? task.op_name ?? task.op_rule_code ?? task.op_code ?? 'UNKNOWN'
  }
  const stepNo = task.step_order != null ? `${task.step_order}. ` : ''
  const code = task.op_rule_code ?? task.op_code ?? 'UNKNOWN'
  const name = (task.op_rule_name ?? task.op_name ?? '').trim()
  const base = name ? `${stepNo}${code} - ${name}` : `${stepNo}${code}`
  return isCritical ? `★ ${base}` : base
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
  const categories = sorted.map((task) => formatNormalLabel(task, isCriticalPath(task)))

  const data = sorted.map((task, index) => taskBarData(task, index))
  return makeOption(categories, data, maxEndForTasks(sorted), {
    gridLeft: 170,
    tooltipFormatter: (p) => taskTooltip(p.data?.task, p.data?.label, p.data?.group),
  })
}

function buildLaneOption() {
  const rows = laneRows.value
  const rowLabels = rows.map((row) => row.label)
  const yAxisData = rows.map((row) => ({
    value: row.label,
    textStyle: {
      color: row.type === 'lane' ? row.color : '#334155',
      fontWeight: row.type === 'lane' ? 700 : 400,
    },
  }))
  const maxTime = maxEndForTasks(activeTasks.value)

  const backgroundData = rows.map((row, rowIndex) => ({
    value: [rowIndex, 0, maxTime],
    color: row.color,
    isLaneHeader: row.type === 'lane',
  }))
  const barData = rows
    .map((row, rowIndex) => row.type === 'task' ? taskBarData(row.task, rowIndex, row.group) : null)
    .filter(Boolean)

  return makeOption(yAxisData, barData, maxTime, {
    gridLeft: 260,
    rowLabels,
    tooltipFormatter: (p) => taskTooltip(p.data?.task, p.data?.label, p.data?.group),
    extraSeries: [
      {
        type: 'custom',
        name: '泳道背景',
        renderItem: renderLaneBackground,
        encode: { x: [1, 2], y: 0 },
        data: backgroundData,
        silent: true,
        z: 0,
      },
    ],
  })
}

function taskBarData(task, rowIndex, group = null) {
  const role = task.step_role ?? 'normal'
  const color = ROLE_COLORS[role] ?? ROLE_COLORS.normal
  const critical = isCriticalPath(task)
  const label = formatNormalLabel(task, critical)
  return {
    value: [rowIndex, task.start_min, task.end_min],
    task,
    group,
    label,
    itemStyle: {
      color,
      borderColor: critical ? '#f59e0b' : color,
      borderWidth: critical ? 2 : 0,
    },
  }
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
      task: s,
      label: categories[i],
      itemStyle: { color: ROLE_COLORS[role] ?? ROLE_COLORS.normal },
    }
  }).filter(Boolean)

  const baseBars = steps.map((s, i) => {
    if (s.base_start == null) return null
    return {
      value: [i, s.base_start, s.base_end],
      task: s,
      label: categories[i],
      itemStyle: { color: 'rgba(148,163,184,0.45)' },
    }
  }).filter(Boolean)

  const maxEnd = Math.max(
    props.makespan,
    ...steps.map((s) => Math.max(s.new_end ?? 0, s.base_end ?? 0)),
    1,
  )

  return {
    ...makeOption(categories, newBars, maxEnd, {
      gridLeft: 170,
      tooltipFormatter: (p) => diffTooltip(p.data?.task, p.data?.label, p.seriesName),
    }),
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
    z: 2,
  }
}

function maxEndForTasks(tasks) {
  return Math.max(props.makespan, ...tasks.map((task) => task.end_min ?? 0), 1)
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

function taskTooltip(task, label, group) {
  if (!task) return ''
  const lines = [
    escapeHtml(label || formatNormalLabel(task, isCriticalPath(task))),
    formatTimeRange(task.start_min, task.end_min),
    `步骤状态: ${ROLE_LABELS[task.step_role ?? 'normal'] ?? task.step_role ?? 'normal'}`,
  ]
  const statePath = stateGroupPathLabel(task, group)
  if (statePath) lines.push(`状态包: ${escapeHtml(statePath)}`)
  const activityGroup = task.activity_group_code || task.activity_group_name
  if (activityGroup) lines.push(`活动组: ${escapeHtml(activityGroup)}`)
  const resources = formatResources(task.resources)
  if (resources) lines.push(`资源: ${escapeHtml(resources)}`)
  return lines.join('<br>')
}

function diffTooltip(task, label, seriesName) {
  if (!task) return ''
  const [start, end] = seriesName === '基准'
    ? [task.base_start, task.base_end]
    : [task.new_start, task.new_end]
  return [
    escapeHtml(label || formatDiffLabel(task)),
    `${seriesName}:`,
    formatTimeRange(start, end),
    `步骤状态: ${ROLE_LABELS[task.step_role ?? 'normal'] ?? task.step_role ?? 'normal'}`,
  ].join('<br>')
}

function formatResources(resources) {
  if (!Array.isArray(resources) || !resources.length) return ''
  return resources.map((item) => {
    if (typeof item === 'string') return item
    return item.resource_name || item.resource_code || item.name || item.code || ''
  }).filter(Boolean).join(' / ')
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function renderItem(params, api) {
  const categoryIndex = api.value(0)
  const start = api.coord([api.value(1), categoryIndex])
  const end = api.coord([api.value(2), categoryIndex])
  const height = api.size([0, 1])[1] * 0.58

  return {
    type: 'rect',
    shape: {
      x: start[0],
      y: start[1] - height / 2,
      width: Math.max(end[0] - start[0], 2),
      height,
      r: 3,
    },
    style: {
      ...api.style(),
      textFill: '#fff',
      fontSize: 11,
    },
  }
}

function renderLaneBackground(params, api) {
  const categoryIndex = api.value(0)
  const start = api.coord([api.value(1), categoryIndex])
  const end = api.coord([api.value(2), categoryIndex])
  const height = api.size([0, 1])[1] * 0.92
  const color = params.data?.color ?? '#64748b'
  const isLaneHeader = Boolean(params.data?.isLaneHeader)

  return {
    type: 'group',
    children: [
      {
        type: 'rect',
        shape: {
          x: start[0],
          y: start[1] - height / 2,
          width: Math.max(end[0] - start[0], 1),
          height,
        },
        style: {
          fill: toRgba(color, isLaneHeader ? 0.12 : 0.05),
        },
      },
      {
        type: 'rect',
        shape: {
          x: start[0],
          y: start[1] - height / 2,
          width: isLaneHeader ? 6 : 3,
          height,
        },
        style: {
          fill: color,
          opacity: isLaneHeader ? 0.9 : 0.45,
        },
      },
    ],
  }
}

function toRgba(hex, alpha) {
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!match) return hex
  const [, r, g, b] = match
  return `rgba(${parseInt(r, 16)}, ${parseInt(g, 16)}, ${parseInt(b, 16)}, ${alpha})`
}

function makeOption(categories, data, maxTime, options = {}) {
  const rowLabels = options.rowLabels ?? categories
  return {
    tooltip: {
      formatter: (p) => options.tooltipFormatter
        ? options.tooltipFormatter(p)
        : defaultTooltip(p, rowLabels),
    },
    grid: { left: options.gridLeft ?? 170, right: 24, top: 10, bottom: 32 },
    xAxis: {
      min: 0,
      max: maxTime,
      scale: true,
      axisLabel: { formatter: formatTimePoint },
    },
    yAxis: {
      data: categories,
      axisLabel: { width: (options.gridLeft ?? 170) - 24, overflow: 'truncate' },
      inverse: true,
    },
    series: [
      ...(options.extraSeries ?? []),
      makeSeries(data, '计划'),
    ],
  }
}

function defaultTooltip(p, labels) {
  const [idx, start, end] = p.value
  return `${labels[idx]}<br>${formatTimeRange(start, end)}`
}

function updateChart() {
  if (!chart) return
  chart.setOption(buildOption(), true)
  chart.resize()
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  updateChart()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})

watch(
  () => [
    props.tasks,
    props.laneMode,
    props.laneGroups,
    props.diffMode,
    props.diffSteps,
    props.criticalPath,
    props.makespan,
    props.timeMode,
    props.labelMode,
  ],
  () => nextTick(updateChart),
)
</script>

<style scoped>
.lane-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.lane-summary-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 360px;
  min-height: 26px;
  padding: 3px 8px;
  border-left: 4px solid;
  border-radius: 6px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
}

.lane-summary-code {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lane-summary-meta {
  flex: 0 0 auto;
  color: #64748b;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #475569;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
}
</style>
