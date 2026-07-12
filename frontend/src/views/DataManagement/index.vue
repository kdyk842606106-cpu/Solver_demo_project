<template>
  <div class="data-management">
    <div class="toolbar">
      <div>
        <h2>数据管理</h2>
        <p>维护设备类型、状态目标、活动能力和导入验证数据。</p>
      </div>
      <div class="toolbar-actions">
        <el-button :icon="Download" @click="downloadTemplate">下载场景模板</el-button>
        <el-button type="primary" :icon="Upload" @click="openImport">导入场景</el-button>
      </div>
    </div>

    <el-tabs v-model="activeWorkspace" tab-position="left" class="data-tabs">
      <el-tab-pane label="基础对象" name="basic">
        <el-collapse v-model="basicPanels">
          <el-collapse-item title="设备类型" name="machineType">
            <MachineTypePage />
          </el-collapse-item>
          <el-collapse-item title="设备实例" name="machine">
            <MachinePage />
          </el-collapse-item>
          <el-collapse-item title="机器资源" name="resource">
            <ResourcePage />
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>

      <el-tab-pane label="状态维度" name="stateDimension">
        <BusinessStateDimensionPage />
      </el-tab-pane>

      <el-tab-pane label="状态目标" name="stateTarget">
        <StateTargetWorkspace />
      </el-tab-pane>

      <el-tab-pane label="状态快照" name="stateSnapshot">
        <StatePage />
      </el-tab-pane>

      <el-tab-pane label="活动能力" name="activityCapability">
        <ActivityCapabilityWorkspace />
      </el-tab-pane>

      <el-tab-pane label="网络编辑器" name="networkEditor">
        <NetworkEditorWorkspace @open-workspace="openWorkspace" />
      </el-tab-pane>

      <el-tab-pane label="验证检查" name="validation">
        <ValidationWorkspace />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialogVisible" title="导入业务场景" width="900px">
      <div class="import-panel">
        <input ref="fileInput" type="file" accept=".xlsx" class="file-input" @change="onFileChange" />
        <div class="file-row">
          <el-button :icon="Upload" @click="fileInput?.click()">选择 Excel</el-button>
          <span class="file-name">{{ selectedFile?.name || '未选择文件' }}</span>
          <el-button type="primary" :loading="validating" :disabled="!selectedFile" @click="runDryRun">
            预校验
          </el-button>
        </div>

        <template v-if="result">
          <el-alert
            :type="result.errors.length ? 'error' : 'success'"
            :closable="false"
            class="result-alert"
            :title="result.errors.length ? '预校验发现错误' : '预校验通过'"
          />

          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="场景">{{ result.summary.scenario_code || '-' }}</el-descriptions-item>
            <el-descriptions-item label="活动规则">{{ result.summary.rules_total }}</el-descriptions-item>
            <el-descriptions-item label="机器资源">{{ result.summary.resources_total }}</el-descriptions-item>
            <el-descriptions-item label="状态快照">{{ result.summary.states_total }}</el-descriptions-item>
            <el-descriptions-item label="设备实例">{{ result.summary.machines_total }}</el-descriptions-item>
            <el-descriptions-item label="状态特征">{{ result.summary.state_feature_defs_total }}</el-descriptions-item>
            <el-descriptions-item label="活动包">{{ result.summary.activity_nodes_total ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="原子活动">{{ result.summary.atomic_activities_total ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="包-原子引用">{{ result.summary.activity_package_atomic_refs_total ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="状态节点">{{ result.summary.state_nodes_total ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="Scope Guard">{{ result.summary.scope_guards_total ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="错误">{{ result.summary.error_count }}</el-descriptions-item>
          </el-descriptions>

          <el-table :data="previewRows" size="small" border class="result-table">
            <el-table-column prop="name" label="对象" />
            <el-table-column prop="create" label="新增" width="90" />
            <el-table-column prop="update" label="更新" width="90" />
          </el-table>

          <el-table
            v-if="result.errors.length"
            :data="result.errors"
            size="small"
            border
            class="result-table"
            max-height="260"
          >
            <el-table-column prop="sheet" label="Sheet" width="150" />
            <el-table-column prop="row" label="行" width="80" />
            <el-table-column prop="field" label="字段" width="180" />
            <el-table-column prop="message" label="错误" show-overflow-tooltip />
          </el-table>
        </template>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!result || result.errors.length > 0"
          @click="confirmImport"
        >
          确认导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import MachineTypePage from './MachineTypePage.vue'
import MachinePage from './MachinePage.vue'
import ResourcePage from './ResourcePage.vue'
import BusinessStateDimensionPage from './BusinessStateDimensionPage.vue'
import StateTargetWorkspace from './StateTargetWorkspace.vue'
import StatePage from './StatePage.vue'
import ActivityCapabilityWorkspace from './ActivityCapabilityWorkspace.vue'
import NetworkEditorWorkspace from './NetworkEditorWorkspace.vue'
import ValidationWorkspace from './ValidationWorkspace.vue'
import {
  downloadScenarioTemplate,
  importScenario,
} from '../../api/masterData'

const activeWorkspace = ref('basic')
const basicPanels = ref(['machineType', 'machine', 'resource'])
const dialogVisible = ref(false)
const selectedFile = ref(null)
const fileInput = ref(null)
const result = ref(null)
const validating = ref(false)
const importing = ref(false)

const previewRows = computed(() => {
  if (!result.value?.preview) return []
  const labels = {
    feature_catalog: '全局特征',
    machine_types: '设备类型',
    machines: '设备实例',
    state_feature_defs: '状态特征',
    resources: '机器资源',
    activity_nodes: '活动包',
    atomic_activities: '原子活动',
    activity_package_atomic_refs: '包-原子引用',
    state_nodes: '状态节点',
    scope_guards: 'Scope Guard',
    maintenance_intents: '维护意图',
    layered_health_checks: '导入诊断',
    rules: '活动规则',
    states: '状态快照',
  }
  return Object.entries(result.value.preview).map(([key, value]) => ({
    name: labels[key] || key,
    create: value.create,
    update: value.update,
  }))
})

function openImport() {
  dialogVisible.value = true
}

function openWorkspace(name) {
  activeWorkspace.value = name
}

function onFileChange(event) {
  selectedFile.value = event.target.files?.[0] || null
  result.value = null
}

async function runDryRun() {
  if (!selectedFile.value) return
  validating.value = true
  try {
    result.value = await importScenario(selectedFile.value, { dryRun: true })
  } finally {
    validating.value = false
  }
}

async function confirmImport() {
  if (!selectedFile.value) return
  importing.value = true
  try {
    result.value = await importScenario(selectedFile.value, { dryRun: false })
    ElMessage.success('场景导入完成')
    dialogVisible.value = false
  } finally {
    importing.value = false
  }
}

async function downloadTemplate() {
  const blob = await downloadScenarioTemplate()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'scenario_template.xlsx'
  anchor.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.data-management {
  padding: 20px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}
.toolbar h2 {
  margin: 0 0 6px;
}
.toolbar p {
  margin: 0;
  color: #606266;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
}
.data-tabs {
  min-height: 560px;
}
.file-input {
  display: none;
}
.file-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.file-name {
  color: #606266;
  flex: 1;
}
.result-alert {
  margin: 12px 0;
}
.result-table {
  margin-top: 12px;
}
</style>
