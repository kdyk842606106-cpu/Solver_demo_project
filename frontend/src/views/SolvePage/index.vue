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
            <span class="objective-rule-label">集成规则</span>
            <el-select
              v-model="selectedSchedulingRuleCodes"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="选择排期规则"
              class="scheduling-rule-select"
              data-testid="solve-scheduling-rule-select"
            >
              <el-option
                v-for="rule in schedulingRuleOptions"
                :key="rule.code"
                :label="schedulingRuleOptionLabel(rule)"
                :value="rule.code"
                :disabled="rule.activation_mode === 'required' || !rule.applicable"
              />
            </el-select>
          </div>
        </el-form-item>

        <el-form-item label="工作日历">
          <div class="calendar-controls">
            <el-switch v-model="calendarEnabled" active-text="启用" />
            <el-date-picker
              v-if="calendarEnabled"
              v-model="scheduleStartAt"
              type="datetime"
              placeholder="选择计划开始时间"
              format="YYYY-MM-DD HH:mm"
            />
            <el-input v-if="calendarEnabled" v-model="scheduleTimezone" style="width:150px" />
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

    <el-card v-if="failedExceptionCandidates.length" class="version-card">
      <template #header>无解任务的规则例外</template>
      <el-alert title="原计划已保留。可对具体任务显式申请一次例外并生成子计划完整重排。" type="warning" :closable="false" />
      <el-table :data="failedExceptionCandidates" size="small" border style="margin-top: 12px">
        <el-table-column prop="step_order" label="步骤" width="80" />
        <el-table-column prop="op_rule_code" label="活动" width="180" />
        <el-table-column prop="op_rule_name" label="名称" />
        <el-table-column label="可例外规则" min-width="220">
          <template #default="{ row }">{{ (row.matched_scheduling_rules || []).join(' / ') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }"><el-button type="primary" size="small" @click="openRuleException(row)">申请例外</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-empty v-if="!solveResult && !failedExceptionCandidates.length" class="empty-result" description="尚未执行求解" />

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

      <div class="adjustment-toolbar" :class="{ selecting: adjustmentSelecting }">
        <template v-if="!adjustmentSelecting">
          <div>
            <strong>计划基线调整</strong>
            <span class="muted">显式选择活动范围后，以约束方式生成候选计划。</span>
          </div>
          <el-button type="primary" plain :disabled="diffMode" @click="startAdjustmentSelection">
            计划调整 / 重排
          </el-button>
        </template>
        <template v-else>
          <div class="adjustment-selection-summary">
            <strong>选择待调整范围</strong>
            <el-tag type="primary">已选择 {{ adjustmentScopeStepIds.length }} 个活动</el-tag>
            <span class="muted">可使用任务表、业务分组、甘特单击或右上角矩形框选。</span>
          </div>
          <div class="adjustment-group-actions">
            <el-button
              v-for="group in activityGroupRows"
              :key="`adjust-group-${group.activity_group_id}`"
              size="small"
              @click="addActivityGroupToAdjustment(group.activity_group_id)"
            >选择活动组 {{ group.activity_group_code || group.activity_group_id }}</el-button>
            <el-button
              v-for="group in stateLaneGroups"
              :key="`adjust-state-${group.state_group_id || group.key}`"
              size="small"
              @click="addAdjustmentStepIds((group.tasks || []).map((task) => task.step_id))"
            >选择状态包 {{ group.state_group_code || group.key }}</el-button>
          </div>
          <div class="adjustment-selection-actions">
            <el-button @click="adjustmentScopeStepIds = []">清空</el-button>
            <el-button @click="cancelAdjustmentSelection">取消调整</el-button>
            <el-button type="primary" @click="confirmAdjustmentScope">确认范围并编辑约束</el-button>
          </div>
        </template>
      </div>

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
              :time-mode="solveResult.calendar_summary?.enabled ? 'datetime' : 'minute'"
              :schedule-start-at="solveResult.schedule_start_at || ''"
              :rule-presentations="ganttRulePresentations"
              :selection-mode="adjustmentSelecting"
              :selected-step-ids="adjustmentScopeStepIds"
              @toggle-task="toggleAdjustmentStep"
              @brush-select="addAdjustmentStepIds"
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
              <el-table-column v-if="adjustmentSelecting" label="调整范围" width="100" fixed="left">
                <template #default="{ row }">
                  <el-checkbox
                    :model-value="isAdjustmentRowSelected(row)"
                    :indeterminate="isAdjustmentRowIndeterminate(row)"
                    @change="toggleAdjustmentRow(row)"
                  />
                </template>
              </el-table-column>
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
              <el-table-column label="责任子系统" min-width="130" show-overflow-tooltip>
                <template #default="{ row }">{{ row.row_type === 'task' ? (row.responsible_subsystem || '-') : '-' }}</template>
              </el-table-column>
              <el-table-column label="命中规则" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.row_type === 'task' ? (row.matched_scheduling_rules || []).join(' / ') || '-' : '-' }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="210" fixed="right">
                <template #default="{ row }">
                  <template v-if="row.row_type === 'task'">
                    <el-button size="small" type="warning" @click="openBlockage(row)">标记阻塞</el-button>
                    <el-button
                      v-if="overridableRulesForTask(row).length"
                      size="small"
                      type="primary"
                      @click="openRuleException(row)"
                    >规则例外</el-button>
                  </template>
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
      :atomic-activity-scope-ids="layeredAtomicActivityScopeIds"
      :maintenance-intent-template-ids="selectedMaintenanceIntentTemplateIds"
      :blockage-reason-options="blockageReasonOptions"
      @replanned="onReplanned"
      @adjustment-requested="openBlockageScheduleAdjustment"
    />
    <PlanAdjustmentDrawer
      v-model="adjustmentDrawerVisible"
      :adjustment-id="adjustmentId"
      :tasks="adjustmentScopeTasks"
      :initial-constraints="adjustmentInitialConstraints"
      :calendar-enabled="calendarEnabled"
      :schedule-start-at="solveResult?.schedule_start_at || scheduleStartAt || ''"
      :timezone="scheduleTimezone"
      @edit-scope="editAdjustmentScope"
      @confirmed="onAdjustmentConfirmed"
      @cancelled="resetAdjustmentState"
    />
    <el-dialog v-model="exceptionDialogVisible" title="申请排期规则例外" width="520px">
      <el-form :model="exceptionForm" label-width="100px">
        <el-form-item label="活动">
          <span>{{ selectedExceptionTask?.op_rule_name || selectedExceptionTask?.op_rule_code }}</span>
        </el-form-item>
        <el-form-item label="规则" required>
          <el-select v-model="exceptionForm.rule_code" style="width: 100%">
            <el-option
              v-for="rule in selectedExceptionRules"
              :key="rule.code"
              :label="`${rule.name} (${rule.code})`"
              :value="rule.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="selectedExceptionRule?.type === 'shift_restriction'" label="额外允许 shift" required>
          <el-select v-model="exceptionForm.allow_shift_codes" multiple filterable allow-create default-first-option style="width: 100%" />
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="exceptionForm.reason" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exceptionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="exceptionSubmitting" @click="submitRuleException">确认并完整重排</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GanttChart from '../../components/GanttChart.vue'
import ActivityNetworkBoard from '../../components/ActivityNetworkBoard.vue'
import BlockageDialog from '../../components/BlockageDialog.vue'
import PlanAdjustmentDrawer from '../../components/PlanAdjustmentDrawer.vue'
import VersionHistory from './VersionHistory.vue'
import { buildHierarchyTree, treeSelectProps } from '../../utils/hierarchyTree'
import {
  getActivityNodes,
  getActivityPackageAtomicRefs,
  getBlockageReasons,
  getMachines,
  getMaintenanceIntentTemplates,
  getMachineTypes,
  getSchedulingRuleTypes,
  getStateNodes,
  getStateNodeReferences,
  getStates,
} from '../../api/masterData'
import {
  cancelPlanAdjustment,
  confirmPlanAdjustment,
  createPlanAdjustment,
  getPlanDiff,
  getPlanVersions,
  getSolveRequest,
  postLayeredSolve,
  postMaintenanceSolve,
  postSolve,
  updatePlanAdjustment,
} from '../../api/solve'

// ── State ─────────────────────────────────────────────────────
const machines = ref([])
const machineTypes = ref([])
const states = ref([])
const layeredActivityNodes = ref([])
const layeredAtomicRefs = ref([])
const layeredStateNodes = ref([])
const maintenanceIntentTemplates = ref([])
const schedulingRuleTypes = ref([])
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
const selectedSchedulingRuleCodes = ref([])
const calendarEnabled = ref(false)
const scheduleStartAt = ref(null)
const scheduleTimezone = ref('Asia/Shanghai')
const ganttHierarchyEnabled = ref(true)
const ganttViewMode = ref('traditional')
const collapsedActivityGroupIds = ref([])

const solveResult = ref(null)
const currentPlanId = ref(null)
const versionChain = ref([])
const adjustmentSelecting = ref(false)
const adjustmentDrawerVisible = ref(false)
const adjustmentId = ref(null)
const adjustmentScopeStepIds = ref([])
const adjustmentScopeConfirmedOnce = ref(false)
const adjustmentInitialConstraints = ref([])

const blockageVisible = ref(false)
const selectedTask = ref(null)
const exceptionDialogVisible = ref(false)
const exceptionSubmitting = ref(false)
const selectedExceptionTask = ref(null)
const exceptionForm = ref({ rule_code: '', allow_shift_codes: [], reason: '' })
const failedExceptionCandidates = ref([])

// Diff mode
const diffMode = ref(false)
const diffSteps = ref([])
const basePlanVersion = ref(null)
const currentPlanVersion = ref(null)

// ── Computed ──────────────────────────────────────────────────
const tasks = computed(() => solveResult.value?.schedule?.tasks ?? [])
const adjustmentScopeTasks = computed(() => {
  const selected = new Set(adjustmentScopeStepIds.value)
  return tasks.value.filter((task) => selected.has(task.step_id))
})
const selectedMachine = computed(() => machines.value.find((item) => item.id === solveForm.value.machine_id) || null)
const selectedMachineType = computed(() =>
  machineTypes.value.find((item) => item.id === selectedMachine.value?.machine_type_id) || null,
)
const schedulingRuleTypeByCode = computed(() => new Map(
  schedulingRuleTypes.value.map((item) => [item.type, item]),
))
const allSchedulingRules = computed(() => {
  const rules = []
  const seen = new Set()
  const configuredTypes = new Set()
  for (const rule of selectedMachineType.value?.scheduling_config?.rules || []) {
    if (rule.enabled === false || seen.has(rule.code)) continue
    seen.add(rule.code)
    configuredTypes.add(rule.type)
    rules.push({ ...rule, builtin: false })
  }
  for (const descriptor of schedulingRuleTypes.value) {
    const rule = descriptor.builtin_rule
    if (!rule || seen.has(rule.code) || configuredTypes.has(rule.type)) continue
    seen.add(rule.code)
    rules.push({ ...rule, builtin: true })
  }
  return rules
})
const schedulingRuleOptions = computed(() => allSchedulingRules.value.map((rule) => ({
  ...rule,
  applicable: schedulingRuleSupportedInMode(rule),
})))
const configuredSchedulingRules = computed(() =>
  schedulingRuleOptions.value.filter((rule) => rule.applicable),
)
const selectedExceptionRules = computed(() => overridableRulesForTask(selectedExceptionTask.value))
const selectedExceptionRule = computed(() =>
  selectedExceptionRules.value.find((item) => item.code === exceptionForm.value.rule_code) || null,
)
const layeredStateTreeOptions = computed(() =>
  buildHierarchyTree(layeredStateNodes.value),
)
const layeredActivityTreeOptions = computed(() =>
  buildHierarchyTree(layeredActivityNodes.value, { disabled: (node) => node.level > 2 }),
)
const layeredAtomicActivityScopeIds = computed(() => {
  if (!layeredActivityScopeNodeIds.value.length) return []
  const selectedPackageIds = new Set(layeredActivityScopeNodeIds.value.map(Number))
  let changed = true
  while (changed) {
    changed = false
    for (const node of layeredActivityNodes.value) {
      if (node.parent_id && selectedPackageIds.has(Number(node.parent_id)) && !selectedPackageIds.has(Number(node.id))) {
        selectedPackageIds.add(Number(node.id))
        changed = true
      }
    }
  }
  return [...new Set(
    layeredAtomicRefs.value
      .filter((ref) => ref.is_active && selectedPackageIds.has(Number(ref.activity_node_id)))
      .map((ref) => Number(ref.atomic_activity_id)),
  )].sort((left, right) => left - right)
})
const stateDelta = computed(() => solveResult.value?.state_delta ?? [])
const criticalPath = computed(() => solveResult.value?.critical_path ?? [])
const parallelGroups = computed(() => solveResult.value?.schedule?.parallel_groups ?? [])
const scheduleDiagnostics = computed(() => solveResult.value?.diagnostics?.schedule ?? null)
const ganttRulePresentations = computed(() => {
  const result = {}
  const activeRules = scheduleDiagnostics.value?.scheduling_rules?.active_rules ?? []
  for (const rule of activeRules) {
    const marker = rule.presentation?.gantt_marker
    if (!rule.code || !marker?.text) continue
    result[rule.code] = {
      text: marker.text,
      color: marker.color || '#f59e0b',
      rule_name: rule.name || rule.code,
    }
  }
  return result
})
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
  const legacyObjectiveActive = [
    'minimize_activity_group_span',
    'minimize_activity_group_gaps',
    'minimize_activity_group_interruptions',
    'minimize_state_group_span',
    'minimize_state_group_gaps',
    'minimize_state_group_interruptions',
  ].some((key) => Number(weights[key] ?? 0) > 0)
  const activeCodes = new Set(
    scheduleDiagnostics.value?.scheduling_rules?.active_rule_codes
      || selectedSchedulingRuleCodes.value,
  )
  const registeredRuleActive = allSchedulingRules.value.some((rule) =>
    rule.type === 'state_package_continuity' && activeCodes.has(rule.code),
  )
  return legacyObjectiveActive || registeredRuleActive
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
      const ganttMarkerCounts = {}
      for (const task of groupTasks) {
        for (const ruleCode of task.matched_scheduling_rules || []) {
          if (!ganttRulePresentations.value[ruleCode]) continue
          ganttMarkerCounts[ruleCode] = (ganttMarkerCounts[ruleCode] || 0) + 1
        }
      }
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
        gantt_marker_counts: ganttMarkerCounts,
        gantt_shift_segments: groupTasks.flatMap((task) => task.segments || []),
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
  const source = item.source_type === 'self_activity_rule' ? '自有' : item.source_type
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

function validAdjustmentStepIds(stepIds = []) {
  const available = new Set(tasks.value.map((task) => task.step_id).filter((id) => id != null))
  return stepIds.filter((id) => id != null && available.has(id))
}

function addAdjustmentStepIds(stepIds = []) {
  adjustmentScopeStepIds.value = [
    ...new Set([...adjustmentScopeStepIds.value, ...validAdjustmentStepIds(stepIds)]),
  ]
}

function toggleAdjustmentStep(stepId) {
  if (!validAdjustmentStepIds([stepId]).length) return
  const selected = new Set(adjustmentScopeStepIds.value)
  if (selected.has(stepId)) selected.delete(stepId)
  else selected.add(stepId)
  adjustmentScopeStepIds.value = [...selected]
}

function adjustmentRowStepIds(row) {
  if (row?.row_type === 'task') return validAdjustmentStepIds([row.step_id])
  return (row?.children || []).flatMap((child) => adjustmentRowStepIds(child))
}

function isAdjustmentRowSelected(row) {
  const ids = adjustmentRowStepIds(row)
  const selected = new Set(adjustmentScopeStepIds.value)
  return ids.length > 0 && ids.every((id) => selected.has(id))
}

function isAdjustmentRowIndeterminate(row) {
  const ids = adjustmentRowStepIds(row)
  const selected = new Set(adjustmentScopeStepIds.value)
  const selectedCount = ids.filter((id) => selected.has(id)).length
  return selectedCount > 0 && selectedCount < ids.length
}

function toggleAdjustmentRow(row) {
  const ids = adjustmentRowStepIds(row)
  if (!ids.length) return
  const selected = new Set(adjustmentScopeStepIds.value)
  if (ids.every((id) => selected.has(id))) ids.forEach((id) => selected.delete(id))
  else ids.forEach((id) => selected.add(id))
  adjustmentScopeStepIds.value = [...selected]
}

function addActivityGroupToAdjustment(groupId) {
  addAdjustmentStepIds(
    tasks.value
      .filter((task) => task.activity_group_id === groupId)
      .map((task) => task.step_id),
  )
}

function resetAdjustmentState() {
  adjustmentSelecting.value = false
  adjustmentDrawerVisible.value = false
  adjustmentId.value = null
  adjustmentScopeStepIds.value = []
  adjustmentScopeConfirmedOnce.value = false
  adjustmentInitialConstraints.value = []
}

async function startAdjustmentSelection() {
  if (!currentPlanId.value) return ElMessage.warning('请先生成或加载一条计划基线')
  try {
    const adjustment = await createPlanAdjustment(currentPlanId.value, { kind: 'schedule' })
    adjustmentId.value = adjustment.id
    adjustmentScopeStepIds.value = []
    adjustmentScopeConfirmedOnce.value = false
    adjustmentInitialConstraints.value = []
    adjustmentSelecting.value = true
    adjustmentDrawerVisible.value = false
    activeResultTab.value = 'gantt'
  } catch {
    // The shared HTTP interceptor presents the stable backend error.
  }
}

async function confirmAdjustmentScope() {
  if (!adjustmentScopeStepIds.value.length) return ElMessage.warning('请至少选择一个待调整活动')
  try {
    if (!adjustmentScopeConfirmedOnce.value) {
      await updatePlanAdjustment(adjustmentId.value, {
        scope_step_ids: adjustmentScopeStepIds.value,
        constraints: [],
        remove_inherited_constraint_ids: [],
      })
      adjustmentScopeConfirmedOnce.value = true
    }
    adjustmentSelecting.value = false
    adjustmentDrawerVisible.value = true
  } catch {
    // The shared HTTP interceptor presents the stable backend error.
  }
}

function editAdjustmentScope() {
  adjustmentDrawerVisible.value = false
  adjustmentSelecting.value = true
  activeResultTab.value = 'gantt'
}

async function cancelAdjustmentSelection() {
  try {
    if (adjustmentId.value) await cancelPlanAdjustment(adjustmentId.value)
  } finally {
    resetAdjustmentState()
  }
}

async function onAdjustmentConfirmed({ candidatePlanId, solveRequestId }) {
  if (!candidatePlanId || !solveRequestId) {
    resetAdjustmentState()
    return ElMessage.error('新基线已确认，但候选计划结果标识不完整，请刷新后加载该版本')
  }
  try {
    const detail = await getSolveRequest(solveRequestId)
    await applyResult({
      ...detail,
      solve_request_id: detail.id,
      candidate_plan_id: candidatePlanId,
    })
    ElMessage.success('候选计划已确认为新基线')
  } finally {
    resetAdjustmentState()
  }
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
  return [{ type: 'minimize_makespan', weight: 1.0 }]
}

function schedulingRuleSupportedInMode(rule) {
  const descriptor = schedulingRuleTypeByCode.value.get(rule.type)
  const modes = descriptor?.supported_modes || ['snapshot', 'layered', 'maintenance']
  return modes.includes(solveMode.value)
}

function schedulingRuleOptionLabel(rule) {
  if (!rule.applicable) return `${rule.name}（仅分层/维护）`
  if (rule.activation_mode === 'required') return `${rule.name}（必选）`
  return rule.name
}

function syncSelectedSchedulingRules(includeDefaults = false) {
  const applicableRules = schedulingRuleOptions.value.filter((rule) => rule.applicable)
  const applicableCodes = new Set(applicableRules.map((rule) => rule.code))
  const selected = new Set(
    selectedSchedulingRuleCodes.value.filter((code) => applicableCodes.has(code)),
  )
  for (const rule of applicableRules) {
    if (
      rule.activation_mode === 'required'
      || (includeDefaults && (rule.activation_mode || 'default_on') === 'default_on')
    ) {
      selected.add(rule.code)
    }
  }
  selectedSchedulingRuleCodes.value = [...selected]
}

function calendarContext() {
  if (!calendarEnabled.value) return { enabled: false }
  let scheduleStart = scheduleStartAt.value
  if (scheduleStart) {
    const normalized = new Date(scheduleStart)
    if (!Number.isNaN(normalized.getTime())) {
      normalized.setSeconds(0, 0)
      scheduleStart = normalized.toISOString()
    }
  }
  return {
    enabled: true,
    schedule_start_at: scheduleStart,
    display_timezone: scheduleTimezone.value,
    revision_policy: 'latest',
  }
}

function schedulingConstraints(extra = {}) {
  const applicableCodes = new Set(
    schedulingRuleOptions.value.filter((rule) => rule.applicable).map((rule) => rule.code),
  )
  return {
    scheduling_rules: {
      active_rule_codes: selectedSchedulingRuleCodes.value.filter((code) => applicableCodes.has(code)),
      ...extra,
    },
  }
}

// ── API Actions ───────────────────────────────────────────────
async function loadMachines() {
  ;[machines.value, machineTypes.value, schedulingRuleTypes.value] = await Promise.all([
    getMachines(),
    getMachineTypes(),
    getSchedulingRuleTypes(),
  ])
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
  layeredAtomicRefs.value = []
  layeredStateNodes.value = []
  maintenanceIntentTemplates.value = []
  layeredTargetStateNodeIds.value = []
  layeredActivityScopeNodeIds.value = []
  selectedMaintenanceIntentTemplateIds.value = []
  selectedSchedulingRuleCodes.value = []
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
  syncSelectedSchedulingRules(true)
  const [activities, stateNodes, stateReferences, maintenanceTemplates] = await Promise.all([
    getActivityNodes(machine.machine_type_id),
    getStateNodes(machine.machine_type_id),
    getStateNodeReferences(machine.machine_type_id),
    getMaintenanceIntentTemplates(machine.machine_type_id, { include_inactive: false }),
  ])
  layeredActivityNodes.value = activities
  const activityPackages = activities.filter((node) => node.level === 2)
  layeredAtomicRefs.value = (
    await Promise.all(activityPackages.map((node) => getActivityPackageAtomicRefs(node.id)))
  ).flat()
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
  if (calendarEnabled.value && !scheduleStartAt.value) {
    return ElMessage.warning('启用工作日历后必须选择计划开始时间')
  }
  solving.value = true
  failedExceptionCandidates.value = []
  diffMode.value = false
  try {
    let result
    if (solveMode.value === 'layered') {
      result = await postLayeredSolve({
        machine_id: solveForm.value.machine_id,
        current_state_id: solveForm.value.current_state_id,
        target_state_node_ids: layeredTargetStateNodeIds.value,
        atomic_activity_scope_ids: layeredAtomicActivityScopeIds.value,
        objectives: solveObjectives(),
        constraints: schedulingConstraints(),
        calendar_context: calendarContext(),
      })
    } else if (solveMode.value === 'maintenance') {
      result = await postMaintenanceSolve({
        machine_id: solveForm.value.machine_id,
        current_state_id: solveForm.value.current_state_id,
        intent_template_ids: selectedMaintenanceIntentTemplateIds.value,
        objectives: solveObjectives(),
        constraints: schedulingConstraints(),
        calendar_context: calendarContext(),
      })
    } else {
      result = await postSolve({
        machine_id: solveForm.value.machine_id,
        current_state_id: solveForm.value.current_state_id,
        target_state_id: solveForm.value.target_state_id,
        objectives: solveObjectives(),
        constraints: schedulingConstraints(),
        calendar_context: calendarContext(),
      })
    }
    // HTTP 200 but solve failed (e.g. no solution, infeasible)
    if (result.status !== 'done') {
      console.error('[solve failed]', result)
      window.__lastSolveDiagnostics = result.diagnostics ?? result
      failedExceptionCandidates.value = result.exception_candidates || []
      if (result.candidate_plan_id) currentPlanId.value = result.candidate_plan_id
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
  failedExceptionCandidates.value = []
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

function overridableRulesForTask(task) {
  if (!task) return []
  if (Array.isArray(task.overridable_rules) && task.overridable_rules.length) return task.overridable_rules
  const matched = new Set(task.matched_scheduling_rules || [])
  const snapshotRules = scheduleDiagnostics.value?.scheduling_rules?.active_rules || configuredSchedulingRules.value
  return snapshotRules.filter((rule) =>
    matched.has(rule.code) && !!rule.enforcement?.overridable,
  )
}

function openRuleException(task) {
  const rules = overridableRulesForTask(task)
  if (!rules.length) return
  selectedExceptionTask.value = task
  exceptionForm.value = { rule_code: rules[0].code, allow_shift_codes: [], reason: '' }
  exceptionDialogVisible.value = true
}

async function submitRuleException() {
  const task = selectedExceptionTask.value
  const rule = selectedExceptionRule.value
  if (!task?.step_id || !rule || !exceptionForm.value.reason.trim()) {
    return ElMessage.warning('请选择规则并填写例外原因')
  }
  if (rule.type === 'shift_restriction' && !exceptionForm.value.allow_shift_codes.length) {
    return ElMessage.warning('请填写至少一个额外允许的 shift code')
  }
  const constraints = schedulingConstraints({
    new_override: {
      rule_code: rule.code,
      source_step_id: task.step_id,
      parameters: { allow_shift_codes: exceptionForm.value.allow_shift_codes },
      reason: exceptionForm.value.reason.trim(),
    },
    carry_parent_override_keys: [],
  })
  const common = {
    machine_id: solveForm.value.machine_id,
    current_state_id: solveForm.value.current_state_id,
    parent_plan_id: currentPlanId.value,
    objectives: solveObjectives(),
    constraints,
  }
  exceptionSubmitting.value = true
  try {
    let result
    if (solveMode.value === 'layered') {
      result = await postLayeredSolve({
        ...common,
        target_state_node_ids: layeredTargetStateNodeIds.value,
        atomic_activity_scope_ids: layeredAtomicActivityScopeIds.value,
      })
    } else if (solveMode.value === 'maintenance') {
      result = await postMaintenanceSolve({
        ...common,
        intent_template_ids: selectedMaintenanceIntentTemplateIds.value,
      })
    } else {
      result = await postSolve({ ...common, target_state_id: solveForm.value.target_state_id })
    }
    if (result.status !== 'done') {
      ElMessage.error(`${result.error_code ?? 'ERROR'}: ${result.error_message ?? '规则例外重排失败'}`)
      return
    }
    const accepted = await confirmFullReplanCandidate('rule_exception', result, task.step_id)
    if (accepted) {
      exceptionDialogVisible.value = false
      ElMessage.success('规则例外候选已确认为新基线')
    }
  } finally {
    exceptionSubmitting.value = false
  }
}

// ── Blockage ──────────────────────────────────────────────────
function openBlockage(task) {
  selectedTask.value = task
  blockageVisible.value = true
}

async function onReplanned(result) {
  const accepted = await confirmFullReplanCandidate(
    'blockage',
    result,
    selectedTask.value?.step_id,
  )
  if (accepted) ElMessage.success('阻塞重排候选已确认为新基线')
}

async function openBlockageScheduleAdjustment({ stepId, notBeforeMin }) {
  if (!currentPlanId.value || !stepId) return
  try {
    const constraint = {
      type: 'not_before',
      step_ids: [stepId],
      value_min: notBeforeMin,
    }
    const adjustment = await createPlanAdjustment(currentPlanId.value, {
      kind: 'blockage',
      scope_step_ids: [stepId],
      constraints: [constraint],
    })
    adjustmentId.value = adjustment.id
    adjustmentScopeStepIds.value = [stepId]
    adjustmentScopeConfirmedOnce.value = true
    adjustmentInitialConstraints.value = [constraint]
    adjustmentSelecting.value = false
    adjustmentDrawerVisible.value = true
  } catch {
    // The shared HTTP interceptor presents the stable backend error.
  }
}

async function confirmFullReplanCandidate(kind, result, sourceStepId) {
  if (!currentPlanId.value || !result?.candidate_plan_id) return false
  let adjustment
  try {
    adjustment = await createPlanAdjustment(currentPlanId.value, {
      kind,
      scope_step_ids: sourceStepId ? [sourceStepId] : [],
      candidate_plan_id: result.candidate_plan_id,
    })
    const summary = adjustment.preview_summary || {}
    await ElMessageBox.confirm(
      `候选包含 ${summary.candidate_task_count ?? '—'} 个活动，基线包含 ${summary.base_task_count ?? '—'} 个活动，工期变化 ${summary.makespan_delta_min ?? '—'} 分钟。确认后才会替换当前计划基线。`,
      kind === 'blockage' ? '确认阻塞重排候选' : '确认规则例外候选',
      { type: 'warning', confirmButtonText: '确认为新基线', cancelButtonText: '保留原基线' },
    )
    await confirmPlanAdjustment(adjustment.id)
    await applyResult(result)
    return true
  } catch (error) {
    if (adjustment?.id) {
      try {
        await cancelPlanAdjustment(adjustment.id)
      } catch {
        // Preserve the original error/cancel outcome.
      }
    }
    return false
  }
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

watch(solveMode, () => syncSelectedSchedulingRules(true))

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

.objective-controls,
.calendar-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 32px;
  color: #475569;
  font-size: 13px;
}

.objective-rule-label {
  white-space: nowrap;
}

.scheduling-rule-select {
  min-width: 260px;
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

.adjustment-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
}

.adjustment-toolbar.selecting {
  align-items: flex-start;
  border-color: #93c5fd;
  background: #dbeafe;
}

.adjustment-selection-summary,
.adjustment-group-actions,
.adjustment-selection-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.adjustment-selection-summary {
  flex: 1 1 360px;
}

.adjustment-group-actions {
  flex: 1 1 100%;
}

.adjustment-selection-actions {
  margin-left: auto;
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
