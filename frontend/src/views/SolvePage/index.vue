<!-- 4-6: SolvePage — main orchestrator with state_delta, critical_path, version history, Gantt -->
<template>
  <div>
    <h2>求解</h2>
    <el-row :gutter="20">
      <!-- Left: Solve Form -->
      <el-col :span="8">
        <el-card>
          <template #header>发起求解</template>
          <el-form :model="solveForm" label-width="80px" @submit.prevent>
            <el-form-item label="设备" required>
              <el-select
                v-model="solveForm.machine_id"
                placeholder="请选择设备"
                style="width:100%"
                @change="onMachineChange"
              >
                <el-option
                  v-for="m in machines"
                  :key="m.id"
                  :label="`${m.name} (${m.code})`"
                  :value="m.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="当前状态" required>
              <el-select v-model="solveForm.current_state_id" placeholder="请选择" style="width:100%">
                <el-option
                  v-for="s in states"
                  :key="s.state_id"
                  :label="stateLabel(s)"
                  :value="s.state_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="目标状态" required>
              <el-select v-model="solveForm.target_state_id" placeholder="请选择" style="width:100%">
                <el-option
                  v-for="s in states"
                  :key="s.state_id"
                  :label="stateLabel(s)"
                  :value="s.state_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="优化目标">
              <el-tag type="info">最小化总工期</el-tag>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="solving"
                :disabled="!solveForm.machine_id"
                @click="runSolve"
              >
                开始求解
              </el-button>
              <el-button @click="loadMachines">刷新设备</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Version History -->
        <VersionHistory
          :chain="versionChain"
          :current-id="currentPlanId"
          style="margin-top:16px"
          @diff="onDiff"
          @load="onLoadVersion"
        />
      </el-col>

      <!-- Right: Results -->
      <el-col :span="16">
        <el-empty v-if="!solveResult" description="尚未执行求解" />

        <template v-else>
          <!-- Metrics row -->
          <el-row :gutter="16" style="margin-bottom:16px">
            <el-col :span="6">
              <el-card class="metric-card">
                <el-statistic title="总工期" :value="solveResult.schedule?.makespan ?? 0">
                  <template #suffix>分钟</template>
                </el-statistic>
              </el-card>
            </el-col>
            <el-col :span="18">
              <el-card>
                <div class="info-row">
                  <span class="info-label">状态变化</span>
                  <el-tag
                    v-for="d in stateDelta"
                    :key="d.feature_key"
                    type="info"
                    size="small"
                    style="margin-right:4px"
                  >
                    {{ d.feature_key }}: {{ d.from_value }} → {{ d.to_value }}
                  </el-tag>
                  <span v-if="!stateDelta.length" class="muted">无状态变化</span>
                </div>
                <div class="info-row" style="margin-top:8px">
                  <span class="info-label">关键路径</span>
                  <el-tag
                    v-for="op in criticalPath"
                    :key="op"
                    type="warning"
                    size="small"
                    style="margin-right:4px"
                  >
                    ★ {{ op }}
                  </el-tag>
                  <span v-if="!criticalPath.length" class="muted">—</span>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <!-- Diff mode banner -->
          <el-alert
            v-if="diffMode"
            type="info"
            show-icon
            :closable="true"
            style="margin-bottom:12px"
            @close="exitDiff"
          >
            <template #title>
              正在展示对比视图（基准计划 v{{ basePlanVersion }} vs 当前计划 v{{ currentPlanVersion }}）
            </template>
            <el-button size="small" @click="exitDiff">退出对比</el-button>
          </el-alert>

          <!-- Gantt -->
          <el-card style="margin-bottom:16px">
            <template #header>
              <span>排程 Gantt 图</span>
              <el-tag v-if="diffMode" type="warning" size="small" style="margin-left:8px">对比模式</el-tag>
            </template>
            <GanttChart
              :tasks="tasks"
              :makespan="solveResult.schedule?.makespan ?? 0"
              :critical-path="criticalPath"
              :diff-mode="diffMode"
              :diff-steps="diffSteps"
            />
          </el-card>

          <!-- Task Table -->
          <el-card style="margin-bottom:16px">
            <template #header>任务明细</template>
            <el-table :data="tasks" size="small" border stripe>
              <el-table-column prop="step_order" label="步骤" width="60" />
              <el-table-column prop="op_rule_code" label="活动编码" width="160" />
              <el-table-column label="开始" width="70">
                <template #default="{ row }">{{ row.start_min }}m</template>
              </el-table-column>
              <el-table-column label="结束" width="70">
                <template #default="{ row }">{{ row.end_min }}m</template>
              </el-table-column>
              <el-table-column label="时长" width="60">
                <template #default="{ row }">{{ row.duration_min }}m</template>
              </el-table-column>
              <el-table-column label="角色" width="100">
                <template #default="{ row }">
                  <el-tag
                    :type="roleTagType(row.step_role)"
                    size="small"
                  >
                    {{ roleLabel(row.step_role) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="not_before" width="90">
                <template #default="{ row }">
                  <span v-if="row.not_before != null">{{ row.not_before }}m</span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="资源" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ (row.resources ?? []).map((r) => r.code ?? r).join(', ') || '—' }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="90" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="warning" @click="openBlockage(row)">
                    标记阻塞
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- Parallel Groups -->
          <el-card>
            <template #header>并行组</template>
            <template v-if="parallelGroups.length">
              <el-tag
                v-for="(g, i) in parallelGroups"
                :key="i"
                type="success"
                style="margin-right:6px;margin-bottom:6px"
              >
                并行: {{ g.join(' / ') }}
              </el-tag>
            </template>
            <span v-else class="muted">未检测到实际并行组</span>
          </el-card>
        </template>
      </el-col>
    </el-row>

    <!-- BlockageDialog -->
    <BlockageDialog
      v-model="blockageVisible"
      :task="selectedTask"
      :plan-id="currentPlanId"
      :machine-id="solveForm.machine_id"
      :current-state-id="solveForm.current_state_id"
      :target-state-id="solveForm.target_state_id"
      @replanned="onReplanned"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GanttChart from '../../components/GanttChart.vue'
import BlockageDialog from '../../components/BlockageDialog.vue'
import VersionHistory from './VersionHistory.vue'
import { getMachines, getStates } from '../../api/masterData'
import { postSolve, getPlanVersions, getPlanDiff } from '../../api/solve'

// ── State ─────────────────────────────────────────────────────
const machines = ref([])
const states = ref([])
const solving = ref(false)

const solveForm = ref({
  machine_id: null,
  current_state_id: null,
  target_state_id: null,
})

const solveResult = ref(null)
const currentPlanId = ref(null)
const versionChain = ref([])

const blockageVisible = ref(false)
const selectedTask = ref(null)

// Diff mode
const diffMode = ref(false)
const diffSteps = ref([])
const basePlanVersion = ref(null)
const currentPlanVersion = ref(null)

// ── Computed ──────────────────────────────────────────────────
const tasks = computed(() => solveResult.value?.schedule?.tasks ?? [])
const stateDelta = computed(() => solveResult.value?.state_delta ?? [])
const criticalPath = computed(() => solveResult.value?.critical_path ?? [])
const parallelGroups = computed(() => solveResult.value?.schedule?.parallel_groups ?? [])

// ── Helpers ───────────────────────────────────────────────────
function stateLabel(s) {
  const feats = Object.entries(s.features ?? {}).map(([k, v]) => `${k}:${v}`).join(' / ')
  return `${s.label ?? '未命名'} (${s.state_type})${feats ? ' — ' + feats : ''}`
}

const ROLE_TAG = {
  repair: 'danger',
  pulled_forward: 'primary',
  delayed: 'warning',
}
const ROLE_LABEL_MAP = {
  normal: '正常',
  repair: '维修',
  pulled_forward: '提前',
  delayed: '延后',
}
const roleTagType = (r) => ROLE_TAG[r]
const roleLabel = (r) => ROLE_LABEL_MAP[r] ?? r ?? 'normal'

// ── API Actions ───────────────────────────────────────────────
async function loadMachines() {
  machines.value = await getMachines()
}

async function onMachineChange() {
  states.value = []
  solveForm.value.current_state_id = null
  solveForm.value.target_state_id = null
  if (!solveForm.value.machine_id) return
  const res = await getStates(solveForm.value.machine_id)
  states.value = res.states ?? []
  // Auto-select first current + first target
  const curr = states.value.find((s) => s.state_type === 'current')
  const tgt = states.value.find((s) => s.state_type === 'target')
  if (curr) solveForm.value.current_state_id = curr.state_id
  if (tgt) solveForm.value.target_state_id = tgt.state_id
}

async function runSolve() {
  if (!solveForm.value.machine_id || !solveForm.value.current_state_id || !solveForm.value.target_state_id) {
    return ElMessage.warning('请完整选择设备、当前状态和目标状态')
  }
  if (solveForm.value.current_state_id === solveForm.value.target_state_id) {
    return ElMessage.warning('当前状态和目标状态不能相同')
  }
  solving.value = true
  diffMode.value = false
  try {
    const result = await postSolve({
      machine_id: solveForm.value.machine_id,
      current_state_id: solveForm.value.current_state_id,
      target_state_id: solveForm.value.target_state_id,
      objectives: [{ type: 'minimize_makespan', weight: 1.0 }],
    })
    // HTTP 200 but solve failed (e.g. no solution, infeasible)
    if (result.status !== 'done') {
      ElMessage.error(`${result.error_code ?? 'ERROR'}: ${result.error_message ?? '求解失败'}`)
      return
    }
    await applyResult(result)
    ElMessage.success('求解完成')
  } catch {
    // HTTP errors are already handled (ElMessage.error) by the axios interceptor;
    // swallow the re-thrown Error to prevent Vue's unhandled-promise-rejection warning.
  } finally {
    solving.value = false
  }
}

async function applyResult(result) {
  solveResult.value = result
  currentPlanId.value = result.candidate_plan_id
  // Load version chain
  if (result.candidate_plan_id) {
    versionChain.value = await getPlanVersions(result.candidate_plan_id)
    const cur = versionChain.value.find((v) => v.id === result.candidate_plan_id)
    currentPlanVersion.value = cur?.version ?? null
  }
}

// ── Blockage ──────────────────────────────────────────────────
function openBlockage(task) {
  selectedTask.value = task
  blockageVisible.value = true
}

async function onReplanned(result) {
  ElMessage.success('重排完成')
  await applyResult(result)
}

// ── Diff ──────────────────────────────────────────────────────
async function onDiff(baseId) {
  if (!currentPlanId.value) return
  try {
    const diff = await getPlanDiff(baseId, currentPlanId.value)
    diffSteps.value = diff.steps ?? []
    diffMode.value = true
    const base = versionChain.value.find((v) => v.id === baseId)
    basePlanVersion.value = base?.version ?? baseId
  } catch {
    // error already shown by interceptor
  }
}

async function onLoadVersion(planId) {
  // Just switch diff to compare that version vs current
  await onDiff(planId)
}

function exitDiff() {
  diffMode.value = false
  diffSteps.value = []
}

onMounted(loadMachines)
</script>

<style scoped>
.metric-card { text-align: center; }
.info-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.info-label { font-size: 12px; color: #64748b; font-weight: 600; margin-right: 6px; min-width: 60px; }
.muted { color: #94a3b8; font-size: 13px; }
</style>
