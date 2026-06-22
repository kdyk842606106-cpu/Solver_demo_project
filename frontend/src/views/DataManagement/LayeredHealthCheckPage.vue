<template>
  <div>
    <h2>健康检查</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card>
          <el-form label-width="108px" @submit.prevent>
            <el-form-item label="设备类型" required>
              <el-select v-model="machineTypeId" style="width:100%" @change="onTypeChange">
                <el-option
                  v-for="mt in machineTypes"
                  :key="mt.id"
                  :label="`${mt.name} (${mt.code})`"
                  :value="mt.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="目标状态">
              <el-tree-select
                v-model="targetStateNodeIds"
                :data="stateTreeOptions"
                :props="treeProps"
                node-key="id"
                multiple
                show-checkbox
                check-strictly
                filterable
                collapse-tags
                collapse-tags-tooltip
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="活动范围">
              <el-tree-select
                v-model="activityScopeNodeIds"
                :data="activityTreeOptions"
                :props="treeProps"
                node-key="id"
                multiple
                show-checkbox
                check-strictly
                filterable
                collapse-tags
                collapse-tags-tooltip
                style="width:100%"
              />
            </el-form-item>
            <el-form-item label="包含停用">
              <el-switch v-model="includeInactive" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading" @click="runCheck">运行检查</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card v-loading="loading">
          <el-empty v-if="!result" description="请选择目标状态和活动范围后运行检查" />
          <template v-else>
            <el-alert
              :type="statusAlertType"
              :closable="false"
              class="section"
              :title="statusTitle"
            />

            <el-descriptions :column="4" border size="small" class="section">
              <el-descriptions-item label="目标事实">{{ result.summary.goal_fact_count }}</el-descriptions-item>
              <el-descriptions-item label="候选活动">{{ result.summary.candidate_activity_count }}</el-descriptions-item>
              <el-descriptions-item label="规则">{{ result.summary.effective_rule_count }}</el-descriptions-item>
              <el-descriptions-item label="阻断">{{ result.summary.blocking_count }}</el-descriptions-item>
              <el-descriptions-item label="Provider">{{ result.summary.provider_fact_count }}</el-descriptions-item>
              <el-descriptions-item label="Consumer">{{ result.summary.consumer_fact_count }}</el-descriptions-item>
              <el-descriptions-item label="诊断">{{ result.summary.diagnostic_count }}</el-descriptions-item>
              <el-descriptions-item label="状态">{{ result.status }}</el-descriptions-item>
            </el-descriptions>

            <h3>诊断</h3>
            <el-table :data="result.diagnostics" size="small" border class="section" max-height="260">
              <el-table-column label="级别" width="86">
                <template #default="{ row }">
                  <el-tag :type="row.severity === 'error' ? 'danger' : 'warning'" size="small">
                    {{ row.severity }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="code" label="诊断码" width="180" />
              <el-table-column prop="feature_key" label="特征键" width="130" />
              <el-table-column label="目标" width="120">
                <template #default="{ row }">{{ formatTarget(row) }}</template>
              </el-table-column>
              <el-table-column prop="message" label="说明" show-overflow-tooltip />
            </el-table>

            <h3>Provider / Consumer</h3>
            <el-table :data="result.provider_graph" size="small" border class="section" max-height="320">
              <el-table-column prop="feature_key" label="特征键" width="150" />
              <el-table-column prop="target_value" label="取值" width="120" />
              <el-table-column label="目标状态" width="100">
                <template #default="{ row }">{{ row.goal_state_node_ids.length }}</template>
              </el-table-column>
              <el-table-column label="Providers" show-overflow-tooltip>
                <template #default="{ row }">{{ row.providers.map(formatRule).join('；') || '-' }}</template>
              </el-table-column>
              <el-table-column label="Consumers" show-overflow-tooltip>
                <template #default="{ row }">{{ row.consumers.map(formatConsumer).join('；') || '-' }}</template>
              </el-table-column>
            </el-table>

            <h3>目标事实</h3>
            <el-table :data="result.goal_facts" size="small" border>
              <el-table-column prop="state_node_code" label="状态" width="150" />
              <el-table-column prop="feature_key" label="特征键" width="150" />
              <el-table-column label="目标" width="150">
                <template #default="{ row }">{{ row.operator }} {{ row.target_value }}</template>
              </el-table-column>
              <el-table-column label="路径" show-overflow-tooltip>
                <template #default="{ row }">{{ formatPath(row.source_path) }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  checkLayeredHealth,
  getActivityNodes,
  getMachineTypes,
  getStateNodes,
} from '../../api/masterData'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'

const machineTypes = ref([])
const activityNodes = ref([])
const stateNodes = ref([])
const machineTypeId = ref(null)
const targetStateNodeIds = ref([])
const activityScopeNodeIds = ref([])
const includeInactive = ref(false)
const result = ref(null)
const loading = ref(false)
const treeProps = treeSelectProps
const stateTreeOptions = computed(() =>
  buildHierarchyTree(stateNodes.value, { disabled: (node) => node.level < 2 }),
)
const activityTreeOptions = computed(() =>
  buildHierarchyTree(activityNodes.value, { disabled: (node) => node.level > 2 }),
)

const statusAlertType = computed(() => {
  if (result.value?.status === 'blocked') return 'error'
  if (result.value?.status === 'warning') return 'warning'
  return 'success'
})

const statusTitle = computed(() => {
  if (!result.value) return ''
  if (result.value.status === 'blocked') {
    return `发现 ${result.value.summary.blocking_count} 条阻断诊断`
  }
  if (result.value.status === 'warning') {
    return `发现 ${result.value.summary.diagnostic_count} 条诊断`
  }
  return '未发现阻断诊断'
})

function formatPath(path) {
  return path?.map((item) => item.code).join(' / ') || '-'
}

function formatTarget(row) {
  if (!row.operator && !row.target_value) return '-'
  return `${row.operator || 'eq'} ${row.target_value || ''}`.trim()
}

function formatRule(item) {
  return `${item.op_rule_code}@${item.activity_node_code}`
}

function formatConsumer(item) {
  const source = item.source_type === 'self_activity_rule' ? '自有' : item.scope_guard_name || item.source_type
  return `${item.op_rule_code}@${item.activity_node_code}(${source})`
}

async function onTypeChange() {
  result.value = null
  targetStateNodeIds.value = []
  activityScopeNodeIds.value = []
  if (!machineTypeId.value) {
    activityNodes.value = []
    stateNodes.value = []
    return
  }
  const [activities, states] = await Promise.all([
    getActivityNodes(machineTypeId.value),
    getStateNodes(machineTypeId.value),
  ])
  activityNodes.value = activities
  stateNodes.value = states
}

async function runCheck() {
  if (!machineTypeId.value) return ElMessage.warning('请先选择设备类型')
  if (!targetStateNodeIds.value.length && !activityScopeNodeIds.value.length) {
    return ElMessage.warning('请选择目标状态或活动范围')
  }
  loading.value = true
  try {
    result.value = await checkLayeredHealth(machineTypeId.value, {
      target_state_node_ids: targetStateNodeIds.value,
      activity_scope_node_ids: activityScopeNodeIds.value,
      include_inactive: includeInactive.value,
    })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    machineTypes.value = await getMachineTypes()
  } catch {
    machineTypes.value = []
  }
})
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}

h3 {
  margin: 18px 0 8px;
  font-size: 15px;
}
</style>
