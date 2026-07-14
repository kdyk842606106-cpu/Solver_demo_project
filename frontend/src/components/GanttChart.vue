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
    <div
      v-if="markerLegend.length || shiftLegend.length"
      class="legend presentation-legend"
      aria-label="甘特图例"
      data-testid="gantt-presentation-legend"
    >
      <div class="presentation-legend-title">甘特图例</div>
      <div
        v-if="markerLegend.length"
        class="presentation-legend-row"
        data-testid="gantt-marker-legend-section"
      >
        <span class="presentation-legend-label">作业标识</span>
        <span
          v-for="marker in markerLegend"
          :key="`marker-${marker.key}`"
          class="legend-item presentation-legend-item"
          data-testid="gantt-marker-legend-item"
        >
          <span
            class="marker-swatch"
            :style="{ background: marker.color, color: contrastTextColor(marker.color) }"
          >{{ marker.text }}</span>
          {{ marker.ruleNames.join(' / ') }}
        </span>
      </div>
      <div
        v-if="shiftLegend.length"
        class="presentation-legend-row"
        data-testid="gantt-shift-legend-section"
      >
        <span class="presentation-legend-label">班次</span>
        <span
          v-for="shift in shiftLegend"
          :key="`shift-${shift.key}`"
          class="legend-item presentation-legend-item"
          data-testid="gantt-shift-legend-item"
        >
          <span class="shift-swatch" :style="{ background: shift.color }" />
          {{ shift.detailLabel }}
        </span>
      </div>
    </div>
    <div class="sr-only" data-testid="gantt-accessibility-summary">
      <span v-for="(task, index) in presentationTasks" :key="task.step_order ?? task.op_rule_code ?? index">
        {{ accessibilityTaskSummary(task) }}
      </span>
    </div>
    <div
      ref="chartEl"
      data-testid="gantt-chart-canvas"
      :style="{ width: '100%', height: chartHeight + 'px' }"
    />
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
  scheduleStartAt: { type: String, default: '' },
  rulePresentations: { type: Object, default: () => ({}) },
  selectionMode: { type: Boolean, default: false },
  selectedStepIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['toggle-task', 'brush-select'])

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
const SHIFT_COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#65a30d', '#db2777', '#ea580c', '#4f46e5', '#0d9488']

const chartEl = ref(null)
let chart = null
let resizeObserver = null
let selectableSeriesData = []
let selectableSeriesIndex = 0

const activeTasks = computed(() => {
  if (!props.laneMode) return props.tasks
  return props.laneGroups.flatMap((group) => group.tasks ?? [])
})

const presentationTasks = computed(() => (props.diffMode ? [] : activeTasks.value))

const shiftAxisIntervals = computed(() => presentationTasks.value.flatMap((task) => {
  const segments = task.gantt_shift_segments || task.segments || []
  return segments.map((segment) => ({
    start: Number(segment.start_min),
    end: Number(segment.end_min),
    shift: shiftDescriptor(segment),
  })).filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end) && item.shift)
}))

const shiftLegend = computed(() => {
  const byKey = new Map()
  for (const task of presentationTasks.value) {
    const segments = task.gantt_shift_segments || task.segments || []
    for (const segment of segments) {
      const shift = shiftDescriptor(segment)
      if (shift) byKey.set(shift.key, shift)
    }
  }
  return [...byKey.values()]
    .sort((left, right) => left.key.localeCompare(right.key))
    .map((shift, index) => ({ ...shift, color: SHIFT_COLORS[index % SHIFT_COLORS.length] }))
})

const shiftColorByKey = computed(() => new Map(
  shiftLegend.value.map((shift) => [shift.key, shift.color]),
))

const markerLegend = computed(() => {
  const byKey = new Map()
  for (const task of presentationTasks.value) {
    for (const marker of taskMarkers(task)) {
      const existing = byKey.get(marker.key)
      if (existing) {
        existing.ruleNames = [...new Set([...existing.ruleNames, ...marker.ruleNames])]
      } else {
        byKey.set(marker.key, { ...marker })
      }
    }
  }
  return [...byKey.values()].sort((left, right) => left.key.localeCompare(right.key))
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

  const data = sorted.flatMap((task, index) => taskBarData(task, index))
  selectableSeriesData = data
  selectableSeriesIndex = 0
  return makeOption(categories, data, maxEndForTasks(sorted), {
    gridLeft: 170,
    tooltipFormatter: (p) => taskTooltip(p.data?.task, p.data?.label, p.data?.group, p.data?.segment),
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
    .flatMap((row, rowIndex) => row.type === 'task' ? taskBarData(row.task, rowIndex, row.group) : [])
  selectableSeriesData = barData
  selectableSeriesIndex = 1

  return makeOption(yAxisData, barData, maxTime, {
    gridLeft: 260,
    rowLabels,
    tooltipFormatter: (p) => taskTooltip(p.data?.task, p.data?.label, p.data?.group, p.data?.segment),
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

function shiftDescriptor(segment) {
  if (!segment) return null
  const rawItems = Array.isArray(segment.shifts) && segment.shifts.length
    ? segment.shifts
    : segment.shift_code || segment.shift_name
      ? [{ shift_code: segment.shift_code, shift_name: segment.shift_name }]
      : []
  const items = rawItems
    .map((item) => ({
      code: String(item?.shift_code || '').trim(),
      name: String(item?.shift_name || '').trim(),
    }))
    .filter((item) => item.code || item.name)
  if (!items.length) return null
  const unique = [...new Map(items.map((item) => [`${item.code}|${item.name}`, item])).values()]
  const key = unique
    .map((item) => `${item.code}|${item.name}`)
    .sort()
    .join('&')
  const shortLabel = unique.map((item) => item.name || item.code).join(' ∩ ')
  const detailLabel = unique.map((item) =>
    item.name && item.code ? `${item.name} (${item.code})` : item.name || item.code,
  ).join(' ∩ ')
  return { key, shortLabel, detailLabel }
}

function taskMarkers(task) {
  const counts = task?.gantt_marker_counts
  const aggregate = !!counts && typeof counts === 'object'
  const ruleCodes = counts && typeof counts === 'object'
    ? Object.keys(counts)
    : task?.matched_scheduling_rules || []
  const byKey = new Map()
  for (const ruleCode of ruleCodes) {
    const presentation = props.rulePresentations?.[ruleCode]
    if (!presentation?.text) continue
    const text = String(presentation.text).trim()
    if (!text) continue
    const color = presentation.color || '#f59e0b'
    const key = `${text}|${color}`
    const count = Math.max(1, Number(counts?.[ruleCode] || 1))
    const ruleName = presentation.rule_name || ruleCode
    const existing = byKey.get(key)
    if (existing) {
      existing.count = Math.max(existing.count, count)
      existing.aggregate = existing.aggregate || aggregate
      existing.ruleNames = [...new Set([...existing.ruleNames, ruleName])]
    } else {
      byKey.set(key, { key, text, color, count, aggregate, ruleNames: [ruleName] })
    }
  }
  return [...byKey.values()]
}

function accessibilityTaskSummary(task) {
  const label = formatNormalLabel(task, isCriticalPath(task))
  const markers = taskMarkers(task).map((marker) =>
    `${marker.text}${marker.aggregate || marker.count > 1 ? `×${marker.count}` : ''}`,
  )
  const segments = task.gantt_shift_segments || task.segments || []
  const shifts = [...new Map(
    segments.map(shiftDescriptor).filter(Boolean).map((shift) => [shift.key, shift]),
  ).values()].map((shift) => shift.detailLabel)
  return [label, markers.length ? `甘特标识 ${markers.join(' / ')}` : '', shifts.length ? `班次 ${shifts.join(' / ')}` : '']
    .filter(Boolean)
    .join('；')
}

function taskBarData(task, rowIndex, group = null) {
  const role = task.step_role ?? 'normal'
  const color = ROLE_COLORS[role] ?? ROLE_COLORS.normal
  const critical = isCriticalPath(task)
  const label = formatNormalLabel(task, critical)
  const segments = Array.isArray(task.segments) && task.segments.length
    ? task.segments
    : [{ start_min: task.start_min, end_min: task.end_min, segment_index: 1 }]
  const markers = taskMarkers(task)
  return segments.map((segment, segmentArrayIndex) => {
    const shift = shiftDescriptor(segment)
    return {
      value: [rowIndex, segment.start_min, segment.end_min],
      task,
      segment,
      shift,
      shiftColor: shift ? shiftColorByKey.value.get(shift.key) : null,
      markers: segmentArrayIndex === 0 ? markers : [],
      group,
      label,
      itemStyle: {
        color,
        borderColor: props.selectedStepIds.includes(task.step_id)
          ? '#2563eb'
          : critical ? '#f59e0b' : color,
        borderWidth: props.selectedStepIds.includes(task.step_id) ? 4 : critical ? 2 : 0,
      },
    }
  })
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
    renderItem: (params, api) => renderItem(params, api, data[params.dataIndex]),
    encode: { x: [1, 2], y: 0 },
    data,
    z: 2,
  }
}

function maxEndForTasks(tasks) {
  return Math.max(props.makespan, ...tasks.map((task) => task.end_min ?? 0), 1)
}

function formatTimePoint(value) {
  if (props.timeMode === 'datetime' && props.scheduleStartAt) {
    const date = new Date(new Date(props.scheduleStartAt).getTime() + Number(value) * 60000)
    return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  }
  if (props.timeMode !== 'day') return `${value}m`
  return `D${Math.floor(value / props.dayMinutes) + 1}`
}

function shiftLabelsAtTime(value) {
  const labels = new Set()
  const isScheduleEnd = value === Number(props.makespan)
  for (const interval of shiftAxisIntervals.value) {
    const contains = value >= interval.start && value < interval.end
    const closesSchedule = isScheduleEnd && value === interval.end
    if (contains || closesSchedule) labels.add(interval.shift.shortLabel)
  }
  return [...labels].sort().join(' / ')
}

function formatTimeAxisLabel(value) {
  const time = formatTimePoint(value)
  const shifts = shiftLabelsAtTime(Number(value))
  return shifts ? `${time}\n${shifts}` : time
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

function taskTooltip(task, label, group, segment) {
  if (!task) return ''
  const lines = [
    escapeHtml(label || formatNormalLabel(task, isCriticalPath(task))),
    formatTimeRange(task.start_min, task.end_min),
    `步骤状态: ${ROLE_LABELS[task.step_role ?? 'normal'] ?? task.step_role ?? 'normal'}`,
  ]
  if (task.start_at && task.end_at) {
    lines.push(`绝对时间: ${escapeHtml(task.start_at)} → ${escapeHtml(task.end_at)}`)
    lines.push(`工作量: ${task.duration_min} min / 实际历时: ${task.elapsed_min ?? task.end_min - task.start_min} min`)
    if (task.calendar_pause_min) lines.push(`日历暂停: ${task.calendar_pause_min} min / 片段: ${task.segments?.length ?? 1}`)
  }
  if (segment?.shift_name || segment?.shift_code) {
    const shift = segment.shift_name && segment.shift_code
      ? `${segment.shift_name} (${segment.shift_code})`
      : segment.shift_name || segment.shift_code
    lines.push(`班次: ${escapeHtml(shift)}`)
  } else if (Array.isArray(segment?.shifts) && segment.shifts.length) {
    lines.push(`班次: ${escapeHtml(segment.shifts.map((item) => item.shift_name || item.shift_code).filter(Boolean).join(' ∩ '))}`)
  }
  const markers = taskMarkers(task)
  if (markers.length) {
    lines.push(`甘特标识: ${escapeHtml(markers.map((marker) => {
      const count = marker.aggregate || marker.count > 1 ? `×${marker.count}` : ''
      return `${marker.text}${count}（${marker.ruleNames.join(' / ')}）`
    }).join(' / '))}`)
  }
  if (!segment && Array.isArray(task.gantt_shift_segments)) {
    const shifts = [...new Map(
      task.gantt_shift_segments
        .map(shiftDescriptor)
        .filter(Boolean)
        .map((shift) => [shift.key, shift]),
    ).values()]
    if (shifts.length) {
      lines.push(`班次汇总: ${escapeHtml(shifts.map((shift) => shift.detailLabel).join(' / '))}`)
    }
  }
  const statePath = stateGroupPathLabel(task, group)
  if (statePath) lines.push(`状态包: ${escapeHtml(statePath)}`)
  const activityGroup = task.activity_group_code || task.activity_group_name
  if (activityGroup) lines.push(`活动组: ${escapeHtml(activityGroup)}`)
  if (task.responsible_subsystem) lines.push(`责任子系统: ${escapeHtml(task.responsible_subsystem)}`)
  if (Array.isArray(task.effect_dimension_keys) && task.effect_dimension_keys.length) {
    lines.push(`效果维度: ${escapeHtml(task.effect_dimension_keys.join(' / '))}`)
  }
  if (Array.isArray(task.matched_scheduling_rules) && task.matched_scheduling_rules.length) {
    lines.push(`命中规则: ${escapeHtml(task.matched_scheduling_rules.join(' / '))}`)
  }
  if (Array.isArray(task.scheduling_rule_violations) && task.scheduling_rule_violations.length) {
    lines.push(`软规则违反: ${task.scheduling_rule_violations.length}`)
  }
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

function renderItem(params, api, sourceData = null) {
  const categoryIndex = api.value(0)
  const start = api.coord([api.value(1), categoryIndex])
  const end = api.coord([api.value(2), categoryIndex])
  const height = api.size([0, 1])[1] * 0.58
  const width = Math.max(end[0] - start[0], 2)
  const top = start[1] - height / 2
  const data = sourceData || {}
  const children = [
    {
      type: 'rect',
      shape: { x: start[0], y: top, width, height, r: 3 },
      style: { ...api.style() },
    },
  ]

  if (data.shiftColor) {
    children.push({
      type: 'rect',
      shape: {
        x: start[0] + 1,
        y: top + 1,
        width: Math.max(width - 2, 1),
        height: Math.min(4, Math.max(height - 2, 1)),
        r: [2, 2, 0, 0],
      },
      style: { fill: data.shiftColor },
    })
  }

  let contentOffset = 4
  for (const marker of data.markers || []) {
    const markerLabel = marker.aggregate || marker.count > 1 ? `${marker.text}×${marker.count}` : marker.text
    const markerWidth = Math.max(18, markerLabel.length * 11 + 8)
    children.push({
      type: 'rect',
      shape: {
        x: start[0] + contentOffset,
        y: start[1] - 9,
        width: markerWidth,
        height: 18,
        r: 5,
      },
      style: {
        fill: marker.color,
        stroke: 'rgba(255,255,255,.9)',
        lineWidth: 1,
      },
    })
    children.push({
      type: 'text',
      style: {
        x: start[0] + contentOffset + markerWidth / 2,
        y: start[1],
        text: markerLabel,
        fill: contrastTextColor(marker.color),
        font: '600 11px sans-serif',
        align: 'center',
        verticalAlign: 'middle',
      },
    })
    contentOffset += markerWidth + 4
  }

  return { type: 'group', children }
}

function contrastTextColor(color) {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color || '')
  if (!match) return '#ffffff'
  const luminance = (
    Number.parseInt(match[1], 16) * 0.299
    + Number.parseInt(match[2], 16) * 0.587
    + Number.parseInt(match[3], 16) * 0.114
  )
  return luminance > 155 ? '#1f2937' : '#ffffff'
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
    toolbox: props.selectionMode ? {
      right: 12,
      feature: {
        brush: {
          type: ['rect', 'clear'],
          title: { rect: '框选活动', clear: '清除框选图形' },
        },
      },
    } : undefined,
    brush: props.selectionMode
      ? { brushMode: 'multiple', throttleType: 'debounce', throttleDelay: 120 }
      : undefined,
    grid: { left: options.gridLeft ?? 170, right: 24, top: 10, bottom: shiftLegend.value.length ? 52 : 32 },
    xAxis: {
      min: 0,
      max: maxTime,
      scale: true,
      axisLabel: { formatter: formatTimeAxisLabel, lineHeight: 16, hideOverlap: true },
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

function normalizeBrushRange(range) {
  if (!Array.isArray(range) || range.length < 2) return null
  const xRange = range[0]
  const yRange = range[1]
  if (!Array.isArray(xRange) || !Array.isArray(yRange)) return null
  return {
    xMin: Math.min(Number(xRange[0]), Number(xRange[1])),
    xMax: Math.max(Number(xRange[0]), Number(xRange[1])),
    yMin: Math.min(Number(yRange[0]), Number(yRange[1])),
    yMax: Math.max(Number(yRange[0]), Number(yRange[1])),
  }
}

function selectableRowHalfHeight() {
  const rowIndexes = [...new Set(selectableSeriesData.map((item) => Number(item.value?.[0])))]
  const centers = rowIndexes
    .map((rowIndex) => chart?.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [0, rowIndex])?.[1])
    .filter(Number.isFinite)
    .sort((left, right) => left - right)
  const spacings = centers.slice(1).map((center, index) => center - centers[index]).filter((value) => value > 0)
  const rowSpacing = spacings.length ? Math.min(...spacings) : 28
  return rowSpacing * 0.29
}

function stepIdsIntersectingBrushAreas(areas = []) {
  if (!chart) return []
  const stepIds = new Set()
  const halfHeight = selectableRowHalfHeight()
  for (const area of areas) {
    if (area?.brushType !== 'rect') continue
    const brush = normalizeBrushRange(area.range)
    if (!brush) continue
    for (const item of selectableSeriesData) {
      const [rowIndex, startMin, endMin] = item.value || []
      const start = chart.convertToPixel(
        { xAxisIndex: 0, yAxisIndex: 0 },
        [Number(startMin), Number(rowIndex)],
      )
      const end = chart.convertToPixel(
        { xAxisIndex: 0, yAxisIndex: 0 },
        [Number(endMin), Number(rowIndex)],
      )
      if (!Array.isArray(start) || !Array.isArray(end)) continue
      const bar = {
        xMin: Math.min(start[0], end[0]),
        xMax: Math.max(start[0], end[0]),
        yMin: start[1] - halfHeight,
        yMax: start[1] + halfHeight,
      }
      const intersects = bar.xMax >= brush.xMin
        && bar.xMin <= brush.xMax
        && bar.yMax >= brush.yMin
        && bar.yMin <= brush.yMax
      const stepId = item.task?.step_id
      if (intersects && stepId != null) stepIds.add(stepId)
    }
  }
  return [...stepIds]
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  chart.on('click', (params) => {
    if (!props.selectionMode) return
    const stepId = params?.data?.task?.step_id
    if (stepId != null) emit('toggle-task', stepId)
  })
  chart.on('brushSelected', (params) => {
    if (!props.selectionMode) return
    const batch = params?.batch?.[0] || {}
    const selected = batch.selected || []
    const stepIds = new Set()
    for (const series of selected) {
      if (series.seriesIndex !== selectableSeriesIndex) continue
      for (const dataIndex of series.dataIndex || []) {
        const stepId = selectableSeriesData[dataIndex]?.task?.step_id
        if (stepId != null) stepIds.add(stepId)
      }
    }
    for (const stepId of stepIdsIntersectingBrushAreas(batch.areas || [])) stepIds.add(stepId)
    if (stepIds.size) emit('brush-select', [...stepIds])
  })
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
    props.scheduleStartAt,
    props.rulePresentations,
    props.selectionMode,
    props.selectedStepIds,
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

.presentation-legend {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.97);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.presentation-legend-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
}

.presentation-legend-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
}

.presentation-legend-label {
  flex: 0 0 64px;
  color: #334155;
  font-weight: 600;
}

.presentation-legend-item {
  padding: 2px 0;
}

.marker-swatch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 4px;
  border-radius: 5px;
  color: #1f2937;
  font-weight: 700;
}

.shift-swatch {
  display: inline-block;
  width: 24px;
  height: 5px;
  border-radius: 3px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
