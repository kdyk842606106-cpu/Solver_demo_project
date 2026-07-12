<!-- 4-6: SolvePage — main orchestrator with state_delta, critical_path, version history, Gantt -->
<template>
  <div class="solve-page">
    <div class="page-heading">
      <h2>求解</h2>
      <span class="muted">选择设备与状态后生成排程，结果区按视图全宽展示。</span>
    </div>

    <el-card class="solve-control-card">
      <el-form :model="solveForm" class="solve-toolbar" label-position="top" @submit.prevent>
        <el-form-item label="模式">
          <el-radio-group v-model="solveMode">
            <el-radio-button label="snapshot">快照</el-radio-button>
            <el-radio-button label="layered">分层</el-radio-button>
            <el-radio-button label="maintenance">维护</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="设备" required>
          <el-select
            v-model="solveForm.machine_id"
            placeholder="请选择设备"
            filterable
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
          <el-select v-model="solveForm.current_state_id" placeholder="请选择" filterable>
            <el-option
              v-for="s in states"
              :key="s.state_id"
              :label="stateLabel(s)"
              :value="s.state_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="solveMode === 'snapshot'" label="目标状态" required>
          <el-select v-model="solveForm.target_state_id" placeholder="请选择" filterable>
            <el-option
              v-for="s in states"
              :key="s.state_id"
              :label="stateLabel(s)"
              :value="s.state_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="solveMode === 'layered'" label="目标状态" required>
          <el-tree-select
            v-model="layeredTargetStateNodeIds"
            :data="layeredStateTreeOptions"
            :props="treeProps"
            data-testid="solve-layered-target-state-tree"
            node-key="id"
            multiple
            show-checkbox
            check-strictly
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="请选择状态树节点"
          />
        </el-form-item>

        <el-form-item v-if="solveMode === 'layered'" label="活动范围">
          <el-tree-select
            v-model="layeredActivityScopeNodeIds"
            :data="layeredActivityTreeOptions"
            :props="treeProps"
            node-key="id"
            multiple
            show-checkbox
            check-strictly
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="可不选，默认使用全部原子活动"
          />
        </el-form-item>

        <el-form-item v-if="solveMode === 'maintenance'" label="维护意图" required>
          <el-select
            v-model="selectedMaintenanceIntentTemplateIds"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="请选择维护意图"
          >
            <el-option
              v-for="item in maintenanceIntentTemplates"
              :key="item.id"
              :label="`${item.issue_type} ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="优化目标">
          <div class="objective-controls">
            <el-tag type="info" size="small">最小化总工期</el-tag>
            <el-switch
              v-model="continuityEnabled"
              :active-text="continuitySwitchLabel"
              inactive-text=""
            />
            <el-input-number
              v-if="continuityEnabled"
              v-model="continuityWeight"
              :min="0.1"
              :max="10"
              :step="0.25"
              :precision="2"
              size="small"
              controls-position="right"
              class="objective-weight"
            />
          </div>
        </el-form-item>

        <el-form-item label="操作">
          <div class="toolbar-actions">
            <el-button
              type="primary"
              :loading="solving"
              :disabled="!solveForm.machine_id"
              @click="runSolve"
            >
              开始求解
            </el-button>
            <el-button @click="loadMachines">刷新设备</el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-empty v-if="!solveResult" class="empty-result" description="尚未执行求解" />

    <template v-else>
      <div class="metric-strip">
        <div class="metric-item primary">
          <span>总工期</span>
          <strong>{{ solveResult.schedule?.makespan ?? 0 }}m</strong>
        </div>
        <div class="metric-item">
          <span>活动数</span>
          <strong>{{ tasks.length }}</strong>
        </div>
        <div class="metric-item">
          <span>关键路径</span>
          <strong>{{ criticalPath.length }}</strong>
        </div>
        <div class="metric-item">
          <span>并行组</span>
          <strong>{{ parallelGroups.length }}</strong>
        </div>
        <div class="metric-item">
          <span>计划版本</span>
          <strong>{{ currentPlanVersion ? `v${currentPlanVersion}` : '—' }}</strong>
        </div>
      </div>

      <div class="result-summary">
        <div class="info-row">
          <span class="info-label">状态变化</span>
          <el-tag
            v-for="d in stateDelta"
            :key="d.feature_key"
            type="info"
            size="small"
          >
            {{ d.feature_key }}: {{ d.from_value }} → {{ d.to_value }}
          </el-tag>
          <span v-if="!stateDelta.length" class="muted">无状态变化</span>
        </div>
        <div class="info-row">
          <span class="info-label">关键活动</span>
          <el-tag
            v-for="op in criticalPath"
            :key="op"
            type="warning"
            size="small"
          >
            {{ op }}
          </el-tag>
          <span v-if="!criticalPath.length" class="muted">-</span>
        </div>
        <div v-if="continuitySummary" class="info-row">
          <span class="info-label">{{ continuitySummaryLabel }}</span>
          <el-tag type="info" size="small">
            {{ continuitySummaryGroupLabel }} {{ continuitySummary.group_count ?? 0 }}
          </el-tag>
          <el-tag
            v-for="group in continuityGroups"
            :key="continuityGroupKey(group)"
            :type="group.is_compact ? 'success' : 'warning'"
            size="small"
          >
            {{ continuityGroupLabel(group) }}:
            gap {{ group.internal_gap_min }}m /
            interrupt {{ group.interruption_count }}
          </el-tag>
          <span v-if="!continuityGroups.length" class="muted">{{ continuityEmptyText }}</span>
        </div>
      </div>

      <el-alert
        v-if="diffMode"
        type="info"
        show-icon
        :closable="true"
        class="diff-alert"
        @close="exitDiff"
      >
        <template #title>
          正在展示对比视图（基准计划 v{{ basePlanVersion }} vs 当前计划 v{{ currentPlanVersion }}）
        </template>
        <el-button size="small" @click="exitDiff">退出对比</el-button>
      </el-alert>

      <el-tabs v-model="activeResultTab" class="result-tabs">
        <el-tab-pane label="甘特图" name="gantt">
          <div class="workspace-panel">
            <div class="panel-title">
              <span>排程 Gantt 图</span>
              <el-tag v-if="diffMode" type="warning" size="small">对比模式</el-tag>
            </div>
            <div class="gantt-controls">
              <el-radio-group v-model="ganttViewMode" size="small">
                <el-radio-button label="traditional">传统视图</el-radio-button>
                <el-radio-button label="state-lane" :disabled="!stateLaneAvailable">状态泳道</el-radio-button>
              </el-radio-group>
              <el-tag v-if="effectiveGanttViewMode === 'state-lane' && !continuityObjectiveActive" type="warning" size="small">
                未启用连续性优化
              </el-tag>
              <el-tag v-else-if="diffMode" type="info" size="small">对比模式使用传统视图</el-tag>
              <el-tag v-else-if="ganttViewMode === 'state-lane' && tasks.length && !stateLaneAvailable" type="info" size="small">
                当前结果没有状态包归属数据，已显示传统视图
              </el-tag>
            </div>
            <div
              v-if="effectiveGanttViewMode === 'traditional' && solveResult.layered && activityGroupRows.length && !diffMode"
              class="hierarchy-controls"
            >
              <el-switch
                v-model="ganttHierarchyEnabled"
                active-text="按二级活动查看"
                inactive-text=""
              />
              <el-button
                v-for="group in activityGroupRows"
                :key="group.activity_group_id"
                size="small"
                :type="isActivityGroupCollapsed(group.activity_group_id) ? 'warning' : 'info'"
                plain
                @click="toggleActivityGroup(group.activity_group_id)"
              >
                {{ group.activity_group_code || group.activity_group_id }}
                {{ isActivityGroupCollapsed(group.activity_group_id) ? '已折叠' : '展开' }}
              </el-button>
            </div>
            <GanttChart
              :tasks="effectiveGanttViewMode === 'state-lane' ? [] : ganttTasks"
              :makespan="solveResult.schedule?.makespan ?? 0"
              :critical-path="criticalPath"
              :diff-mode="diffMode"
              :diff-steps="diffSteps"
              :lane-mode="effectiveGanttViewMode === 'state-lane'"
              :lane-groups="stateLaneGroups"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="活动网络图" name="network">
          <div class="workspace-panel">
            <ActivityNetworkBoard
              :tasks="tasks"
              :makespan="solveResult.schedule?.makespan ?? 0"
              :critical-path="criticalPath"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="任务明细" name="tasks">
          <div class="workspace-panel">
            <div class="panel-title">
              <span>任务明细</span>
            </div>
            <el-table
              :data="taskTableRows"
              row-key="row_key"
              default-expand-all
              :tree-props="{ children: 'children' }"
              size="small"
              border
              stripe
            >
              <el-table-column label="步骤" width="90">
                <template #default="{ row }">
                  <span v-if="row.row_type === 'task'">{{ row.step_order }}</span>
                  <span v-else class="muted">{{ row.level }}级</span>
                </template>
              </el-table-column>
              <el-table-column label="活动编码" width="180">
                <template #default="{ row }">
                  {{ row.row_type === 'task' ? row.op_rule_code : row.activity_node_code }}
                </template>
              </el-table-column>
              <el-table-column label="活动名称" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.row_type === 'task' ? (row.op_rule_name || '-') : row.activity_node_name }}
                </template>
              </el-table-column>
              <el-table-column label="二级活动" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.row_type === 'task' ? (row.activity_group_code || '-') : activityNodeGroupLabel(row) }}
                </template>
              </el-table-column>
              <el-table-column label="开始" width="80">
                <template #default="{ row }">
                  <span v-if="row.row_type === 'task'">{{ row.start_min }}m</span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="结束" width="80">
                <template #default="{ row }">
                  <span v-if="row.row_type === 'task'">{{ row.end_min }}m</span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="时长" width="80">
                <template #default="{ row }">
                  <span v-if="row.row_type === 'task'">{{ row.duration_min }}m</span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="角色" width="100">
                <template #default="{ row }">
                  <el-tag v-if="row.row_type === 'task'" :type="roleTagType(row.step_role)" size="small">
                    {{ roleLabel(row.step_role) }}
                  </el-tag>
                  <span v-else class="muted">活动组</span>
                </template>
              </el-table-column>
              <el-table-column label="not_before" width="110">
                <template #default="{ row }">
                  <span v-if="row.row_type === 'task' && row.not_before != null">{{ row.not_before }}m</span>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="资源" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.row_type === 'task' ? formatResources(row.resources) : `${row.scheduled_task_count || 0} 个任务` }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="110" fixed="right">
                <template #default="{ row }">
                  <el-button v-if="row.row_type === 'task'" size="small" type="warning" @click="openBlockage(row)">
                    标记阻塞
                  </el-button>
                  <span v-else class="muted">—</span>
                </template>
              </el-table-column>
            </el-table>

            <div class="parallel-section">
              <span class="section-label">并行组</span>
              <template v-if="parallelGroups.length">
                <el-tag
                  v-for="(g, i) in parallelGroups"
                  :key="i"
                  type="success"
                >
                  {{ g.join(' / ') }}
                </el-tag>
              </template>
              <span v-else class="muted">未检测到实际并行组</span>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="solveResult.layered" label="分层解释" name="layered">
          <div class="workspace-panel layered-panel">
            <el-descriptions
              v-if="solveResult.maintenance"
              :column="3"
              border
              size="small"
              class="layered-table"
            >
              <el-descriptions-item label="维护意图">
                {{ solveResult.maintenance.intent_templates.map((item) => item.name).join(' / ') }}
              </el-descriptions-item>
              <el-descriptions-item label="合并数量">
                {{ solveResult.maintenance.merged_intent_count }}
              </el-descriptions-item>
              <el-descriptions-item label="观测覆盖">
                {{ Object.entries(solveResult.maintenance.current_state_overrides || {}).map(([k, v]) => `${k}=${v}`).join(' / ') || '-' }}
              </el-descriptions-item>
            </el-descriptions>
            <div v-if="layeredPreflightHealth" class="panel-title split-title">
              <span>求解前诊断</span>
              <el-tag :type="healthTagType(layeredPreflightHealth.status)" size="small">
                {{ healthStatusLabel(layeredPreflightHealth.status) }}
              </el-tag>
            </div>
            <el-descriptions
              v-if="layeredPreflightHealth"
              :column="4"
              border
              size="small"
              class="layered-table"
            >
              <el-descriptions-item label="目标事实">
                {{ layeredPreflightHealth.summary?.goal_fact_count ?? 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="候选活动">
                {{ layeredPreflightHealth.summary?.candidate_activity_count ?? 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="有效规则">
                {{ layeredPreflightHealth.summary?.effective_rule_count ?? 0 }}
              </el-descriptions-item>
              <el-descriptions-item label="诊断">
                {{ layeredPreflightHealth.summary?.diagnostic_count ?? 0 }}
                / 阻塞 {{ layeredPreflightHealth.blocking_count ?? 0 }}
              </el-descriptions-item>
            </el-descriptions>
            <el-table
              v-if="layeredPreflightHealth?.diagnostics?.length"
              :data="layeredPreflightHealth.diagnostics"
              size="small"
              border
              class="layered-table"
            >
              <el-table-column prop="code" label="诊断码" width="170" />
              <el-table-column label="等级" width="100">
                <template #default="{ row }">
                  <el-tag :type="diagnosticSeverityTag(row.severity)" size="small">
                    {{ row.severity || 'warning' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="message" label="说明" min-width="240" show-overflow-tooltip />
              <el-table-column label="对象" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ formatHealthDiagnostic(row) }}</template>
              </el-table-column>
            </el-table>
            <div class="panel-title">
              <span>状态树完成</span>
              <el-tag
                :type="solveResult.layered.state_replay.status === 'ok' ? 'success' : 'danger'"
                size="small"
              >
                {{ solveResult.layered.state_replay.status }}
              </el-tag>
            </div>
            <el-table
              :data="layeredStateRows"
              row-key="state_node_id"
              default-expand-all
              :tree-props="{ children: 'children' }"
              size="small"
              border
              class="layered-table"
            >
              <el-table-column prop="level" label="层级" width="70" />
              <el-table-column prop="state_node_code" label="状态编码" width="160" />
              <el-table-column prop="state_node_name" label="状态名称" min-width="160" show-overflow-tooltip />
              <el-table-column label="完成度" width="120">
                <template #default="{ row }">{{ row.satisfied_leaf_count }} / {{ row.goal_leaf_count }}</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="110" />
              <el-table-column label="来源活动" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ formatStateSource(row) }}</template>
              </el-table-column>
            </el-table>

            <div class="panel-title split-title">
              <span>活动树汇总</span>
            </div>
            <el-table
              :data="layeredActivityRows"
              row-key="activity_node_id"
              default-expand-all
              :tree-props="{ children: 'children' }"
              size="small"
              border
              class="layered-table"
            >
              <el-table-column prop="level" label="层级" width="70" />
              <el-table-column prop="activity_node_code" label="活动编码" width="160" />
              <el-table-column prop="activity_node_name" label="活动名称" min-width="160" show-overflow-tooltip />
              <el-table-column prop="scheduled_task_count" label="任务数" width="90" />
              <el-table-column label="步骤" min-width="120">
                <template #default="{ row }">{{ row.task_step_orders.join(' / ') }}</template>
              </el-table-column>
            </el-table>

            <div class="panel-title split-title">
              <span>活动选择解释</span>
            </div>
            <el-table :data="solveResult.layered.activity_selection || []" size="small" border class="layered-table">
              <el-table-column prop="op_rule_code" label="活动规则" width="170" />
              <el-table-column prop="activity_node_code" label="三级活动" width="150" />
              <el-table-column label="选择" width="120">
                <template #default="{ row }">
                  <el-tag :type="selectionTagType(row)" size="small">
                    {{ selectionStatusLabel(row) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="原因" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ selectionReasonLabel(row.reason) }}</template>
              </el-table-column>
              <el-table-column label="复用" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ formatSelectionConsumers(row) }}</template>
              </el-table-column>
            </el-table>

            <template v-if="solveResult.maintenance">
              <div class="panel-title split-title">
                <span>维修维护解释</span>
              </div>
              <el-table :data="maintenanceSharedProviders" size="small" border class="layered-table">
                <el-table-column prop="op_rule_code" label="复用活动" width="170" />
                <el-table-column prop="activity_node_code" label="三级活动" width="150" />
                <el-table-column label="复用对象" min-width="220" show-overflow-tooltip>
                  <template #default="{ row }">{{ formatSelectionConsumers(row) }}</template>
                </el-table-column>
              </el-table>
              <el-table :data="maintenanceSkippedActivities" size="small" border class="layered-table">
                <el-table-column prop="op_rule_code" label="跳过活动" width="170" />
                <el-table-column prop="activity_node_code" label="三级活动" width="150" />
                <el-table-column label="原因" min-width="180">
                  <template #default="{ row }">{{ selectionReasonLabel(row.reason) }}</template>
                </el-table-column>
              </el-table>
            </template>

            <div class="panel-title split-title">
              <span>目标状态来源</span>
            </div>
            <el-table :data="stateGoalRows" size="small" border class="layered-table">
              <el-table-column prop="state_node_code" label="状态" width="170" />
              <el-table-column prop="feature_key" label="特征" width="150" />
              <el-table-column label="目标值" width="120">
                <template #default="{ row }">{{ row.target_value }}</template>
              </el-table-column>
              <el-table-column label="来源" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ formatGoalSource(row) }}</template>
              </el-table-column>
            </el-table>

            <div class="panel-title split-title">
              <span>连续性解释</span>
              <el-tag v-if="continuityObjectiveActive" type="success" size="small">软成本已参与</el-tag>
              <el-tag v-else type="info" size="small">仅最小化工期</el-tag>
            </div>
            <el-table :data="continuityExplanationRows" size="small" border class="layered-table">
              <el-table-column prop="state_group_code" label="状态包" width="160" />
              <el-table-column label="窗口" width="170">
                <template #default="{ row }">{{ row.window_start_min }}m - {{ row.window_end_min }}m</template>
              </el-table-column>
              <el-table-column prop="internal_gap_min" label="空档" width="90" />
              <el-table-column prop="interruption_count" label="插入" width="90" />
              <el-table-column label="说明" min-width="260" show-overflow-tooltip>
                <template #default="{ row }">{{ continuityReason(row) }}</template>
              </el-table-column>
            </el-table>

            <div class="panel-title split-title">
              <span>状态回放</span>
            </div>
            <el-table :data="solveResult.layered.state_replay.steps" size="small" border class="layered-table">
              <el-table-column prop="step_order" label="步骤" width="70" />
              <el-table-column prop="op_rule_code" label="活动" width="170" />
              <el-table-column label="前置" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.preconditions_satisfied ? 'success' : 'danger'" size="small">
                    {{ row.preconditions_satisfied ? '满足' : '缺失' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态变化" show-overflow-tooltip>
                <template #default="{ row }">{{ formatChangedFeatures(row.changed_features) }}</template>
              </el-table-column>
            </el-table>

            <div class="panel-title split-title">
              <span>有效前置来源</span>
            </div>
            <el-table :data="solveResult.layered.effective_preconditions" size="small" border>
              <el-table-column prop="op_rule_code" label="活动规则" width="170" />
              <el-table-column prop="activity_node_code" label="三级活动" width="150" />
              <el-table-column label="前置条件" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.preconditions.map(formatLayeredPrecondition).join('；') || '—' }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="版本历史" name="versions">
          <div class="workspace-panel version-panel">
            <VersionHistory
              :chain="versionChain"
              :current-id="currentPlanId"
              @diff="onDiff"
              @load="onLoadVersion"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- BlockageDialog -->
    <BlockageDialog
      v-model="blockageVisible"
      :task="selectedTask"
      :plan-id="currentPlanId"
      :machine-id="solveForm.machine_id"
      :current-state-id="solveForm.current_state_id"
      :target-state-id="solveForm.target_state_id"
      :mode="solveMode"
      :objectives="solveObjectives()"
      :target-state-node-ids="layeredTargetStateNodeIds"
      :activity-scope-node-ids="layeredActivityScopeNodeIds"
      :maintenance-intent-template-ids="selectedMaintenanceIntentTemplateIds"
      :blockage-reason-options="blockageReasonOptions"
      @replanned="onReplanned"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GanttChart from '../../components/GanttChart.vue'
import ActivityNetworkBoard from '../../components/ActivityNetworkBoard.vue'
import BlockageDialog from '../../components/BlockageDialog.vue'
import VersionHistory from './VersionHistory.vue'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'
import {
  getActivityNodes,
  getBlockageReasons,
  getMachines,
  getMaintenanceIntentTemplates,
  getStateNodes,
  getStateNodeReferences,
  getStates,
} from '../../api/masterData'
import { postLayeredSolve, postMaintenanceSolve, postSolve, getPlanVersions, getPlanDiff } from '../../api/solve'

// ── State ─────────────────────────────────────────────────────
const machines = ref([])
const states = ref([])
const layeredActivityNodes = ref([])
const layeredStateNodes = ref([])
const maintenanceIntentTemplates = ref([])
const blockageReasonOptions = ref([])
const solving = ref(false)
const activeResultTab = ref('gantt')
const solveMode = ref('snapshot')
const treeProps = treeSelectProps

const solveForm = ref({
  machine_id: null,
  current_state_id: null,
  target_state_id: null,
})
const layeredTargetStateNodeIds = ref([])
const layeredActivityScopeNodeIds = ref([])
const selectedMaintenanceIntentTemplateIds = ref([])
const continuityEnabled = ref(false)
const continuityWeight = ref(1.0)
const ganttHierarchyEnabled = ref(true)
const ganttViewMode = ref('traditional')
const collapsedActivityGroupIds = ref([])

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
const layeredStateTreeOptions = computed(() =>
  buildHierarchyTree(layeredStateNodes.value),
)
const layeredActivityTreeOptions = computed(() =>
  buildHierarchyTree(layeredActivityNodes.value, { disabled: (node) => node.level > 2 }),
)
const stateDelta = computed(() => solveResult.value?.state_delta ?? [])
const criticalPath = computed(() => solveResult.value?.critical_path ?? [])
const parallelGroups = computed(() => solveResult.value?.schedule?.parallel_groups ?? [])
const scheduleDiagnostics = computed(() => solveResult.value?.diagnostics?.schedule ?? null)
const stateContinuityAvailable = computed(() => solveMode.value === 'layered' || solveMode.value === 'maintenance')
const continuityObjectiveKind = computed(() => stateContinuityAvailable.value ? 'state' : 'activity')
const continuitySwitchLabel = computed(() =>
  continuityObjectiveKind.value === 'state' ? '状态包连续性' : '活动连续性',
)
const stateContinuitySummary = computed(() => scheduleDiagnostics.value?.state_group_continuity ?? null)
const activityContinuitySummary = computed(() => scheduleDiagnostics.value?.activity_group_continuity ?? null)
const continuitySummary = computed(() => {
  if (solveResult.value?.layered) return stateContinuitySummary.value
  return activityContinuitySummary.value
})
const continuityGroups = computed(() => continuitySummary.value?.groups ?? [])
const stateContinuityGroups = computed(() => stateContinuitySummary.value?.groups ?? [])
const continuitySummaryLabel = computed(() =>
  solveResult.value?.layered ? '状态包连续性' : '活动连续性',
)
const continuitySummaryGroupLabel = computed(() =>
  solveResult.value?.layered ? '状态包' : '二级活动',
)
const continuityEmptyText = computed(() =>
  solveResult.value?.layered ? '暂无多任务状态包' : '暂无多任务二级活动组',
)
const layeredPreflightHealth = computed(
  () => solveResult.value?.layered?.preflight_health ?? solveResult.value?.diagnostics?.layered_health ?? null,
)
const layeredStateRows = computed(
  () => solveResult.value?.layered?.state_tree ?? solveResult.value?.layered?.state_summary ?? [],
)
const layeredActivityRows = computed(
  () => solveResult.value?.layered?.activity_tree ?? solveResult.value?.layered?.activity_summary ?? [],
)
const activitySelectionRows = computed(() => solveResult.value?.layered?.activity_selection ?? [])
const stateGoalRows = computed(() => solveResult.value?.layered?.state_replay?.goal_results ?? [])
const maintenanceSharedProviders = computed(() =>
  activitySelectionRows.value.filter((row) => row.status === 'selected' && row.is_shared_provider),
)
const maintenanceSkippedActivities = computed(() =>
  activitySelectionRows.value.filter((row) => row.status === 'skipped'),
)
const continuityObjectiveActive = computed(() => {
  const weights = continuitySummary.value?.objective_weights ?? {}
  return [
    'minimize_activity_group_span',
    'minimize_activity_group_gaps',
    'minimize_activity_group_interruptions',
    'minimize_state_group_span',
    'minimize_state_group_gaps',
    'minimize_state_group_interruptions',
  ].some((key) => Number(weights[key] ?? 0) > 0)
})
const continuityExplanationRows = computed(() => continuityGroups.value)
const hasStateLaneData = computed(() => tasks.value.some(hasStateGroupMembership))
const stateLaneAvailable = computed(() => !diffMode.value && hasStateLaneData.value)
const effectiveGanttViewMode = computed(() => {
  if (ganttViewMode.value === 'state-lane' && stateLaneAvailable.value) return 'state-lane'
  return 'traditional'
})
const activityGroupRows = computed(() => {
  const byId = new Map()
  for (const task of tasks.value) {
    if (task.activity_group_id == null) continue
    const current = byId.get(task.activity_group_id) ?? {
      activity_group_id: task.activity_group_id,
      activity_group_code: task.activity_group_code,
      activity_group_name: task.activity_group_name,
      task_count: 0,
      start_min: task.start_min,
      end_min: task.end_min,
    }
    current.task_count += 1
    current.start_min = Math.min(current.start_min, task.start_min)
    current.end_min = Math.max(current.end_min, task.end_min)
    byId.set(task.activity_group_id, current)
  }
  return [...byId.values()].sort((a, b) => a.start_min - b.start_min || String(a.activity_group_code).localeCompare(String(b.activity_group_code)))
})

function stateNodesWithReferenceParents(stateNodes = [], stateReferences = []) {
  const byId = new Map(stateNodes.map((node) => [node.id, node]))
  const primaryRefByStateId = new Map()
  const activeRefs = stateReferences
    .filter((ref) => ref?.is_active !== false)
    .filter((ref) => byId.has(ref.state_node_id) && byId.has(ref.parent_state_node_id))
    .sort((a, b) =>
      Number(a.sort_order ?? 0) - Number(b.sort_order ?? 0) ||
      Number(a.id ?? 0) - Number(b.id ?? 0),
    )
  for (const ref of activeRefs) {
    if (!primaryRefByStateId.has(ref.state_node_id)) {
      primaryRefByStateId.set(ref.state_node_id, ref)
    }
  }

  return stateNodes.map((node) => {
    const ref = primaryRefByStateId.get(node.id)
    if (!ref || node.parent_id) return node
    const parent = byId.get(ref.parent_state_node_id)
    return {
      ...node,
      parent_id: ref.parent_state_node_id,
      level: parent ? Number(parent.level || 0) + 1 : node.level,
      sort_order: ref.sort_order ?? node.sort_order,
      reference_id: ref.id,
      reference_parent_id: ref.parent_state_node_id,
    }
  })
}
const stateLaneGroups = computed(() => {
  if (!hasStateLaneData.value) return []
  const summaryById = new Map(
    stateContinuityGroups.value.map((group) => [String(group.state_group_id), group]),
  )
  const byKey = new Map()

  for (const task of tasks.value) {
    const path = stateGroupPath(task)
    const primary = path[path.length - 1] ?? null
    const key = primary?.state_group_id != null ? `state-${primary.state_group_id}` : 'unassigned'
    const summary = primary?.state_group_id != null
      ? summaryById.get(String(primary.state_group_id)) ?? {}
      : {}
    if (!byKey.has(key)) {
      byKey.set(key, {
        key,
        state_group_id: primary?.state_group_id ?? null,
        state_group_code: primary?.state_group_code ?? null,
        state_group_name: primary?.state_group_name ?? '未归属状态包',
        parent_state_groups: path.slice(0, -1),
        state_group_path: path,
        start_min: task.start_min,
        end_min: task.end_min,
        task_count: 0,
        tasks: [],
        is_compact: summary.is_compact ?? null,
        internal_gap_min: summary.internal_gap_min ?? null,
        interruption_count: summary.interruption_count ?? null,
      })
    }

    const lane = byKey.get(key)
    lane.task_count += 1
    lane.start_min = Math.min(lane.start_min, task.start_min)
    lane.end_min = Math.max(lane.end_min, task.end_min)
    lane.tasks.push({
      ...task,
      state_group_path: path,
      state_group_label: stateGroupLabel(primary),
      display_name: `${task.op_rule_code}${task.op_rule_name ? ` - ${task.op_rule_name}` : ''}`,
    })
  }

  return [...byKey.values()]
    .map((lane) => ({
      ...lane,
      tasks: lane.tasks.sort((a, b) => a.start_min - b.start_min || a.step_order - b.step_order),
    }))
    .sort((a, b) =>
      a.start_min - b.start_min ||
      String(a.state_group_code).localeCompare(String(b.state_group_code)),
    )
})
const ganttTasks = computed(() => {
  if (!solveResult.value?.layered || diffMode.value || !ganttHierarchyEnabled.value) {
    return tasks.value
  }
  const collapsed = new Set(collapsedActivityGroupIds.value)
  const result = []
  const taskGroups = new Map()
  for (const task of tasks.value) {
    const key = task.activity_group_id ?? `ungrouped-${task.step_order}`
    if (!taskGroups.has(key)) taskGroups.set(key, [])
    taskGroups.get(key).push(task)
  }
  for (const group of activityGroupRows.value) {
    const groupTasks = taskGroups.get(group.activity_group_id) ?? []
    if (collapsed.has(group.activity_group_id)) {
      result.push({
        row_type: 'activity_group',
        step_order: null,
        op_rule_code: `GROUP_${group.activity_group_code || group.activity_group_id}`,
        op_rule_name: group.activity_group_name,
        display_name: `${group.activity_group_code || group.activity_group_id} (${group.task_count} 个任务)`,
        start_min: group.start_min,
        end_min: group.end_min,
        duration_min: group.end_min - group.start_min,
        step_role: 'normal',
      })
    } else {
      for (const task of groupTasks.sort((a, b) => a.start_min - b.start_min || a.step_order - b.step_order)) {
        result.push({
          ...task,
          display_name: `${task.activity_group_code || '未分组'} / ${task.op_rule_code}`,
        })
      }
    }
    taskGroups.delete(group.activity_group_id)
  }
  for (const groupTasks of taskGroups.values()) {
    result.push(...groupTasks)
  }
  return result
})
const taskTableRows = computed(() => {
  if (!solveResult.value?.layered || !layeredActivityRows.value.length) {
    return tasks.value.map((task) => ({ ...task, row_key: `task-${task.step_order}`, row_type: 'task' }))
  }
  const tasksByActivityNode = new Map()
  for (const task of tasks.value) {
    const key = task.activity_node_id ?? `task-${task.step_order}`
    if (!tasksByActivityNode.has(key)) tasksByActivityNode.set(key, [])
    tasksByActivityNode.get(key).push(task)
  }
  const toRows = (nodes) => nodes.map((node) => {
    const children = []
    if (node.children?.length) children.push(...toRows(node.children))
    const nodeTasks = tasksByActivityNode.get(node.activity_node_id) ?? []
    children.push(...nodeTasks
      .sort((a, b) => a.step_order - b.step_order)
      .map((task) => ({ ...task, row_key: `task-${task.step_order}`, row_type: 'task', children: [] })))
    return {
      ...node,
      row_key: `activity-${node.activity_node_id}`,
      row_type: 'activity',
      children,
    }
  })
  return toRows(layeredActivityRows.value)
})

// ── Helpers ───────────────────────────────────────────────────
function stateLabel(s) {
  const feats = Object.entries(s.features ?? {}).map(([k, v]) => `${k}:${v}`).join(' / ')
  return `${s.label ?? '未命名'} (${s.state_type})${feats ? ' — ' + feats : ''}`
}

function formatResources(resources) {
  if (!Array.isArray(resources) || resources.length === 0) return '—'
  const labels = resources
    .map((r) => {
      if (typeof r === 'string' || typeof r === 'number') return String(r)
      if (!r || typeof r !== 'object') return ''
      return r.resource_code ?? r.code ?? r.resource_name ?? ''
    })
    .filter(Boolean)
  return labels.length ? labels.join(', ') : '—'
}

function formatChangedFeatures(changed) {
  const entries = Object.entries(changed || {})
  if (!entries.length) return '—'
  return entries.map(([key, value]) => `${key}: ${value.from_value ?? '—'} → ${value.to_value ?? '—'}`).join('；')
}

function formatLayeredPrecondition(item) {
  const source = item.source_type === 'self_activity_rule' ? '自有' : item.scope_guard_name || item.source_type
  const target = item.feature_key || item.state_node_code || '-'
  const value = item.feature_value ? `${item.operator} ${item.feature_value}` : item.operator
  return `${source}:${target} ${value}`
}

function selectionTagType(row) {
  if (row.is_shared_provider) return 'success'
  if (row.status === 'selected') return 'primary'
  if (row.reason === 'effects_already_satisfied') return 'info'
  return 'warning'
}

function selectionStatusLabel(row) {
  if (row.is_shared_provider) return '复用'
  if (row.status === 'selected') return '已选择'
  return '已跳过'
}

function selectionReasonLabel(reason) {
  const labels = {
    selected_by_planner: 'Planner 选择',
    effects_already_satisfied: '当前状态已满足',
    not_demanded_by_selected_plan: '未被目标或已选前置需要',
    not_required_by_minimal_plan: '最小必要活动集未采用',
  }
  return labels[reason] ?? reason ?? '—'
}

function formatSelectionConsumers(row) {
  const consumers = row.consumers || []
  if (!consumers.length) return '—'
  return consumers
    .map((item) => {
      if (item.type === 'goal_fact') return `目标:${item.state_node_code || item.feature_key}`
      if (item.type === 'scheduled_precondition') return `前置:${item.op_rule_code}`
      return item.type
    })
    .join(' / ')
}

function formatStateSource(row) {
  if (row.level !== 3) return '—'
  if (row.source_op_rule_codes?.length) {
    return row.source_op_rule_codes
      .map((code, index) => {
        const step = row.source_step_orders?.[index]
        return step != null ? `${step}. ${code}` : code
      })
      .join(' / ')
  }
  if (row.status === 'complete') return '当前状态已满足'
  return '—'
}

function formatGoalSource(row) {
  const source = row.source || {}
  if (source.source_type === 'activity') {
    const step = source.step_order != null ? `${source.step_order}. ` : ''
    return `${step}${source.op_rule_code || source.activity_node_code || '活动'}`
  }
  if (source.source_type === 'current_state') return '当前状态已满足'
  return row.satisfied ? '已满足' : '未满足'
}

function stateGroupPath(task) {
  const direct = Array.isArray(task?.state_continuity_groups)
    ? task.state_continuity_groups.filter((group) => group?.state_group_id != null)
    : []
  if (direct.length) return direct

  return stateContinuityGroups.value.filter((group) =>
    Array.isArray(group?.task_step_orders) && group.task_step_orders.includes(task?.step_order),
  )
}

function hasStateGroupMembership(task) {
  return stateGroupPath(task).length > 0
}

function resultHasStateLaneData(result) {
  const resultTasks = result?.schedule?.tasks ?? []
  if (resultTasks.some((task) =>
    Array.isArray(task?.state_continuity_groups) &&
    task.state_continuity_groups.some((group) => group?.state_group_id != null),
  )) {
    return true
  }

  const stepOrders = new Set(resultTasks.map((task) => task.step_order))
  const diagnosticGroups = result?.diagnostics?.schedule?.state_group_continuity?.groups ?? []
  return diagnosticGroups.some((group) =>
    Array.isArray(group?.task_step_orders) &&
    group.task_step_orders.some((stepOrder) => stepOrders.has(stepOrder)),
  )
}

function stateGroupLabel(group) {
  if (!group) return '未归属状态包'
  return group.state_group_code || group.state_group_name || `状态包#${group.state_group_id}`
}

function continuityGroupKey(group) {
  return group.state_group_id ?? group.activity_group_id ?? group.state_group_code ?? group.activity_group_code
}

function continuityGroupLabel(group) {
  return group.state_group_code ||
    group.activity_group_code ||
    group.state_group_name ||
    group.activity_group_name ||
    group.state_group_id ||
    group.activity_group_id ||
    '未命名分组'
}

function continuityReason(row) {
  const groupText = solveResult.value?.layered ? '状态包' : '二级活动'
  if (row.is_compact) return `同一${groupText}内任务形成紧凑窗口`
  if (row.interruption_count > 0) return `窗口内插入 ${row.interruption_count} 个其他${groupText}任务`
  if (row.internal_gap_min > 0) return `前置条件或资源安排造成同${solveResult.value?.layered ? '包' : '组'}任务空档`
  return `${groupText}连续性软成本未改变该组排序`
}

function activityNodeGroupLabel(row) {
  if (row.level === 2) return row.activity_node_code
  return row.scheduled_task_count ? `${row.scheduled_task_count} 个任务` : '—'
}

function isActivityGroupCollapsed(groupId) {
  return collapsedActivityGroupIds.value.includes(groupId)
}

function toggleActivityGroup(groupId) {
  if (groupId == null) return
  const collapsed = new Set(collapsedActivityGroupIds.value)
  if (collapsed.has(groupId)) collapsed.delete(groupId)
  else collapsed.add(groupId)
  collapsedActivityGroupIds.value = [...collapsed]
}

function healthTagType(status) {
  if (status === 'ok') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'blocked') return 'danger'
  return 'info'
}

function healthStatusLabel(status) {
  const labels = {
    ok: '通过',
    warning: '有警告',
    blocked: '有阻塞',
  }
  return labels[status] ?? status ?? '未知'
}

function diagnosticSeverityTag(severity) {
  if (severity === 'error') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function formatHealthDiagnostic(row) {
  const parts = []
  if (row.feature_key) parts.push(row.target_value ? `${row.feature_key}=${row.target_value}` : row.feature_key)
  if (row.op_rule_id) parts.push(`rule#${row.op_rule_id}`)
  if (row.activity_node_id) parts.push(`activity#${row.activity_node_id}`)
  if (row.state_node_id) parts.push(`state#${row.state_node_id}`)
  if (row.provider_count != null) parts.push(`providers:${row.provider_count}`)
  return parts.join(' / ') || '—'
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

function solveObjectives() {
  const objectives = [{ type: 'minimize_makespan', weight: 1.0 }]
  if (!continuityEnabled.value) return objectives

  const weight = Number(continuityWeight.value) || 1.0
  if (!stateContinuityAvailable.value) {
    return [
      ...objectives,
      { type: 'minimize_activity_group_span', weight },
      { type: 'minimize_activity_group_gaps', weight },
      { type: 'minimize_activity_group_interruptions', weight },
    ]
  }

  return [
    ...objectives,
    { type: 'minimize_state_group_span', weight },
    { type: 'minimize_state_group_gaps', weight },
    { type: 'minimize_state_group_interruptions', weight },
  ]
}

// ── API Actions ───────────────────────────────────────────────
async function loadMachines() {
  machines.value = await getMachines()
  try {
    const reasons = await getBlockageReasons()
    blockageReasonOptions.value = Array.isArray(reasons) ? reasons : []
  } catch {
    blockageReasonOptions.value = []
  }
}

async function onMachineChange() {
  states.value = []
  layeredActivityNodes.value = []
  layeredStateNodes.value = []
  maintenanceIntentTemplates.value = []
  layeredTargetStateNodeIds.value = []
  layeredActivityScopeNodeIds.value = []
  selectedMaintenanceIntentTemplateIds.value = []
  collapsedActivityGroupIds.value = []
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

  const machine = machines.value.find((m) => m.id === solveForm.value.machine_id)
  if (!machine?.machine_type_id) return
  const [activities, stateNodes, stateReferences, maintenanceTemplates] = await Promise.all([
    getActivityNodes(machine.machine_type_id),
    getStateNodes(machine.machine_type_id),
    getStateNodeReferences(machine.machine_type_id),
    getMaintenanceIntentTemplates(machine.machine_type_id, { include_inactive: false }),
  ])
  layeredActivityNodes.value = activities
  layeredStateNodes.value = stateNodesWithReferenceParents(stateNodes, stateReferences)
  maintenanceIntentTemplates.value = maintenanceTemplates
}

async function runSolve() {
  if (!solveForm.value.machine_id || !solveForm.value.current_state_id) {
    return ElMessage.warning('请完整选择设备和当前状态')
  }
  if (solveMode.value === 'snapshot' && !solveForm.value.target_state_id) {
    return ElMessage.warning('请选择目标状态')
  }
  if (solveMode.value === 'snapshot' && solveForm.value.current_state_id === solveForm.value.target_state_id) {
    return ElMessage.warning('当前状态和目标状态不能相同')
  }
  if (solveMode.value === 'layered' && !layeredTargetStateNodeIds.value.length) {
    return ElMessage.warning('请选择分层目标状态')
  }
  if (solveMode.value === 'maintenance' && !selectedMaintenanceIntentTemplateIds.value.length) {
    return ElMessage.warning('请选择维护意图')
  }
  solving.value = true
  diffMode.value = false
  try {
    let result
    if (solveMode.value === 'layered') {
      result = await postLayeredSolve({
        machine_id: solveForm.value.machine_id,
        current_state_id: solveForm.value.current_state_id,
        target_state_node_ids: layeredTargetStateNodeIds.value,
        activity_scope_node_ids: layeredActivityScopeNodeIds.value,
        objectives: solveObjectives(),
      })
    } else if (solveMode.value === 'maintenance') {
      result = await postMaintenanceSolve({
        machine_id: solveForm.value.machine_id,
        current_state_id: solveForm.value.current_state_id,
        intent_template_ids: selectedMaintenanceIntentTemplateIds.value,
        objectives: solveObjectives(),
      })
    } else {
      result = await postSolve({
        machine_id: solveForm.value.machine_id,
        current_state_id: solveForm.value.current_state_id,
        target_state_id: solveForm.value.target_state_id,
        objectives: solveObjectives(),
      })
    }
    // HTTP 200 but solve failed (e.g. no solution, infeasible)
    if (result.status !== 'done') {
      console.error('[solve failed]', result)
      window.__lastSolveDiagnostics = result.diagnostics ?? result
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
  collapsedActivityGroupIds.value = []
  ganttViewMode.value = resultHasStateLaneData(result) ? 'state-lane' : 'traditional'
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
    ganttViewMode.value = 'traditional'
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
.solve-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.page-heading {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.page-heading h2 {
  margin: 0;
  color: #0f172a;
}

.solve-control-card {
  border-radius: 8px;
}

.solve-toolbar {
  display: grid;
  grid-template-columns: 130px minmax(220px, 1.1fr) minmax(220px, 1.2fr) minmax(220px, 1.2fr) minmax(220px, 1.2fr) minmax(260px, 1fr) 210px;
  gap: 12px;
  align-items: end;
}

.solve-toolbar :deep(.el-form-item) {
  margin-bottom: 0;
}

.solve-toolbar :deep(.el-select) {
  width: 100%;
}

.objective-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 32px;
  color: #475569;
  font-size: 13px;
}

.objective-weight {
  width: 108px;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: 32px;
}

.empty-result {
  min-height: 360px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  background: #ffffff;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.metric-item {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.metric-item span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
}

.metric-item strong {
  color: #0f172a;
  font-size: 24px;
  line-height: 1;
}

.metric-item.primary {
  border-color: #99f6e4;
  background: #f0fdfa;
}

.result-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.info-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.info-label {
  min-width: 64px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.diff-alert {
  margin: 0;
}

.result-tabs {
  min-width: 0;
  padding: 0 16px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.workspace-panel {
  min-width: 0;
  padding-top: 8px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  color: #0f172a;
  font-weight: 600;
}

.gantt-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.hierarchy-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.parallel-section {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.section-label {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.version-panel {
  max-width: 760px;
}

.layered-panel {
  max-width: 1200px;
}

.layered-table {
  margin-bottom: 12px;
}

.split-title {
  margin-top: 18px;
}

.muted {
  color: #94a3b8;
  font-size: 13px;
}

@media (max-width: 1280px) {
  .solve-toolbar {
    grid-template-columns: repeat(2, minmax(220px, 1fr));
  }

  .metric-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .solve-toolbar,
  .metric-strip {
    grid-template-columns: 1fr;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }
}
</style>
