<template>
  <div class="calendar-page">
    <el-row :gutter="16">
      <el-col :span="9">
        <el-card>
          <template #header>工作日历模板</template>
          <el-form :model="form" label-width="80px">
            <el-form-item label="编码"><el-input v-model="form.code" :disabled="Boolean(editId)" /></el-form-item>
            <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
            <el-form-item label="时区"><el-input v-model="form.timezone" placeholder="Asia/Shanghai" /></el-form-item>
            <el-form-item label="启用"><el-switch v-model="form.is_active" :disabled="editingSystemDefault" /></el-form-item>
          </el-form>
          <div class="weekly-schedules">
            <div v-for="(schedule, scheduleIndex) in form.weekly_schedules" :key="schedule.key" class="schedule-group">
              <div class="shift-fields">
                <el-input v-model="schedule.shift_code" placeholder="班次编码，如 DAY_SHIFT" />
                <el-input v-model="schedule.shift_name" placeholder="班次名称，如 白班" />
              </div>
              <div class="schedule-header">
                <span class="section-label">工作日</span>
                <el-checkbox-group v-model="schedule.weekdays" size="small">
                  <el-checkbox-button v-for="day in weekdayOptions" :key="day.value" :value="day.value">
                    {{ day.label }}
                  </el-checkbox-button>
                </el-checkbox-group>
                <el-button link type="danger" @click="removeSchedule(scheduleIndex)">删除班次组</el-button>
              </div>
              <div class="time-section-title">工作时间段</div>
              <el-table :data="schedule.windows" size="small" border max-height="220">
                <el-table-column label="开始"><template #default="{ row }"><el-time-select v-model="row.start_time" start="00:00" step="00:30" end="23:30" /></template></el-table-column>
                <el-table-column label="结束"><template #default="{ row }"><el-time-select v-model="row.end_time" start="00:30" step="00:30" end="23:59" /></template></el-table-column>
                <el-table-column label="跨日" width="62"><template #default="{ row }"><el-switch v-model="row.spans_next_day" /></template></el-table-column>
                <el-table-column width="54"><template #default="{ $index }"><el-button link type="danger" @click="schedule.windows.splice($index, 1)">删</el-button></template></el-table-column>
              </el-table>
              <el-button class="row-action" @click="addWindow(schedule)">增加时间段</el-button>
            </div>
          </div>
          <el-button class="row-action" plain @click="addSchedule">增加不同班次组</el-button>
          <el-form-item label="日期例外" class="exception-field">
            <el-input v-model="exceptionsJson" type="textarea" :rows="5" placeholder='JSON，例如 [{"date":"2026-10-01","mode":"closed","windows":[]}]' />
          </el-form-item>
          <div class="actions">
            <el-button type="primary" :loading="saving" @click="saveCalendar">保存新版本</el-button>
            <el-button @click="resetCalendar">清空</el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :span="15">
        <el-card>
          <template #header>日历列表</template>
          <el-table :data="calendars" size="small" border>
            <el-table-column prop="code" label="编码" width="130" />
            <el-table-column prop="name" label="名称" />
            <el-table-column label="默认" width="90"><template #default="{ row }"><el-tag v-if="row.is_system_default" type="warning">系统默认</el-tag><span v-else>-</span></template></el-table-column>
            <el-table-column label="时区" width="130"><template #default="{ row }">{{ row.current_revision?.timezone || '-' }}</template></el-table-column>
            <el-table-column label="版本" width="70"><template #default="{ row }">v{{ row.current_revision?.revision_no || 0 }}</template></el-table-column>
            <el-table-column label="状态" width="70"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
            <el-table-column label="操作" width="180"><template #default="{ row }"><el-button size="small" @click="editCalendar(row)">编辑</el-button><el-button v-if="!row.is_system_default" link type="primary" @click="makeSystemDefault(row)">设为默认</el-button></template></el-table-column>
          </el-table>
        </el-card>

        <el-card class="policy-card">
          <template #header>机器日历策略</template>
          <el-form label-width="110px">
            <el-form-item label="具体机器">
              <el-select v-model="machineId" filterable @change="loadPolicy" style="width:100%">
                <el-option v-for="item in machines" :key="item.id" :value="item.id" :label="`${item.name} (${item.code})`" />
              </el-select>
            </el-form-item>
            <el-form-item label="默认日历">
              <el-select v-model="defaultCalendarId" clearable placeholder="继承系统默认" style="width:100%">
                <el-option v-for="item in activeCalendars" :key="item.id" :value="item.id" :label="`${item.name} (${item.code})`" />
              </el-select>
              <div v-if="inheritsSystemDefault && effectiveDefaultCalendar" class="inherit-hint">当前继承：{{ effectiveDefaultCalendar.name }}</div>
            </el-form-item>
          </el-form>
          <el-table :data="dimensionRows" size="small" border>
            <el-table-column prop="feature_name" label="状态维度模板" />
            <el-table-column prop="feature_key" label="维度键" />
            <el-table-column label="工作日历" width="220">
              <template #default="{ row }">
                <el-select v-model="row.work_calendar_id" clearable style="width:100%">
                  <el-option v-for="item in activeCalendars" :key="item.id" :value="item.id" :label="item.name" />
                </el-select>
              </template>
            </el-table-column>
          </el-table>
          <el-button class="row-action" type="primary" :disabled="!machineId" @click="savePolicy">保存机器策略</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createWorkCalendar,
  getFeatureDefs,
  getMachineCalendarPolicy,
  getMachines,
  getWorkCalendars,
  setSystemDefaultWorkCalendar,
  updateMachineCalendarPolicy,
  updateWorkCalendar,
} from '../../api/masterData'

const weekdayOptions = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' },
]

let scheduleKey = 0
const newSchedule = (weekdays = [], windows = [], shiftCode = '', shiftName = '') => ({
  key: ++scheduleKey,
  weekdays,
  windows,
  shift_code: shiftCode,
  shift_name: shiftName,
})
const emptyForm = () => ({
  code: '',
  name: '',
  timezone: 'Asia/Shanghai',
  is_active: true,
  weekly_schedules: [newSchedule([1, 2, 3, 4, 5])],
  date_exceptions: [],
})
const calendars = ref([])
const machines = ref([])
const form = ref(emptyForm())
const editId = ref(null)
const exceptionsJson = ref('[]')
const saving = ref(false)
const machineId = ref(null)
const defaultCalendarId = ref(null)
const dimensionRows = ref([])
const inheritsSystemDefault = ref(false)
const effectiveDefaultCalendarId = ref(null)
const activeCalendars = computed(() => calendars.value.filter((item) => item.is_active))
const editingSystemDefault = computed(() => Boolean(editId.value && calendars.value.find((item) => item.id === editId.value)?.is_system_default))
const effectiveDefaultCalendar = computed(() => calendars.value.find((item) => item.id === effectiveDefaultCalendarId.value))
const cloneJson = (value) => JSON.parse(JSON.stringify(value))

function addSchedule() {
  form.value.weekly_schedules.push(newSchedule())
}

function removeSchedule(index) {
  form.value.weekly_schedules.splice(index, 1)
  if (!form.value.weekly_schedules.length) addSchedule()
}

function addWindow(schedule) {
  schedule.windows.push({ start_time: '08:00', end_time: '17:00', spans_next_day: false })
}

function groupWeeklyWindows(windows) {
  const byShiftAndWeekday = new Map()
  for (const item of windows) {
    const shiftKey = JSON.stringify([item.shift_code || '', item.shift_name || ''])
    const key = `${shiftKey}:${item.weekday}`
    if (!byShiftAndWeekday.has(key)) byShiftAndWeekday.set(key, { shiftKey, weekday: item.weekday, windows: [] })
    byShiftAndWeekday.get(key).windows.push({
      start_time: item.start_time,
      end_time: item.end_time,
      spans_next_day: Boolean(item.spans_next_day),
    })
  }
  const groups = new Map()
  for (const { shiftKey, weekday, windows: dayWindows } of [...byShiftAndWeekday.values()].sort((a, b) => a.weekday - b.weekday)) {
    dayWindows.sort((a, b) => `${a.start_time}-${a.end_time}`.localeCompare(`${b.start_time}-${b.end_time}`))
    const signature = `${shiftKey}:${JSON.stringify(dayWindows)}`
    const [shiftCode, shiftName] = JSON.parse(shiftKey)
    if (!groups.has(signature)) groups.set(signature, newSchedule([], dayWindows, shiftCode, shiftName))
    groups.get(signature).weekdays.push(weekday)
  }
  return [...groups.values()]
}

function expandWeeklySchedules() {
  const weeklyWindows = []
  for (const schedule of form.value.weekly_schedules) {
    if (!schedule.weekdays.length || !schedule.windows.length) continue
    for (const weekday of schedule.weekdays) {
      for (const window of schedule.windows) weeklyWindows.push({
        weekday,
        ...window,
        ...(schedule.shift_code ? { shift_code: schedule.shift_code } : {}),
        ...(schedule.shift_name ? { shift_name: schedule.shift_name } : {}),
      })
    }
  }
  return weeklyWindows.sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time))
}

async function load() {
  ;[calendars.value, machines.value] = await Promise.all([getWorkCalendars(), getMachines()])
}

async function makeSystemDefault(row) {
  await setSystemDefaultWorkCalendar(row.id)
  ElMessage.success(`${row.name} 已设为系统默认日历`)
  await load()
}

function editCalendar(row) {
  editId.value = row.id
  const weeklySchedules = groupWeeklyWindows(cloneJson(row.current_revision?.weekly_windows || []))
  form.value = {
    code: row.code,
    name: row.name,
    timezone: row.current_revision?.timezone || 'Asia/Shanghai',
    is_active: row.is_active,
    weekly_schedules: weeklySchedules.length ? weeklySchedules : [newSchedule()],
    date_exceptions: cloneJson(row.current_revision?.date_exceptions || []),
  }
  exceptionsJson.value = JSON.stringify(form.value.date_exceptions, null, 2)
}

function resetCalendar() {
  editId.value = null
  form.value = emptyForm()
  exceptionsJson.value = '[]'
}

async function saveCalendar() {
  let exceptions
  try { exceptions = JSON.parse(exceptionsJson.value || '[]') } catch { return ElMessage.error('日期例外 JSON 格式错误') }
  let weeklyWindows
  try { weeklyWindows = expandWeeklySchedules() } catch (error) { return ElMessage.error(error.message) }
  if (!weeklyWindows.length) return ElMessage.error('请至少选择一个工作日并配置一个工作时间段')
  const payload = {
    code: form.value.code,
    name: form.value.name,
    timezone: form.value.timezone,
    is_active: form.value.is_active,
    weekly_windows: weeklyWindows,
    date_exceptions: exceptions,
  }
  saving.value = true
  try {
    if (editId.value) {
      const { code, ...updatePayload } = payload
      await updateWorkCalendar(editId.value, updatePayload)
    } else {
      await createWorkCalendar(payload)
    }
    ElMessage.success('工作日历已保存为新版本')
    resetCalendar()
    await load()
  } finally { saving.value = false }
}

async function loadPolicy() {
  const machine = machines.value.find((item) => item.id === machineId.value)
  if (!machine) return
  const [policy, features] = await Promise.all([
    getMachineCalendarPolicy(machine.id),
    getFeatureDefs(machine.machine_type_id),
  ])
  const bindings = new Map((policy.dimension_bindings || []).map((item) => [item.state_dimension_template_id, item.work_calendar_id]))
  defaultCalendarId.value = policy.default_work_calendar_id
  effectiveDefaultCalendarId.value = policy.effective_default_work_calendar_id
  inheritsSystemDefault.value = policy.inherits_system_default
  dimensionRows.value = features
    .filter((item) => item.is_dimension_template)
    .map((item) => ({ ...item, work_calendar_id: bindings.get(item.id) || null }))
}

async function savePolicy() {
  await updateMachineCalendarPolicy(machineId.value, {
    default_work_calendar_id: defaultCalendarId.value,
    dimension_bindings: dimensionRows.value
      .filter((item) => item.work_calendar_id)
      .map((item) => ({ state_dimension_template_id: item.id, work_calendar_id: item.work_calendar_id })),
  })
  await loadPolicy()
  ElMessage.success('机器日历策略已保存')
}

onMounted(load)
</script>

<style scoped>
.calendar-page { padding: 4px; }
.policy-card { margin-top: 16px; }
.weekly-schedules { display: flex; flex-direction: column; gap: 12px; }
.schedule-group { padding: 12px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-fill-color-blank); }
.schedule-header { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.shift-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
.section-label { color: var(--el-text-color-regular); font-size: 14px; white-space: nowrap; }
.time-section-title { margin-bottom: 8px; color: var(--el-text-color-regular); font-size: 14px; }
.row-action { margin-top: 12px; }
.exception-field { margin-top: 14px; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.inherit-hint { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>
