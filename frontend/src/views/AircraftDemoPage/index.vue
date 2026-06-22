<template>
  <div class="aircraft-demo">
    <div class="page-head">
      <div>
        <h2>飞机总装计划排期对比</h2>
        <div class="muted">原计划排期与二次变更后的自动优化排期并列展示，包含人员、设备和空间资源约束。</div>
      </div>
      <el-tag type="primary" effect="light">飞机总装 Mock 演示</el-tag>
    </div>

    <el-row :gutter="16" class="metric-row">
      <el-col :span="6">
        <el-card class="metric-card">
          <el-statistic title="原计划总工期" :value="days(initialResponse.schedule.makespan)">
            <template #suffix>天</template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="metric-card">
          <el-statistic title="机械顺延参考" :value="days(mechanicalResponse.schedule.makespan)">
            <template #suffix>天</template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="metric-card">
          <el-statistic title="调整后总工期" :value="days(optimizedResponse.schedule.makespan)">
            <template #suffix>天</template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="metric-card">
          <el-statistic title="相对机械顺延缩短" :value="savedDays">
            <template #suffix>天</template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="summary-card">
      <template #header>二次变更说明</template>
      <el-row :gutter="16">
        <el-col :span="6">
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="设备">{{ machine.name }} ({{ machine.code }})</el-descriptions-item>
            <el-descriptions-item label="当前状态">{{ currentState.label }}</el-descriptions-item>
            <el-descriptions-item label="目标状态">{{ targetState.label }}</el-descriptions-item>
          </el-descriptions>
        </el-col>
        <el-col :span="18">
          <div class="change-grid">
            <div class="change-item">
              <el-tag type="danger">插入</el-tag>
              <span>新增机身密封返修，工期 2 天，需要在全机通电检查前完成。</span>
            </div>
            <div class="change-item">
              <el-tag type="warning">约束</el-tag>
              <span>发动机吊装施加 not_before = D11。</span>
            </div>
            <div class="change-item">
              <el-tag type="primary">提拉</el-tag>
              <span>航电机架安装不依赖发动机吊装，被自动提拉到 D8-D9。</span>
            </div>
            <div class="change-item">
              <el-tag type="success">空间</el-tag>
              <span>同一空间同一时间只能执行一个活动，前机身电子舱空间内的作业被串行安排。</span>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <section
      v-for="page in schedulePages"
      :key="page.key"
      class="schedule-page"
    >
      <div class="schedule-page-title">
        <div>
          <h3>{{ page.title }}</h3>
          <div class="muted">{{ page.description }}</div>
        </div>
        <el-space>
          <el-tag :type="page.tagType">{{ page.badge }}</el-tag>
          <el-tag effect="plain">总工期 {{ days(page.response.schedule.makespan) }} 天</el-tag>
        </el-space>
      </div>

      <el-card class="gantt-card">
        <template #header>排程 Gantt</template>
        <GanttChart
          :tasks="page.response.schedule.tasks"
          :makespan="page.response.schedule.makespan"
          :critical-path="page.response.critical_path"
          time-mode="day"
          label-mode="order-name"
          :day-minutes="DAY_MINUTES"
        />
      </el-card>

      <el-card class="table-card">
        <template #header>任务明细</template>
        <el-table :data="page.response.schedule.tasks" size="small" border stripe>
          <el-table-column prop="step_order" label="任务序号" width="86" />
          <el-table-column prop="op_rule_name" label="活动名称" min-width="190" show-overflow-tooltip />
          <el-table-column label="开始" width="70">
            <template #default="{ row }">{{ dayPoint(row.start_min) }}</template>
          </el-table-column>
          <el-table-column label="结束" width="70">
            <template #default="{ row }">{{ dayEnd(row.end_min) }}</template>
          </el-table-column>
          <el-table-column label="工期" width="70">
            <template #default="{ row }">{{ days(row.duration_min) }}天</template>
          </el-table-column>
          <el-table-column label="not_before" width="104">
            <template #default="{ row }">
              <span v-if="row.not_before != null">{{ dayPoint(row.not_before) }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="人员/设备资源" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ formatWorkResources(row.resources) }}</template>
          </el-table-column>
          <el-table-column label="空间资源" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ formatSpaceResources(row.resources) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import GanttChart from '../../components/GanttChart.vue'
import {
  AIRCRAFT_DEMO_RESPONSES,
  DAY_MINUTES,
  getAircraftDemoMachines,
  getAircraftDemoStates,
} from '../../mock/aircraftAssemblyDemo'

const machines = ref([])
const statesResponse = ref({ states: [] })

const initialResponse = AIRCRAFT_DEMO_RESPONSES.initial
const mechanicalResponse = AIRCRAFT_DEMO_RESPONSES.mechanical
const optimizedResponse = AIRCRAFT_DEMO_RESPONSES.optimized

const schedulePages = computed(() => [
  {
    key: 'initial',
    title: '原计划排期页面',
    description: '计划未发生二次变更时，发动机吊装与航电机架安装在 D8-D9 并行执行；二者占用不同空间资源，总装交付检查在 D17 完成。',
    badge: '原计划',
    tagType: 'info',
    response: initialResponse,
  },
  {
    key: 'optimized',
    title: '计划调整后排期页面',
    description: '插入临时返修并施加 not_before 后，系统重新考虑人员、设备和空间资源约束；同属前机身电子舱空间的作业串行排布，总工期控制在 D19。',
    badge: '自动优化',
    tagType: 'success',
    response: optimizedResponse,
  },
])

const machine = computed(() => machines.value[0] ?? {})
const currentState = computed(() => statesResponse.value.states.find((s) => s.state_type === 'current') ?? {})
const targetState = computed(() => statesResponse.value.states.find((s) => s.state_type === 'target') ?? {})
const savedDays = computed(() => days(mechanicalResponse.schedule.makespan - optimizedResponse.schedule.makespan))

function days(minutes) {
  return Math.round(minutes / DAY_MINUTES)
}

function dayPoint(minutes) {
  return `D${Math.floor(minutes / DAY_MINUTES) + 1}`
}

function dayEnd(minutes) {
  return `D${Math.ceil(minutes / DAY_MINUTES)}`
}

function formatWorkResources(resources) {
  return (resources ?? [])
    .filter((r) => r.resource_type !== 'SPACE')
    .map((r) => r.resource_name ?? r.resource_code)
    .join(', ') || '-'
}

function formatSpaceResources(resources) {
  return (resources ?? [])
    .filter((r) => r.resource_type === 'SPACE')
    .map((r) => r.resource_name ?? r.resource_code)
    .join(', ') || '-'
}

onMounted(async () => {
  machines.value = await getAircraftDemoMachines()
  statesResponse.value = await getAircraftDemoStates()
})
</script>

<style scoped>
.aircraft-demo {
  color: #1f2937;
}

.page-head,
.schedule-page-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.page-head {
  margin-bottom: 16px;
}

h2,
h3 {
  margin: 0 0 6px;
}

.metric-row,
.summary-card,
.schedule-page {
  margin-top: 16px;
}

.metric-card {
  text-align: center;
}

.change-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.change-item {
  display: grid;
  grid-template-columns: 58px 1fr;
  align-items: start;
  gap: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.schedule-page {
  padding: 18px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.gantt-card,
.table-card {
  margin-top: 14px;
}

.muted {
  color: #64748b;
  font-size: 13px;
}
</style>
