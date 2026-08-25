<template>
  <div class="solve-workspace">
    <section class="solve-hero">
      <div>
        <p class="eyebrow">IMMUTABLE SHARED INPUT</p>
        <h1>多引擎求解</h1>
        <p>沿用原求解工作台的甘特图、活动网络和指标视图，输入统一切换为 Planner 场景快照。</p>
      </div>
      <el-tag :type="capabilities.planner_available ? 'success' : 'danger'">
        {{ capabilities.planner_available ? 'Planner 已连接' : 'Planner 未连接' }}
      </el-tag>
    </section>

    <section class="control-card">
      <el-form label-position="top" class="control-grid">
        <el-form-item label="场景">
          <el-select v-model="form.scenario_id" filterable style="width:100%" @change="loadScenario">
            <el-option v-for="item in scenarios" :key="item.id" :value="item.id" :label="`${item.display_code} · ${item.name}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="运行方式">
          <el-select v-model="form.engine" style="width:100%">
            <el-option label="全部对比" value="ALL" />
            <el-option label="旧引擎" value="LEGACY" />
            <el-option label="Anytime A*" value="ASTAR" />
            <el-option label="遗传算法 GA" value="GA" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间预算（秒）">
          <el-input-number v-model="form.budget.time_limit_seconds" :min="0.1" :max="120" :step="0.5" style="width:100%" />
        </el-form-item>
        <el-form-item label="随机种子">
          <el-input-number v-model="form.seed" style="width:100%" />
        </el-form-item>
      </el-form>
      <div class="run-actions">
        <div><span>资源模型</span><strong>容量汇总（不分配具体资源实例）</strong></div>
        <el-button type="primary" size="large" :disabled="!form.scenario_id || !capabilities.planner_available" :loading="running" @click="solve">开始求解</el-button>
      </div>
    </section>

    <el-empty v-if="!run" description="选择场景并启动求解" />
    <template v-else>
      <section class="run-summary">
        <div><span>运行状态</span><strong>{{ run.status }}</strong></div>
        <div><span>场景快照</span><code>{{ run.scenario_hash?.slice(0, 16) }}</code></div>
        <div><span>输入共享</span><strong>{{ run.result?.engines_share_mutable_state === false ? '隔离且一致' : '-' }}</strong></div>
        <div><span>场景版本</span><strong>r{{ scenarioDetails.revision || '-' }}</strong></div>
      </section>

      <section class="comparison-card">
        <header class="section-title"><div><h2>引擎结果对比</h2><p>同一不可变快照、同一 Validator 口径。</p></div></header>
        <el-table :data="engineRows" size="small" row-key="engine">
          <el-table-column prop="label" label="引擎" min-width="150" />
          <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag size="small" :type="row.pathCount ? 'success' : 'danger'">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="pathCount" label="合法方案" width="100" />
          <el-table-column prop="makespan" label="最短完工" width="100" />
          <el-table-column prop="executionCount" label="活动数" width="90" />
          <el-table-column prop="elapsed" label="耗时（秒）" width="120" />
          <el-table-column label="统一校验" width="110"><template #default="{ row }"><el-tag v-if="row.validator" size="small" type="success">{{ row.validator }}</el-tag><span v-else>-</span></template></el-table-column>
          <el-table-column label="查看" width="90"><template #default="{ row }"><el-button link type="primary" @click="activeEngine = row.engine">详情</el-button></template></el-table-column>
        </el-table>
      </section>

      <section class="result-card">
        <header class="result-header">
          <div><p class="eyebrow dark">SOLUTION WORKBENCH</p><h2>{{ engineLabel(activeEngine) }} · 方案详情</h2></div>
          <el-radio-group v-model="activeEngine" size="small">
            <el-radio-button v-for="item in engineRows" :key="item.engine" :value="item.engine">{{ item.label }}</el-radio-button>
          </el-radio-group>
        </header>

        <el-alert v-if="!activePresentation.path" :title="activePresentation.result?.error || activePresentation.result?.diagnosis?.error_message || '未找到合法方案'" type="error" :closable="false" show-icon />
        <template v-else>
          <div class="metric-strip">
            <div><span>总工期</span><strong>{{ activePresentation.makespan }}</strong></div>
            <div><span>活动数</span><strong>{{ activePresentation.tasks.length }}</strong></div>
            <div><span>资源峰值</span><strong>{{ activePresentation.resourcePeak }}</strong></div>
            <div><span>Validator</span><strong>{{ activePresentation.path.validator_status }}</strong></div>
          </div>

          <el-tabs v-model="activeResultTab" class="result-tabs">
            <el-tab-pane label="甘特图" name="gantt">
              <GanttChart :tasks="activePresentation.tasks" :makespan="activePresentation.makespan" :critical-path="activePresentation.criticalPath" time-mode="minute" />
            </el-tab-pane>
            <el-tab-pane label="活动网络图" name="network">
              <ActivityNetworkBoard :tasks="activePresentation.tasks" :makespan="activePresentation.makespan" :critical-path="activePresentation.criticalPath" />
            </el-tab-pane>
            <el-tab-pane label="执行明细" name="detail">
              <el-table :data="activePresentation.tasks" size="small" stripe>
                <el-table-column prop="step_order" label="#" width="55" />
                <el-table-column prop="op_code" label="活动编号" width="120" />
                <el-table-column prop="op_name" label="活动" min-width="180" />
                <el-table-column prop="start_min" label="开始" width="85" />
                <el-table-column prop="end_min" label="结束" width="85" />
                <el-table-column prop="duration_min" label="工期" width="85" />
                <el-table-column label="资源" min-width="180"><template #default="{ row }">{{ resourceLabel(row.resources) || '-' }}</template></el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="求解指标" name="metrics">
              <el-descriptions :column="3" border>
                <el-descriptions-item v-for="item in metricRows" :key="item.key" :label="item.label">{{ item.value }}</el-descriptions-item>
              </el-descriptions>
            </el-tab-pane>
          </el-tabs>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import GanttChart from '../../components/GanttChart.vue'
import ActivityNetworkBoard from '../../components/ActivityNetworkBoard.vue'
import { createPlannerRun, getPlannerCapabilities, getPlannerScenario, listPlannerScenarios } from '../../api/planner'
import { plannerPathToTasks } from '../PlannerData/plannerPresentation'

const scenarios = ref([])
const capabilities = ref({ planner_available: false })
const scenarioDetails = ref({ revision: 0, scenario: {} })
const running = ref(false)
const run = ref(null)
const activeEngine = ref('ASTAR')
const activeResultTab = ref('gantt')
const form = reactive({ scenario_id: '', engine: 'ALL', seed: 42, budget: { time_limit_seconds: 5, transition_limit: 20000, max_solutions: 10 } })
const results = computed(() => run.value?.result?.results || {})

const presentations = computed(() => Object.fromEntries(Object.entries(results.value).map(([engine, result]) => {
  const path = result.paths?.[0] || null
  const tasks = path ? plannerPathToTasks(path, scenarioDetails.value.scenario || {}) : []
  const makespan = Number(path?.metrics?.makespan ?? Math.max(0, ...tasks.map((item) => item.end_min)))
  return [engine, { engine, result, path, tasks, makespan, criticalPath: tasks.map((item) => item.op_code), resourcePeak: (path?.metrics?.resource_peak || []).reduce((total, item) => total + Number(item?.[1] || 0), 0) }]
})))

const engineRows = computed(() => Object.entries(results.value).map(([engine, result]) => {
  const path = result.paths?.[0]
  return { engine, label: engineLabel(engine), status: result.status, pathCount: result.paths?.length || 0, makespan: path?.metrics?.makespan ?? '-', executionCount: path?.metrics?.execution_count ?? path?.executions?.length ?? '-', elapsed: result.elapsed_seconds ?? '-', validator: path?.validator_status || '' }
}))

const activePresentation = computed(() => presentations.value[activeEngine.value] || { result: results.value[activeEngine.value], path: null, tasks: [], makespan: 0, criticalPath: [], resourcePeak: 0 })
const metricRows = computed(() => {
  const metrics = activePresentation.value.path?.metrics || {}
  const labels = { makespan: '总工期', execution_count: '活动数', critical_path_length: '关键路径长度', peak_parallelism: '峰值并行度', average_parallelism: '平均并行度', total_wait: '总等待', missing_goal_facts: '缺失目标事实', resource_utilization: '资源利用率', resource_peak: '资源峰值' }
  return Object.entries(metrics).filter(([key]) => labels[key]).map(([key, value]) => ({ key, label: labels[key], value: formatMetric(value) }))
})

onMounted(async () => {
  ;[scenarios.value, capabilities.value] = await Promise.all([listPlannerScenarios(), getPlannerCapabilities()])
  if (scenarios.value.length) {
    form.scenario_id = scenarios.value[0].id
    await loadScenario()
  }
})

async function loadScenario() {
  run.value = null
  if (!form.scenario_id) {
    scenarioDetails.value = { revision: 0, scenario: {} }
    return
  }
  scenarioDetails.value = await getPlannerScenario(form.scenario_id)
  const budget = scenarioDetails.value.scenario?.default_budget
  if (budget) Object.assign(form.budget, budget)
}

async function solve() {
  running.value = true
  try {
    run.value = await createPlannerRun(form)
    const resultEngines = Object.keys(results.value)
    activeEngine.value = resultEngines.find((engine) => results.value[engine]?.paths?.length) || resultEngines[0] || form.engine
    activeResultTab.value = 'gantt'
    if (run.value.status === 'OK') ElMessage.success('求解完成并通过统一校验')
    else ElMessage.warning('运行结束，请检查各引擎结果')
  } catch (error) {
    ElMessage.error(error?.response?.data?.error_message || error.message || '求解失败')
  } finally {
    running.value = false
  }
}

function engineLabel(engine) { return { LEGACY: '旧引擎', ASTAR: 'Anytime A*', GA: '遗传算法 GA' }[engine] || engine }
function resourceLabel(resources) { return (resources || []).map((item) => `${item.name}×${item.quantity || 1}`).join('、') }
function formatMetric(value) {
  if (Array.isArray(value)) return value.map((item) => Array.isArray(item) ? item.join('：') : String(item)).join('；') || '-'
  if (typeof value === 'number') return Number.isInteger(value) ? value : value.toFixed(3)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value ?? '-'
}
</script>

<style scoped>
.solve-workspace{display:grid;gap:16px}.solve-hero{display:flex;align-items:center;justify-content:space-between;padding:26px 30px;border-radius:18px;color:#fff;background:linear-gradient(130deg,#172554,#1e3a8a 62%,#0f766e);box-shadow:0 18px 45px rgba(30,58,138,.18)}.solve-hero h1{margin:3px 0 7px;font-size:28px}.solve-hero p{margin:0;color:#bfdbfe}.eyebrow{font-size:11px;letter-spacing:.16em;color:#5eead4!important}.eyebrow.dark{color:#0f766e!important}.control-card,.comparison-card,.result-card{padding:20px 22px;background:#fff;border:1px solid #e2e8f0;border-radius:14px}.control-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:14px}.run-actions,.result-header,.section-title{display:flex;align-items:center;justify-content:space-between;gap:16px}.run-actions{border-top:1px solid #e2e8f0;padding-top:14px}.run-actions div{display:flex;gap:10px;align-items:center}.run-actions span,.run-summary span,.metric-strip span,.section-title p{color:#64748b;font-size:12px}.run-summary{display:flex;gap:32px;flex-wrap:wrap;padding:14px 20px;border-radius:12px;background:#eff6ff;border:1px solid #bfdbfe}.run-summary div{display:flex;gap:8px;align-items:center}.section-title h2,.result-header h2{margin:0}.section-title p{margin:4px 0 14px}.result-header{margin-bottom:16px}.result-header .eyebrow{margin:0 0 4px}.metric-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}.metric-strip div{padding:12px;border:1px solid #dbeafe;border-radius:10px;background:#f8fbff;text-align:center}.metric-strip span{display:block}.metric-strip strong{font-size:20px;color:#1e3a8a}.result-tabs{min-height:360px}@media(max-width:1050px){.control-grid{grid-template-columns:1fr 1fr}.solve-hero,.result-header{align-items:flex-start;flex-direction:column}.metric-strip{grid-template-columns:1fr 1fr}}@media(max-width:700px){.control-grid,.metric-strip{grid-template-columns:1fr}.run-actions{align-items:flex-start;flex-direction:column}}
</style>
