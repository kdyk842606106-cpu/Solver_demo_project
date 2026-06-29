<template>
  <div class="network-editor" data-testid="network-editor">
    <div class="workspace-toolbar" data-testid="network-editor-toolbar">
      <div>
        <h2>网络编辑器</h2>
        <p>预览已提交网络，进入编辑后维护草稿并统一提交到数据库。</p>
      </div>
      <div class="toolbar-controls">
        <el-select
          v-model="machineTypeId"
          data-testid="network-editor-machine-type-select"
          placeholder="选择设备类型"
          filterable
          default-first-option
          style="width: 300px"
          @change="onTypeChange"
        >
          <el-option-group
            v-for="group in machineTypeOptionGroups"
            :key="group.label"
            :label="group.label"
          >
            <el-option
              v-for="item in group.items"
              :key="`${group.label}-${item.id}`"
              :label="machineTypeOptionLabel(item)"
              :value="item.id"
            />
          </el-option-group>
        </el-select>
        <el-segmented
          v-model="viewMode"
          data-testid="network-editor-view-mode"
          aria-label="视图模式"
          :options="[
            { label: '纲要', value: 'outline' },
            { label: '实现', value: 'implementation' },
            { label: '求解', value: 'solver_ready' },
          ]"
          @change="reloadGraph"
        />
        <el-switch v-model="includeInactive" data-testid="network-editor-include-inactive" active-text="停用" @change="reloadGraph" />
        <el-tag :type="isEditMode ? 'warning' : 'info'">{{ editorModeLabel }}</el-tag>
        <el-tag v-if="hasDraftChanges" type="danger">未提交 {{ draftChangeCount }}</el-tag>
        <el-button v-if="!isEditMode" type="primary" :icon="EditPen" :disabled="!machineTypeId" data-testid="network-editor-enter-edit" @click="startEditSession">
          进入编辑
        </el-button>
        <template v-else>
          <el-button type="success" :icon="Check" :disabled="!hasDraftChanges" :loading="draftSubmitting" data-testid="network-editor-submit-draft" @click="submitDraftChanges">
            统一提交
          </el-button>
          <el-button :icon="Close" :disabled="draftSubmitting" data-testid="network-editor-cancel-edit" @click="cancelEditSession">取消编辑</el-button>
        </template>
        <el-button :icon="Plus" :disabled="!canMutate" data-testid="network-editor-create-state" @click="openCreateState()">新建状态</el-button>
        <el-button :icon="Plus" :disabled="!canMutate" data-testid="network-editor-create-activity" @click="openCreateActivityNode()">新建虚拟活动</el-button>
        <el-button :icon="Plus" :disabled="!canMutate" data-testid="network-editor-create-atomic" @click="openCreateAtomicActivity()">新建原子活动</el-button>
        <el-button :icon="Refresh" :disabled="!canMutate" data-testid="network-editor-auto-arrange" @click="autoArrangeCanvas">自动整理</el-button>
        <el-button :icon="Refresh" :disabled="!machineTypeId || draftSubmitting" data-testid="network-editor-refresh" @click="refreshWorkspace">刷新</el-button>
        <el-button
          :icon="Search"
          data-testid="network-editor-impact"
          :disabled="!machineTypeId || (!selectedStateId && !selectedActivityGraphId)"
          :loading="impactLoading"
          @click="loadImpact({ immediate: true })"
        >
          影响分析
        </el-button>
        <el-button type="primary" :icon="Link" :disabled="!machineTypeId" data-testid="network-editor-validate" @click="runValidation">校验</el-button>
        <el-button :icon="Search" :disabled="!machineTypeId" data-testid="network-editor-solver-precheck" @click="runSolverPrecheck">求解预检</el-button>
      </div>
    </div>

    <el-empty v-if="!machineTypeId" description="先选择一个设备类型" />

    <template v-else>
      <div class="focus-strip" data-testid="network-editor-focus-strip">
        <el-select
          v-model="selectedStateRootIds"
          multiple
          collapse-tags
          collapse-tags-tooltip
          filterable
          placeholder="状态根节点"
          style="min-width: 260px"
          @change="reloadGraph"
        >
          <el-option v-for="item in stateNodes" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
        </el-select>
        <el-select
          v-model="selectedActivityScopeIds"
          multiple
          collapse-tags
          collapse-tags-tooltip
          filterable
          placeholder="活动范围"
          style="min-width: 260px"
          @change="reloadGraph"
        >
          <el-option v-for="item in activityScopeOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
        </el-select>
        <div class="depth-control">
          <span>状态深度</span>
          <el-input-number v-model="stateDepth" :min="0" :max="12" controls-position="right" @change="reloadGraph" />
        </div>
        <div class="depth-control">
          <span>活动深度</span>
          <el-input-number v-model="activityDepth" :min="0" :max="12" controls-position="right" @change="reloadGraph" />
        </div>
        <el-button :disabled="!selectedStateId && !selectedActivityGraphId" @click="focusCurrentSelection">聚焦选中</el-button>
        <el-button :disabled="!selectedStateId && !selectedActivityGraphId" @click="collapseCurrentSelection">折叠选中</el-button>
        <el-button :disabled="!selectedStateId && !selectedActivityGraphId" @click="expandCurrentSelectionOneLevel">展开一层</el-button>
        <el-button :disabled="!selectedStateId && !selectedActivityGraphId" @click="expandCurrentSelectionAll">展开全部</el-button>
        <el-button :disabled="!selectedStateRootIds.length && !selectedActivityScopeIds.length" @click="clearGraphFocus">清除焦点</el-button>
      </div>

      <div v-if="focusedActivityCanvas" class="focus-context-strip" data-testid="network-editor-activity-focus-strip">
        <div class="focus-context-main">
          <el-tag size="small" type="primary">专注画布</el-tag>
          <span
            v-for="item in focusedActivityCanvas.breadcrumb"
            :key="item.id"
            class="focus-breadcrumb-item"
          >
            {{ nodeLabel(item) }}
          </span>
        </div>
        <div class="focus-boundaries">
          <span>上下文</span>
          <el-tag
            v-for="state in focusedActivityCanvas.contextStates.slice(0, 3)"
            :key="`ctx-${state.id}`"
            size="small"
            effect="plain"
          >
            {{ nodeLabel(state) }}
          </el-tag>
          <el-tag v-if="focusedActivityCanvas.contextStates.length > 3" size="small" effect="plain">
            +{{ focusedActivityCanvas.contextStates.length - 3 }}
          </el-tag>
          <span>输出</span>
          <el-tag
            v-for="state in focusedActivityCanvas.outputStates.slice(0, 3)"
            :key="`out-${state.id}`"
            size="small"
            type="success"
            effect="plain"
          >
            {{ nodeLabel(state) }}
          </el-tag>
          <el-tag v-if="focusedActivityCanvas.outputStates.length > 3" size="small" type="success" effect="plain">
            +{{ focusedActivityCanvas.outputStates.length - 3 }}
          </el-tag>
          <el-tag
            v-if="focusedActivityCanvas.metrics.declaredOutputCount"
            size="small"
            :type="focusedActivityCanvas.metrics.missingOutputCount ? 'warning' : 'success'"
          >
            实现 {{ focusedActivityCanvas.metrics.implementedOutputCount }}/{{ focusedActivityCanvas.metrics.declaredOutputCount }}
          </el-tag>
        </div>
        <div class="focus-context-actions">
          <el-button
            v-if="focusedActivityCanvas.parentId"
            size="small"
            @click="enterActivityFocusById(focusedActivityCanvas.parentId)"
          >
            上层
          </el-button>
          <el-button size="small" @click="clearGraphFocus">退出</el-button>
        </div>
      </div>

      <div class="summary-strip">
        <div class="metric">
          <span>状态</span>
          <strong>{{ graphSummary.state_node_count || 0 }}</strong>
        </div>
        <div class="metric">
          <span>活动</span>
          <strong>{{ graphSummary.activity_node_count || 0 }}</strong>
        </div>
        <div class="metric">
          <span>虚拟活动</span>
          <strong>{{ graphSummary.virtual_activity_count || 0 }}</strong>
        </div>
        <div class="metric">
          <span>可执行活动</span>
          <strong>{{ graphSummary.executable_activity_count || 0 }}</strong>
        </div>
        <div class="metric">
          <span>绑定</span>
          <strong>{{ graphSummary.binding_count || 0 }}</strong>
        </div>
        <div class="metric">
          <span>状态深度</span>
          <strong>{{ graphSummary.max_state_depth || 0 }}</strong>
        </div>
        <div class="metric">
          <span>活动深度</span>
          <strong>{{ graphSummary.max_activity_depth || 0 }}</strong>
        </div>
        <div class="metric">
          <span>依赖链</span>
          <strong>{{ graphSummary.longest_dependency_chain_depth || 0 }}</strong>
        </div>
        <div class="metric warning">
          <span>覆盖缺口</span>
          <strong>{{ graphSummary.coverage_gap_count || 0 }}</strong>
        </div>
        <div class="metric warning">
          <span>部分实现</span>
          <strong>{{ graphSummary.partial_virtual_activity_count || 0 }}</strong>
        </div>
        <div class="metric warning">
          <span>跨层级</span>
          <strong>{{ graphSummary.cross_level_binding_count || 0 }}</strong>
        </div>
        <div class="metric warning">
          <span>孤立节点</span>
          <strong>{{ (graphSummary.orphan_state_count || 0) + (graphSummary.orphan_activity_count || 0) }}</strong>
        </div>
        <div class="metric danger">
          <span>阻塞</span>
          <strong>{{ validationSummary.blocking_count || 0 }}</strong>
        </div>
      </div>

      <div class="solver-readiness-strip" :class="solverReadinessClass">
        <div>
          <strong>{{ solverReadinessTitle }}</strong>
          <span>{{ solverReadinessDetail }}</span>
        </div>
        <el-button size="small" :type="solverReadinessButtonType" @click="runValidation">校验</el-button>
      </div>

      <div class="workspace-body" data-testid="network-editor-workspace-body">
        <div class="editor-grid">
          <section class="resource-pane" data-testid="network-editor-resource-pane">
          <div class="pane-header">
            <span>资源树</span>
            <el-tag size="small" type="info">{{ stateNodes.length + activityNodes.length + atomicActivities.length }} 项</el-tag>
          </div>
          <el-input v-model="keyword" data-testid="network-editor-resource-search" clearable placeholder="搜索状态或活动" class="search-input" />
          <div class="quick-create">
            <el-button :icon="Plus" size="small" :disabled="!canMutate" data-testid="network-editor-resource-create-state" @click="openCreateState()">新建状态</el-button>
            <el-button :icon="Plus" size="small" :disabled="!canMutate" data-testid="network-editor-resource-create-activity" @click="openCreateActivityNode()">新建虚拟活动</el-button>
            <el-button :icon="Plus" size="small" :disabled="!canMutate" data-testid="network-editor-resource-create-atomic" @click="openCreateAtomicActivity()">新建原子活动</el-button>
          </div>
          <div v-if="hasDraftChanges" class="draft-change-list">
            <div class="section-title">
              <span>编辑草稿</span>
              <el-tag size="small" type="danger">{{ draftChangeCount }}</el-tag>
            </div>
            <div
              v-for="change in draftChanges"
              :key="change.client_id"
              class="draft-change-row"
            >
              <el-tag size="small" type="warning">{{ draftOperationLabel(change.operation) }}</el-tag>
              <span>{{ change.label || draftEntityLabel(change.entity_type) }}</span>
            </div>
          </div>

          <div class="resource-section">
            <div class="section-title">状态</div>
            <el-tree
              :data="filteredStateTree"
              node-key="id"
              default-expand-all
              highlight-current
              :expand-on-click-node="false"
              @node-click="selectState"
            >
              <template #default="{ data }">
                <div class="tree-row">
                  <span class="tree-row-label">{{ data.name }}</span>
                  <div class="tree-row-actions">
                    <el-tooltip v-if="!data.feature_key" content="在状态包中添加状态" placement="top">
                      <el-button :icon="Plus" size="small" text circle :disabled="!canMutate" @click.stop="openCreateState(data)" />
                    </el-tooltip>
                    <el-tag size="small" :type="data.feature_key ? 'success' : 'info'">
                      {{ data.feature_key ? '原子' : '状态包' }}
                    </el-tag>
                  </div>
                </div>
              </template>
            </el-tree>
          </div>

          <div class="resource-section">
            <div class="section-title">活动</div>
            <el-tree
              :data="filteredActivityTree"
              node-key="id"
              default-expand-all
              highlight-current
              :expand-on-click-node="false"
              @node-click="selectActivityNode"
            >
              <template #default="{ data }">
                <div class="tree-row">
                  <span class="tree-row-label">{{ data.name }}</span>
                  <div class="tree-row-actions">
                    <el-tooltip
                      v-if="data.resource_type !== 'atomic_activity' && data.level <= 2"
                      :content="data.level === 1 ? '新建二级活动' : '新建原子活动'"
                      placement="top"
                    >
                      <el-button :icon="Plus" size="small" text circle :disabled="!canMutate" @click.stop="openCreateActivityChild(data)" />
                    </el-tooltip>
                    <el-tag size="small" :type="data.resource_type === 'atomic_activity' ? 'success' : data.level <= 2 ? 'info' : 'warning'">
                      {{ data.resource_type === 'atomic_activity' ? '原子' : data.level <= 2 ? '虚拟' : '旧执行' }}
                    </el-tag>
                  </div>
                </div>
              </template>
            </el-tree>
          </div>

          <div class="resource-section">
            <div class="section-title">
              <span>未布置节点</span>
              <el-tag size="small" :type="unplacedNodeCount ? 'warning' : 'success'">{{ unplacedNodeCount }}</el-tag>
            </div>
            <div v-if="unplacedNodeCount" class="unplaced-list">
              <button
                v-for="node in unplacedStateNodes"
                :key="node.id"
                class="unplaced-row"
                type="button"
                @click="selectGraphState(node)"
              >
                <span>状态</span>
                <strong>{{ node.code }}</strong>
              </button>
              <button
                v-for="node in unplacedActivityNodes"
                :key="node.id"
                class="unplaced-row"
                type="button"
                @click="selectGraphActivity(node)"
              >
                <span>{{ node.activity_type === 'virtual' ? '虚拟活动' : '可执行活动' }}</span>
                <strong>{{ node.code }}</strong>
              </button>
            </div>
            <el-empty v-else :description="unplacedEmptyDescription" :image-size="44" />
          </div>

          <div class="resource-section">
            <div class="section-title">状态包成员</div>
            <div class="reference-form">
              <el-select v-model="referenceForm.state_node_id" filterable placeholder="引用状态">
                <el-option
                  v-for="item in stateNodes"
                  :key="item.id"
                  :label="nodeLabel(item)"
                  :value="item.id"
                />
              </el-select>
              <el-select v-model="referenceForm.parent_state_node_id" filterable placeholder="加入状态包">
                <el-option
                  v-for="item in stateNodes.filter((node) => !node.feature_key)"
                  :key="item.id"
                  :label="nodeLabel(item)"
                  :value="item.id"
                />
              </el-select>
              <el-button :icon="Plus" :disabled="!canCreateReference" @click="createReference">添加</el-button>
            </div>
            <el-table :data="stateReferences" size="small" border max-height="180">
              <el-table-column prop="state_node_code" label="状态" width="110" />
              <el-table-column prop="parent_state_node_code" label="所在状态包" />
              <el-table-column label="" width="66">
                <template #default="{ row }">
                  <el-button type="danger" link :disabled="!canMutate" @click="removeReference(row)">移除引用</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </section>

          <section class="canvas-pane" v-loading="loading" data-testid="network-editor-canvas-pane">
          <div class="pane-header">
            <span>二部图画布</span>
            <el-tag size="small" :type="canvasStatusType">{{ canvasStatusLabel }}</el-tag>
          </div>
          <div
            v-if="viewMode === 'solver_ready'"
            class="solver-view-note"
            data-testid="network-editor-solver-view-note"
          >
            <strong>求解视图</strong>
            <span>仅显示可执行活动与求解事实投影，虚拟活动作为分组元数据保留在求解预检中。</span>
          </div>
          <div class="canvas-action-bar">
            <span class="drag-hint">{{ dragHintLabel }}</span>
            <div class="canvas-view-controls" data-testid="network-editor-canvas-view-controls">
              <el-button-group>
                <el-button size="small" aria-label="缩小画布" data-testid="network-editor-zoom-out" @click="changeCanvasZoom(-canvasZoomStep)">-</el-button>
                <el-button size="small" aria-label="重置画布缩放" data-testid="network-editor-zoom-reset" @click="resetCanvasZoom">
                  {{ canvasZoomPercent }}
                </el-button>
                <el-button size="small" aria-label="放大画布" data-testid="network-editor-zoom-in" @click="changeCanvasZoom(canvasZoomStep)">+</el-button>
              </el-button-group>
            </div>
            <el-button size="small" :disabled="!canQuickConnect" @click="createSelectedInputEdge">
              {{ inputEdgeLabel }}
            </el-button>
            <el-button size="small" type="success" :disabled="!canQuickConnect" @click="createSelectedOutputEdge">
              {{ outputEdgeLabel }}
            </el-button>
          </div>
          <div
            class="canvas x6-canvas-wrapper"
            data-testid="network-editor-canvas"
            @click.self="closeContextMenu"
          >
            <NetworkEditorX6Canvas
              :state-nodes="x6VisibleStateNodes"
              :activity-nodes="x6VisibleActivityNodes"
              :edges="x6RenderedEdges"
              :selected-state-id="selectedStateId"
              :selected-activity-graph-id="selectedActivityGraphId"
              :is-edit-mode="isEditMode"
              :can-mutate="canMutate"
              :canvas-zoom="canvasZoom"
              :state-root-ids="selectedStateRootIds"
              :state-depth="stateDepth"
              :activity-depth="activityDepth"
              @select-state="handleX6SelectState"
              @select-activity="handleX6SelectActivity"
              @toggle-state-expansion="toggleGraphStateExpansion"
              @toggle-activity-expansion="toggleGraphActivityExpansion"
              @edit-state="openEditGraphState"
              @edit-activity="handleX6EditActivity"
              @create-state-inside="openCreateStateInside"
              @create-activity-inside="openCreateActivityInside"
              @focus-activity="enterActivityFocus"
              @layout-change="handleX6LayoutChange"
              @container-resize="handleX6ContainerResize"
              @blank-dblclick="handleX6BlankDoubleClick"
              @connect-nodes="handleX6ConnectNodes"
            />
          </div>
          <div
            v-if="false"
            class="canvas"
            data-testid="network-editor-legacy-canvas"
            :style="{ minHeight: `${canvasHeight * canvasZoom}px` }"
            @click.self="closeContextMenu"
            @dblclick.self="handleCanvasBlankDoubleClick"
            @wheel="handleCanvasWheel"
          >
            <div class="canvas-surface" :style="canvasSurfaceStyle">
              <div class="canvas-content" :style="canvasContentStyle">
            <svg class="edge-layer" :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`" preserveAspectRatio="none">
              <g
                v-for="edge in renderedEdges"
                :key="edge.id"
              >
                <path
                  :d="edgePath(edge)"
                  :class="[
                    'edge-line',
                    edge.type === 'STATE_TO_ACTIVITY' ? 'input-edge' : 'output-edge',
                    { highlighted: isImpactEdge(edge), aggregate: edge.aggregate },
                  ]"
                >
                  <title>{{ edgeTitle(edge) }}</title>
                </path>
                <path
                  v-if="edge.aggregate"
                  :d="edgePath(edge)"
                  class="edge-hit-target"
                  role="button"
                  tabindex="0"
                  :aria-label="`${edge.aggregateLabel}，点击展开具体连线`"
                  @click.stop="expandAggregateEdge(edge)"
                  @keydown.enter.stop.prevent="expandAggregateEdge(edge)"
                  @keydown.space.stop.prevent="expandAggregateEdge(edge)"
                />
                <text
                  v-if="edgeDisplayLabel(edge)"
                  class="edge-label"
                  :x="edgeLabelPoint(edge).x"
                  :y="edgeLabelPoint(edge).y"
                >
                  {{ edgeDisplayLabel(edge) }}
                </text>
              </g>
            </svg>

            <div class="canvas-column state-column">
              <div
                v-for="container in statePackageContainers"
                :key="container.id"
                class="state-package-container"
                :data-testid="`network-editor-state-package-container-${container.stateNodeId}`"
                :class="{ selected: selectedStateId === container.stateNodeId }"
                :style="{
                  top: `${container.top}px`,
                  height: `${container.height}px`,
                  left: `${container.left}px`,
                  width: `${container.width}px`,
                }"
                @dblclick.self.stop="handleStatePackageContainerDoubleClick(container, $event)"
              >
                <span class="container-title">{{ container.name }}</span>
                <small>{{ container.childCount }} 个状态</small>
                <span
                  v-if="isEditMode"
                  class="container-move-handle"
                  :data-testid="`network-editor-state-package-container-move-${container.stateNodeId}`"
                  title="拖动移动容器及内部状态"
                  @pointerdown.stop.prevent="startContainerMove(container, 'state', $event)"
                />
                <span
                  v-if="isEditMode"
                  class="container-resize-handle"
                  title="拖动调整容器尺寸"
                  @pointerdown.stop.prevent="startContainerResize(container, 'state', $event)"
                />
              </div>
              <button
                v-for="(node, index) in visibleStateNodes"
                :key="node.id"
                class="graph-node state-node"
                :data-testid="`network-editor-state-node-${node.state_node_id}`"
                :class="{
                  selected: selectedStateId === node.state_node_id,
                  'multi-selected': multiSelectedStateSet.has(node.state_node_id),
                  'staged-input': stagedInputStateSet.has(node.state_node_id),
                  'staged-output': stagedOutputStateSet.has(node.state_node_id),
                  dragging: canvasDrag?.graphId === node.id,
                  'drop-target': dragOverTarget === node.id,
                  'coverage-gap': statePackageCoverage(node)?.status && statePackageCoverage(node).status !== 'complete',
                  'impact-highlight': impactHighlights.stateIds.has(node.id),
                }"
                :style="nodeStyle(node, index, 'state')"
                :draggable="false"
                @click="selectGraphState(node, $event)"
                @dragstart="startStateDrag(node, $event)"
                @dragend="endCanvasDrag"
                @dragover.prevent="dragOverState(node, $event)"
                @dragleave="leaveDropTarget(node)"
                @drop.prevent="dropOnState(node, $event)"
                @contextmenu.prevent.stop="openStateContextMenu(node, $event)"
              >
                <span
                  v-if="isEditMode"
                  class="layout-handle"
                  title="拖动调整位置"
                  @pointerdown.stop.prevent="startLayoutDrag(node, index, 'state', $event)"
                />
                <span
                  v-if="isEditMode"
                  class="semantic-port port-left"
                  title="被产出端口：活动输出拖到这里"
                  @dragover.prevent.stop="dragOverState(node, $event)"
                  @dragleave.stop="leaveDropTarget(node)"
                  @drop.prevent.stop="dropOnState(node)"
                >
                  产出
                </span>
                <span
                  v-if="isEditMode"
                  class="semantic-port port-right"
                  draggable="true"
                  title="前置端口：从这里拖到活动输入"
                  @dragstart.stop="startStateDrag(node, $event)"
                  @dragend="endCanvasDrag"
                >
                  输入
                </span>
                <span class="node-code">{{ node.code }}</span>
                <span class="node-name">{{ node.name }}</span>
                <span class="node-meta">
                  {{ node.leaf_count || 1 }} 叶子
                  <span v-if="stateNodeMetrics(node).childCount" class="node-metric-badge">
                    成员 {{ stateNodeMetrics(node).childCount }}
                  </span>
                  <span v-if="stateNodeMetrics(node).maxDescendantDepth" class="node-metric-badge">
                    深度 {{ stateNodeMetrics(node).maxDescendantDepth }}
                  </span>
                  <span v-if="stateNodeMetrics(node).relatedActivityCount" class="node-metric-badge">
                    活动 {{ stateNodeMetrics(node).relatedActivityCount }}
                  </span>
                  <span v-if="node.reference_ids?.length" class="node-reference-badge">
                    引用 {{ node.reference_ids.length }}
                  </span>
                  <span
                    v-if="statePackageCoverage(node)"
                    :class="['node-coverage-badge', `coverage-${statePackageCoverage(node).status}`]"
                  >
                    覆盖 {{ statePackageCoverage(node).coveredCount }}/{{ statePackageCoverage(node).leafCount }}
                  </span>
                  <span v-if="statePackageCoverage(node)?.bindingCount" class="node-binding-badge">
                    {{ statePackageCoverage(node).bindingCount }} 绑定
                  </span>
                </span>
                <span v-if="isGraphStateAggregate(node) || canMutate" class="node-actions" @click.stop>
                  <span
                    v-if="isGraphStateAggregate(node)"
                    class="node-action"
                    role="button"
                    tabindex="0"
                    :title="isGraphStateExpanded(node) ? '折叠该状态包' : '展开该状态包'"
                    @click.stop="toggleGraphStateExpansion(node)"
                    @keydown.enter.stop.prevent="toggleGraphStateExpansion(node)"
                    @keydown.space.stop.prevent="toggleGraphStateExpansion(node)"
                  >
                    {{ isGraphStateExpanded(node) ? '折叠' : '展开' }}
                  </span>
                  <span
                    v-if="canMutate"
                    class="node-action"
                    role="button"
                    tabindex="0"
                    title="编辑状态"
                    @click.stop="openEditGraphState(node)"
                    @keydown.enter.stop.prevent="openEditGraphState(node)"
                    @keydown.space.stop.prevent="openEditGraphState(node)"
                  >
                    编辑
                  </span>
                  <span
                    v-if="isGraphStateAggregate(node) && canMutate"
                    class="node-action"
                    role="button"
                    tabindex="0"
                    title="在该状态包中添加状态"
                    @click.stop="openCreateStateInside(node)"
                    @keydown.enter.stop.prevent="openCreateStateInside(node)"
                    @keydown.space.stop.prevent="openCreateStateInside(node)"
                  >
                    添加状态
                  </span>
                </span>
              </button>
            </div>

            <div class="canvas-column activity-column">
              <div
                v-for="container in virtualActivityContainers"
                :key="container.id"
                class="virtual-container"
                :data-testid="`network-editor-virtual-activity-container-${container.id}`"
                :class="{ selected: selectedActivityGraphId === container.id }"
                :style="{
                  top: `${container.top}px`,
                  height: `${container.height}px`,
                  left: `${container.left}px`,
                  width: `${container.width}px`,
                }"
              >
                <div class="container-title">{{ container.name }}</div>
                <div class="container-meta">
                  <small>{{ container.childCount }} 项</small>
                  <small v-if="container.contextCount">上下文 {{ container.contextCount }}</small>
                  <small
                    v-if="container.declaredOutputCount"
                    :class="{ warning: container.missingOutputCount, success: !container.missingOutputCount }"
                  >
                    输出 {{ container.implementedOutputCount }}/{{ container.declaredOutputCount }}
                  </small>
                </div>
                <span
                  v-if="isEditMode"
                  class="container-move-handle"
                  :data-testid="`network-editor-virtual-activity-container-move-${container.id}`"
                  title="拖动移动容器及内部活动"
                  @pointerdown.stop.prevent="startContainerMove(container, 'activity', $event)"
                />
                <span
                  v-if="isEditMode"
                  class="container-resize-handle"
                  title="拖动调整容器尺寸"
                  @pointerdown.stop.prevent="startContainerResize(container, 'activity', $event)"
                />
              </div>
              <button
                v-for="(node, index) in visibleActivityNodes"
                :key="node.id"
                class="graph-node activity-node"
                :data-testid="`network-editor-activity-node-${node.id}`"
                :class="{
                  selected: selectedActivityGraphId === node.id,
                  executable: node.activity_type === 'executable',
                  'focus-root': focusedActivityCanvas?.node.id === node.activity_node_id,
                  dragging: canvasDrag?.graphId === node.id,
                  'drop-target': dragOverTarget === node.id,
                  'impact-highlight': impactHighlights.activityIds.has(node.id),
                }"
                :style="nodeStyle(node, index, 'activity')"
                :draggable="false"
                @click="selectGraphActivity(node)"
                @dragstart="startActivityDrag(node, $event)"
                @dragend="endCanvasDrag"
                @dragover.prevent="dragOverActivity(node, $event)"
                @dragleave="leaveDropTarget(node)"
                @drop.prevent="dropOnActivity(node, $event)"
                @dblclick.prevent="enterActivityFocus(node)"
                @contextmenu.prevent.stop="openActivityContextMenu(node, $event)"
              >
                <span
                  v-if="isEditMode"
                  class="layout-handle"
                  title="拖动调整位置"
                  @pointerdown.stop.prevent="startLayoutDrag(node, index, 'activity', $event)"
                />
                <span
                  v-if="isEditMode"
                  class="semantic-port port-left"
                  :title="node.activity_type === 'virtual' ? '上下文输入端口：状态拖到这里' : '输入端口：状态拖到这里'"
                  @dragover.prevent.stop="dragOverActivity(node, $event)"
                  @dragleave.stop="leaveDropTarget(node)"
                  @drop.prevent.stop="dropOnActivity(node)"
                >
                  输入
                </span>
                <span
                  v-if="isEditMode"
                  class="semantic-port port-right"
                  draggable="true"
                  :title="node.activity_type === 'virtual' ? '声明输出端口：从这里拖到状态' : '输出端口：从这里拖到状态'"
                  @dragstart.stop="startActivityDrag(node, $event)"
                  @dragend="endCanvasDrag"
                >
                  产出
                </span>
                <span class="node-code">{{ node.code }}</span>
                <span class="node-name">{{ node.name }}</span>
                <span class="node-meta">
                  <span class="node-kind-badge">{{ node.activity_type === 'virtual' ? '虚拟' : '可执行' }}</span>
                  <span
                    v-if="node.activity_type === 'virtual' && activityNodeMetrics(node).childCount"
                    class="node-metric-badge"
                  >
                    子活动 {{ activityNodeMetrics(node).childCount }}
                  </span>
                  <span
                    v-if="node.activity_type === 'virtual' && activityNodeMetrics(node).maxDescendantDepth"
                    class="node-metric-badge"
                  >
                    深度 {{ activityNodeMetrics(node).maxDescendantDepth }}
                  </span>
                  <span
                    v-if="node.activity_type === 'virtual' && activityNodeMetrics(node).declaredOutputCount"
                    :class="['node-metric-badge', activityNodeMetrics(node).missingOutputCount ? 'warning' : 'complete']"
                  >
                    实现 {{ activityNodeMetrics(node).implementedOutputCount }}/{{ activityNodeMetrics(node).declaredOutputCount }}
                  </span>
                  <span v-if="activityNodeMetrics(node).inputCount" class="node-metric-badge">
                    输入 {{ activityNodeMetrics(node).inputCount }}
                  </span>
                  <span v-if="activityNodeMetrics(node).inheritedInputCount" class="node-metric-badge inherited">
                    上下文 {{ activityNodeMetrics(node).inheritedInputCount }}
                  </span>
                  <span v-if="activityNodeMetrics(node).outputCount" class="node-metric-badge">
                    输出 {{ activityNodeMetrics(node).outputCount }}
                  </span>
                  <span v-if="activityNodeMetrics(node).crossLevelCount" class="node-metric-badge warning">
                    跨层级 {{ activityNodeMetrics(node).crossLevelCount }}
                  </span>
                </span>
                <span v-if="node.activity_type === 'virtual'" class="node-actions" @click.stop>
                  <span
                    class="node-action"
                    role="button"
                    tabindex="0"
                    :title="isGraphActivityExpanded(node) ? '折叠该虚拟活动' : '展开该虚拟活动'"
                    @click.stop="toggleGraphActivityExpansion(node)"
                    @keydown.enter.stop.prevent="toggleGraphActivityExpansion(node)"
                    @keydown.space.stop.prevent="toggleGraphActivityExpansion(node)"
                  >
                    {{ isGraphActivityExpanded(node) ? '折叠' : '展开' }}
                  </span>
                  <span
                    class="node-action"
                    role="button"
                    tabindex="0"
                    title="进入专注画布"
                    @click.stop="enterActivityFocus(node)"
                    @keydown.enter.stop.prevent="enterActivityFocus(node)"
                    @keydown.space.stop.prevent="enterActivityFocus(node)"
                  >
                    专注
                  </span>
                  <span
                    v-if="canMutate && node.level === 1"
                    class="node-action"
                    role="button"
                    tabindex="0"
                    title="添加内部虚拟活动"
                    @click.stop="openCreateActivityInside(node)"
                    @keydown.enter.stop.prevent="openCreateActivityInside(node)"
                    @keydown.space.stop.prevent="openCreateActivityInside(node)"
                  >
                    子活动
                  </span>
                  <span
                    v-if="canMutate && node.level === 2"
                    class="node-action"
                    role="button"
                    tabindex="0"
                    title="添加内部原子活动"
                    @click.stop="openCreateActivityInside(node)"
                    @keydown.enter.stop.prevent="openCreateActivityInside(node)"
                    @keydown.space.stop.prevent="openCreateActivityInside(node)"
                  >
                    原子
                  </span>
                </span>
              </button>
            </div>

            <div
              v-if="contextMenu"
              class="node-context-menu"
              data-testid="network-editor-node-context-menu"
              :style="contextMenuStyle"
              @click.stop
            >
              <div class="context-menu-title">{{ contextMenuTitle }}</div>
              <button v-if="contextMenu.kind === 'state'" type="button" @click="focusContextState">
                设为状态焦点
              </button>
              <button
                v-if="contextMenu.kind === 'state'"
                type="button"
                :disabled="!canMutate"
                @click="editContextState"
              >
                编辑状态
              </button>
              <button
                v-if="contextMenu.kind === 'state' && isGraphStateAggregate(contextMenu.node)"
                type="button"
                :disabled="!canMutate"
                @click="createContextChildState"
              >
                添加状态
              </button>
              <button v-if="contextMenu.kind === 'activity'" type="button" @click="focusContextActivity">
                设为活动焦点
              </button>
              <button
                v-if="contextMenu.kind === 'activity' && contextMenu.node.activity_type === 'virtual'"
                type="button"
                @click="focusContextVirtualActivity"
              >
                进入专注画布
              </button>
              <button
                v-if="contextMenu.kind === 'activity'"
                type="button"
                :disabled="!canMutate"
                @click="editContextActivity"
              >
                编辑活动
              </button>
              <button
                v-if="contextMenu.kind === 'activity' && contextMenu.node.activity_type === 'virtual' && contextMenu.node.level <= 2"
                type="button"
                :disabled="!canMutate"
                @click="createContextActivityInside"
              >
                {{ contextMenu.node.level === 1 ? '添加子活动' : '添加原子活动' }}
              </button>
            </div>

            <div
              v-if="stateMultiSelectToolbarVisible"
              class="multi-select-toolbar"
              data-testid="network-editor-state-multi-select-toolbar"
              :style="stateMultiSelectToolbarStyle"
              @click.stop
            >
              <strong>已选 {{ multiSelectedStateIds.length }} · 前置 {{ stagedInputStateIds.length }} · 产出 {{ stagedOutputStateIds.length }}</strong>
              <button type="button" :disabled="!multiSelectedStateIds.length" @click="stageSelectedStatesAsInput">
                设为前置
              </button>
              <button type="button" :disabled="!multiSelectedStateIds.length" @click="stageSelectedStatesAsOutput">
                设为产出
              </button>
              <button type="button" :disabled="!canCreateActivityFromStateSelection" @click="createVirtualActivityFromStateSelection">
                创建虚拟活动
              </button>
              <button type="button" :disabled="!canCreateActivityFromStateSelection" @click="createAtomicActivityFromStateSelection">
                创建原子活动
              </button>
              <button type="button" @click="clearStateMultiSelection(true)">清空</button>
            </div>
              </div>
            </div>
          </div>
        </section>

          <section class="properties-pane" data-testid="network-editor-properties-pane">
          <div class="pane-header">
            <span>属性与绑定</span>
            <el-tag size="small">{{ selectedBinding ? `#${selectedBinding.id}` : '未选绑定' }}</el-tag>
          </div>

          <div class="detail-block">
            <div class="section-title">当前选择</div>
            <el-descriptions :column="1" size="small" border>
              <el-descriptions-item label="状态">{{ selectedStateLabel }}</el-descriptions-item>
              <el-descriptions-item v-if="selectedStateGraphNode" label="所在状态包">
                {{ selectedStatePrimaryParentLabel }}
              </el-descriptions-item>
              <el-descriptions-item v-if="selectedStateReferenceParentLabels.length" label="其他出现位置">
                <div class="reference-parent-list">
                  <el-tag
                    v-for="item in selectedStateReferenceParentLabels"
                    :key="item"
                    size="small"
                    type="warning"
                  >
                    {{ item }}
                  </el-tag>
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="活动">{{ selectedActivityLabel }}</el-descriptions-item>
            </el-descriptions>
            <div class="selected-actions">
              <el-button size="small" :disabled="!canMutate || !selectedEditableLabel" data-testid="network-editor-edit-selected" @click="editSelected">编辑选中</el-button>
              <el-button size="small" type="danger" :disabled="!canMutate || !selectedEditableLabel" data-testid="network-editor-delete-selected" @click="deleteSelected">
                {{ selectedDeleteActionLabel }}
              </el-button>
            </div>
          </div>

          <div class="detail-block" v-loading="impactLoading">
            <div class="section-title">影响分析</div>
            <div class="impact-grid">
              <div>
                <span>{{ impactMetricLabels.upstream }}</span>
                <strong>{{ selectedImpact.upstream.length }}</strong>
              </div>
              <div>
                <span>{{ impactMetricLabels.downstream }}</span>
                <strong>{{ selectedImpact.downstream.length }}</strong>
              </div>
              <div>
                <span>{{ impactMetricLabels.bindings }}</span>
                <strong>{{ selectedImpact.bindings.length }}</strong>
              </div>
            </div>
            <div v-if="impactStateCoverage" class="impact-coverage">
              <div class="impact-grid">
                <div>
                  <span>叶子状态</span>
                  <strong>{{ impactStateCoverage.leaf_state_count || 0 }}</strong>
                </div>
                <div>
                  <span>状态包绑定</span>
                  <strong>{{ impactStateCoverage.package_binding_count || 0 }}</strong>
                </div>
                <div>
                  <span>绑定引用</span>
                  <strong>{{ impactStateCoverage.binding_ids?.length || 0 }}</strong>
                </div>
              </div>
              <div v-if="impactStateCoverage.leaf_states?.length" class="impact-list">
                <el-tag
                  v-for="leaf in impactStateCoverage.leaf_states.slice(0, 8)"
                  :key="leaf.id || leaf.state_node_id"
                  size="small"
                  type="success"
                >
                  {{ impactItemLabel(leaf) }}
                </el-tag>
                <el-tag v-if="impactStateCoverage.leaf_states.length > 8" size="small" type="info">
                  +{{ impactStateCoverage.leaf_states.length - 8 }}
                </el-tag>
              </div>
            </div>
            <div v-if="impactResult && impactResult.participates_in_solver !== null" class="impact-list">
              <el-tag size="small" :type="impactResult?.participates_in_solver ? 'success' : 'info'">
                {{ impactResult?.participates_in_solver ? '参与求解活动' : '仅展示活动' }}
              </el-tag>
            </div>
            <div v-for="section in impactSections" :key="section.label" class="impact-section">
              <span>{{ section.label }}</span>
              <div class="impact-list">
                <el-tag
                  v-for="item in section.items.slice(0, 8)"
                  :key="item.id || item.code || item.message"
                  size="small"
                  :type="section.type"
                >
                  {{ impactItemLabel(item) }}
                </el-tag>
                <el-tag v-if="section.items.length > 8" size="small" type="info">
                  +{{ section.items.length - 8 }}
                </el-tag>
              </div>
            </div>
            <div v-if="selectedImpact.bindings.length" class="impact-list">
              <el-tag
                v-for="item in selectedImpact.bindings.slice(0, 6)"
                :key="item.id"
                size="small"
                :type="coverageTagType(item.coverage_status)"
              >
                {{ bindingRoleText(item.binding_role) }} / {{ coverageStatusLabel(item.coverage_status) }}
              </el-tag>
            </div>
          </div>

          <div class="detail-block">
            <div class="section-title">创建绑定</div>
            <el-form label-width="78px" @submit.prevent>
              <el-form-item label="角色">
                <el-select v-model="bindingForm.binding_role" style="width: 100%">
                  <el-option
                    v-for="item in roleOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="bindingForm.state_node_id" filterable style="width: 100%">
                  <el-option
                    v-for="item in stateSelectOptions"
                    :key="item.id"
                    :label="nodeLabel(item)"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="活动">
                <el-select v-model="bindingForm.activity_graph_id" filterable style="width: 100%" @change="onBindingActivityChange">
                  <el-option
                    v-for="item in activitySelectOptions"
                    :key="item.id"
                    :label="`${item.code} ${item.name}`"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-if="selectedBindingActivity?.atomic_activity_id" label="规则">
                <el-select v-model="bindingForm.op_rule_id" filterable clearable style="width: 100%">
                  <el-option
                    v-for="item in opRuleOptions"
                    :key="item.id"
                    :label="`${item.code} ${item.name}`"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item v-if="bindingFormShowsCoverageSelector" label="覆盖">
                <div class="binding-coverage-editor">
                  <el-segmented
                    v-model="bindingForm.coverage_mode"
                    data-testid="network-editor-binding-coverage-segmented"
                    aria-label="绑定覆盖范围"
                    :options="[
                      { label: '全部当前成员', value: 'all' },
                      { label: '选择部分成员', value: 'partial' },
                    ]"
                  />
                  <el-select
                    v-if="bindingForm.coverage_mode === 'partial'"
                    v-model="bindingForm.covered_leaf_state_ids"
                    multiple
                    filterable
                    collapse-tags
                    collapse-tags-tooltip
                    style="width: 100%"
                    placeholder="选择覆盖的叶子状态"
                  >
                    <el-option
                      v-for="item in bindingFormLeafStateOptions"
                      :key="item.id"
                      :label="item.label"
                      :value="item.id"
                    />
                  </el-select>
                  <span class="form-hint">{{ bindingFormCoverageSummary }}</span>
                </div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Plus" :disabled="!canCreateBinding" data-testid="network-editor-create-binding" @click="createBindingFromForm">
                  连接
                </el-button>
                <el-button :disabled="!canUpdateBinding" data-testid="network-editor-update-binding" @click="updateSelectedBindingFromForm">
                  更新选中绑定
                </el-button>
                <el-button :disabled="!canOpenBatchBinding" @click="openBatchBindingDialog">
                  批量绑定
                </el-button>
              </el-form-item>
            </el-form>
          </div>

          <div class="detail-block">
            <div class="section-title">绑定列表</div>
            <el-table :data="bindings" size="small" border max-height="260" highlight-current-row @row-click="selectBinding">
              <el-table-column label="角色" width="112">
                <template #default="{ row }">{{ bindingRoleText(row.binding_role) }}</template>
              </el-table-column>
              <el-table-column label="覆盖" width="82">
                <template #default="{ row }">
                  <el-tag size="small" :type="coverageTagType(row.coverage_status)">
                    {{ coverageStatusLabel(row.coverage_status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="对象" show-overflow-tooltip>
                <template #default="{ row }">{{ bindingLabel(row) }}</template>
              </el-table-column>
            </el-table>
            <div v-if="selectedBinding" class="coverage-panel">
              <div class="section-title">
                <span>覆盖快照</span>
                <el-tag size="small" :type="coverageTagType(selectedCoverage.coverageStatus)">
                  {{ coverageStatusLabel(selectedCoverage.coverageStatus) }}
                </el-tag>
              </div>
              <div class="coverage-summary">
                <div>
                  <span>绑定状态</span>
                  <strong>{{ selectedCoverage.boundStateLabel }}</strong>
                </div>
                <div>
                  <span>已覆盖</span>
                  <strong>{{ selectedCoverage.coveredActiveCount }} / {{ selectedCoverage.currentLeafCount }}</strong>
                </div>
                <div>
                  <span>缺失</span>
                  <strong>{{ selectedCoverage.missingLeaves.length }}</strong>
                </div>
                <div>
                  <span>过期 ID</span>
                  <strong>{{ selectedCoverage.staleLeafIds.length }}</strong>
                </div>
              </div>
              <div v-if="selectedCoverage.missingLeaves.length" class="coverage-list">
                <span>缺失叶子状态</span>
                <el-tag
                  v-for="leaf in selectedCoverage.missingLeaves"
                  :key="leaf.id"
                  size="small"
                  type="warning"
                >
                  {{ nodeLabel(leaf) }}
                </el-tag>
              </div>
              <div v-if="selectedCoverage.staleLeafIds.length" class="coverage-list">
                <span>过期快照 ID</span>
                <el-tag
                  v-for="id in selectedCoverage.staleLeafIds"
                  :key="id"
                  size="small"
                  type="danger"
                >
                  #{{ id }}
                </el-tag>
              </div>
              <div v-if="selectedCoverage.coveredLeaves.length" class="coverage-list compact">
                <span>覆盖叶子</span>
                <el-tag
                  v-for="leaf in selectedCoverage.coveredLeaves.slice(0, 8)"
                  :key="leaf.id"
                  size="small"
                  type="success"
                >
                  {{ nodeLabel(leaf) }}
                </el-tag>
                <el-tag v-if="selectedCoverage.coveredLeaves.length > 8" size="small" type="info">
                  +{{ selectedCoverage.coveredLeaves.length - 8 }}
                </el-tag>
              </div>
            </div>
            <div class="binding-actions">
              <el-button :disabled="!canMutate || !selectedBinding" data-testid="network-editor-refresh-selected-coverage" @click="refreshSelectedCoverage">刷新覆盖</el-button>
              <el-button type="danger" :disabled="!canMutate || !selectedBinding" data-testid="network-editor-remove-binding" @click="removeBinding">删除绑定</el-button>
            </div>
          </div>
          </section>
        </div>

        <section class="validation-pane" data-testid="network-editor-validation-pane">
        <div class="issue-column">
          <div class="pane-header">
            <span>建模校验</span>
            <el-tag size="small">{{ validationResult?.modeling_issues?.length || 0 }}</el-tag>
          </div>
          <el-table
            :data="validationResult?.modeling_issues || []"
            data-testid="network-editor-model-issues-table"
            size="small"
            border
            max-height="220"
            @row-click="inspectIssue"
          >
            <el-table-column label="级别" width="76">
              <template #default="{ row }">
                <el-tag size="small" :type="issueSeverityTagType(row.severity)">
                  {{ issueSeverityLabel(row.severity) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="问题" width="190" show-overflow-tooltip>
              <template #default="{ row }">{{ issueCodeLabel(row.code) }}</template>
            </el-table-column>
            <el-table-column label="说明" show-overflow-tooltip>
              <template #default="{ row }">{{ issueMessageText(row) }}</template>
            </el-table-column>
            <el-table-column label="建议" show-overflow-tooltip>
              <template #default="{ row }">{{ issueSuggestedActionText(row) }}</template>
            </el-table-column>
            <el-table-column label="" width="176">
              <template #default="{ row }">
                <div class="issue-actions">
                  <el-button type="primary" link data-testid="network-editor-model-issue-locate" :data-issue-code="row.code" @click.stop="inspectIssue(row)">定位</el-button>
                  <el-button
                    v-if="canOpenRuleMaintenance(row)"
                    type="warning"
                    link
                    data-testid="network-editor-model-issue-open-rules"
                    :data-issue-code="row.code"
                    @click.stop="openRuleMaintenance(row)"
                  >
                    规则
                  </el-button>
                  <el-button
                    v-if="canRefreshIssueCoverage(row)"
                    type="success"
                    link
                    data-testid="network-editor-model-issue-refresh-coverage"
                    :data-issue-code="row.code"
                    @click.stop="refreshIssueCoverage(row)"
                  >
                    刷新
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="issue-column">
          <div class="pane-header">
            <span>求解器准备</span>
            <el-tag size="small" :type="(validationResult?.summary?.blocking_count || 0) ? 'danger' : 'success'">
              {{ networkEditorStatusLabel(validationResult?.status || 'pending') }}
            </el-tag>
          </div>
          <el-table
            :data="validationResult?.solver_ready_issues || []"
            data-testid="network-editor-solver-issues-table"
            size="small"
            border
            max-height="220"
            @row-click="inspectIssue"
          >
            <el-table-column label="级别" width="76">
              <template #default="{ row }">
                <el-tag size="small" :type="issueSeverityTagType(row.severity)">
                  {{ issueSeverityLabel(row.severity) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="问题" width="190" show-overflow-tooltip>
              <template #default="{ row }">{{ issueCodeLabel(row.code) }}</template>
            </el-table-column>
            <el-table-column label="说明" show-overflow-tooltip>
              <template #default="{ row }">{{ issueMessageText(row) }}</template>
            </el-table-column>
            <el-table-column label="建议" show-overflow-tooltip>
              <template #default="{ row }">{{ issueSuggestedActionText(row) }}</template>
            </el-table-column>
            <el-table-column label="" width="176">
              <template #default="{ row }">
                <div class="issue-actions">
                  <el-button type="primary" link data-testid="network-editor-solver-issue-locate" :data-issue-code="row.code" @click.stop="inspectIssue(row)">定位</el-button>
                  <el-button
                    v-if="canOpenRuleMaintenance(row)"
                    type="warning"
                    link
                    data-testid="network-editor-solver-issue-open-rules"
                    :data-issue-code="row.code"
                    @click.stop="openRuleMaintenance(row)"
                  >
                    规则
                  </el-button>
                  <el-button
                    v-if="canRefreshIssueCoverage(row)"
                    type="success"
                    link
                    data-testid="network-editor-solver-issue-refresh-coverage"
                    :data-issue-code="row.code"
                    @click.stop="refreshIssueCoverage(row)"
                  >
                    刷新
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="solver-precheck-column">
          <div class="pane-header">
            <span>求解预检</span>
            <el-tag size="small" :type="solverPrecheck?.status === 'ready' ? 'success' : 'warning'">
              {{ networkEditorStatusLabel(solverPrecheck?.status || 'none') }}
            </el-tag>
          </div>
          <el-alert
            v-if="solverPrecheck && !solverPrecheckReady"
            class="solver-precheck-blocked-alert"
            type="warning"
            :closable="false"
            show-icon
            title="阻塞项未清空，求解器暂不可直接读取"
          />
          <div v-if="solverPrecheck" class="solver-precheck-summary-grid">
            <div>
              <span>目标事实</span>
              <strong>{{ solverPrecheck.summary?.goal_fact_count ?? 0 }}</strong>
            </div>
            <div>
              <span>候选活动</span>
              <strong>{{ solverPrecheck.summary?.candidate_activity_count ?? 0 }}</strong>
            </div>
            <div>
              <span>规则</span>
              <strong>{{ solverPrecheck.summary?.effective_rule_count ?? 0 }}</strong>
            </div>
            <div>
              <span>状态组</span>
              <strong>{{ solverPrecheck.summary?.state_aggregation_rule_count ?? 0 }}</strong>
            </div>
            <div>
              <span>虚拟活动组</span>
              <strong>{{ solverPrecheck.summary?.virtual_activity_group_count ?? 0 }}</strong>
            </div>
            <div>
              <span>阻塞项</span>
              <strong>{{ solverPrecheck.summary?.blocking_issue_count ?? 0 }}</strong>
            </div>
          </div>
          <div v-if="solverPrecheck?.solve_request_template" class="solve-template-summary">
            <div class="section-title">
              <span>/solve/layered</span>
              <span class="template-tags">
                <el-tag
                  size="small"
                  :type="solveTemplateStatusTagType(solverPrecheck.solve_request_template)"
                >
                  {{ solveTemplateStatusLabel(solverPrecheck.solve_request_template) }}
                </el-tag>
                <el-tag size="small" type="info">
                  {{ runtimeFieldLabel(solverPrecheck.solve_request_template.required_runtime_fields) }}
                </el-tag>
              </span>
            </div>
            <div class="template-row">
              <span>目标状态</span>
              <strong>{{ solverPrecheck.solve_request_template.body?.target_state_node_ids?.length || 0 }}</strong>
            </div>
            <div class="template-row">
              <span>活动范围</span>
              <strong>{{ solverPrecheck.solve_request_template.body?.activity_scope_node_ids?.length || 0 }}</strong>
            </div>
            <div class="template-row">
              <span>目标函数</span>
              <strong>{{ solverPrecheck.solve_request_template.body?.objective || '-' }}</strong>
            </div>
          </div>
          <el-table :data="solverPrecheck?.executable_activities || []" size="small" border max-height="220">
            <el-table-column prop="atomic_activity_code" label="可执行活动" width="140" />
            <el-table-column prop="op_rule_code" label="规则" width="120" />
            <el-table-column label="继承/自身/输出" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.inherited_preconditions.length }} / {{ row.own_preconditions.length }} / {{ row.own_effects.length }}
              </template>
            </el-table-column>
          </el-table>
          <div v-if="solverPrecheck?.blocking_issues?.length" class="solver-precheck-blockers">
            <div class="section-title">阻塞项</div>
            <el-table
              :data="solverPrecheck.blocking_issues"
              data-testid="network-editor-solver-precheck-blocking-issues-table"
              size="small"
              border
              max-height="160"
              @row-click="inspectIssue"
            >
              <el-table-column label="问题" width="190" show-overflow-tooltip>
                <template #default="{ row }">{{ issueCodeLabel(row.code) }}</template>
              </el-table-column>
              <el-table-column label="说明" show-overflow-tooltip>
                <template #default="{ row }">{{ issueMessageText(row) }}</template>
              </el-table-column>
              <el-table-column label="建议" show-overflow-tooltip>
                <template #default="{ row }">{{ issueSuggestedActionText(row) }}</template>
              </el-table-column>
              <el-table-column label="" width="176">
                <template #default="{ row }">
                  <div class="issue-actions">
                    <el-button type="primary" link data-testid="network-editor-solver-precheck-blocking-issue-locate" :data-issue-code="row.code" @click.stop="inspectIssue(row)">定位</el-button>
                    <el-button
                      v-if="canOpenRuleMaintenance(row)"
                      type="warning"
                      link
                      data-testid="network-editor-solver-precheck-blocking-issue-open-rules"
                      :data-issue-code="row.code"
                      @click.stop="openRuleMaintenance(row)"
                    >
                      规则
                    </el-button>
                    <el-button
                      v-if="canRefreshIssueCoverage(row)"
                      type="success"
                      link
                      data-testid="network-editor-solver-precheck-blocking-issue-refresh-coverage"
                      :data-issue-code="row.code"
                      @click.stop="refreshIssueCoverage(row)"
                    >
                      刷新
                    </el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
        </section>
      </div>
    </template>

    <el-drawer
      v-model="stateDrawerVisible"
      :title="stateDrawerTitle"
      size="460px"
      destroy-on-close
      data-testid="network-editor-state-drawer"
    >
      <el-form label-width="110px" @submit.prevent>
        <el-form-item label="编码">
          <el-input v-model="stateForm.code" placeholder="留空自动生成" maxlength="64" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="stateForm.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="类型">
          <el-segmented
            v-model="stateForm.state_kind"
            data-testid="network-editor-state-kind-segmented"
            aria-label="状态类型"
            :options="[
              { label: '状态包', value: 'aggregate' },
              { label: '原子状态', value: 'atomic' },
            ]"
            @change="onStateKindChange"
          />
        </el-form-item>
        <el-form-item label="所在状态包">
          <el-select v-model="stateForm.parent_id" clearable filterable style="width: 100%" @change="onStateParentChange">
            <el-option v-for="item in stateParentOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="stateForm.state_kind !== 'aggregate'" label="状态维度" required>
          <el-select
            v-model="stateForm.feature_key"
            data-testid="network-editor-state-feature"
            placeholder="选择状态维度"
            filterable
            clearable
            style="width: 100%"
            @change="onStateFeatureChange"
          >
            <el-option
              v-for="item in stateFeatureOptions"
              :key="item.feature_key"
              :label="stateFeatureLabel(item)"
              :value="item.feature_key"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="stateForm.state_kind !== 'aggregate'" label="目标值" required>
          <el-select
            v-if="stateTargetOptions.length"
            v-model="stateForm.target_value"
            data-testid="network-editor-state-target-value"
            placeholder="选择目标值"
            filterable
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="value in stateTargetOptions"
              :key="value"
              :label="value"
              :value="value"
            />
          </el-select>
          <el-input
            v-else
            v-model="stateForm.target_value"
            data-testid="network-editor-state-target-value"
            placeholder="该维度未配置可选值，可临时填写"
            maxlength="256"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="stateForm.sort_order" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="stateForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-testid="network-editor-state-drawer-cancel" @click="stateDrawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingState" data-testid="network-editor-state-drawer-save" @click="saveQuickState">保存</el-button>
      </template>
    </el-drawer>

    <el-dialog
      v-model="duplicateStateDialogVisible"
      title="发现相似状态"
      width="560px"
      destroy-on-close
      data-testid="network-editor-duplicate-state-dialog"
    >
      <div class="duplicate-state-dialog">
        <p>
          系统发现当前设备类型下已有相同或相似状态。推荐复用已有状态，并把它作为引用实例加入当前状态包。
        </p>
        <el-radio-group v-model="duplicateStateSelectedId" class="duplicate-state-list">
          <el-radio
            v-for="candidate in duplicateStateCandidates"
            :key="candidate.id"
            :label="candidate.id"
            :data-testid="`network-editor-duplicate-state-option-${candidate.id}`"
            border
          >
            <strong>{{ nodeLabel(candidate) }}</strong>
            <span>{{ duplicateCandidateReasonLabel(candidate) }}</span>
          </el-radio>
        </el-radio-group>
      </div>
      <template #footer>
        <el-button data-testid="network-editor-duplicate-state-back" @click="closeDuplicateStateDialog">返回编辑</el-button>
        <el-button :loading="savingState" data-testid="network-editor-duplicate-state-create" @click="createPendingStateDespiteDuplicate">仍然新建</el-button>
        <el-button
          type="primary"
          :disabled="!duplicateStateSelectedId"
          :loading="savingState"
          data-testid="network-editor-duplicate-state-reuse"
          @click="reuseDuplicateState"
        >
          复用选中状态
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="packageChangeDialogVisible"
      title="共享状态包修改确认"
      width="620px"
      destroy-on-close
      data-testid="network-editor-package-change-dialog"
    >
      <div class="package-change-dialog">
        <p>
          状态包 <strong>{{ pendingPackageSourceLabel }}</strong> 已被其他状态包复用。请选择本次成员变更如何影响这些使用方。
        </p>
        <div class="package-reference-list">
          <el-tag
            v-for="parent in packageChangeReferenceParents"
            :key="parent.id"
            type="warning"
          >
            {{ nodeLabel(parent) }}
          </el-tag>
        </div>
        <div class="package-impact-preview">
          <div class="section-title">影响预览</div>
          <div class="package-impact-grid">
            <div>
              <span>本次变更</span>
              <strong>{{ packageChangeImpact.changedStateLabel }}</strong>
            </div>
            <div>
              <span>受影响状态包</span>
              <strong>{{ packageChangeImpact.affectedPackageLabels.length }}</strong>
            </div>
            <div>
              <span>相关绑定</span>
              <strong>{{ packageChangeImpact.bindingCount }}</strong>
            </div>
            <div>
              <span>当前覆盖缺口</span>
              <strong>{{ packageChangeImpact.coverageGapCount }}</strong>
            </div>
          </div>
          <div class="package-impact-list">
            <span>受影响状态包</span>
            <div>
              <el-tag
                v-for="label in packageChangeImpact.affectedPackageLabels"
                :key="label"
                size="small"
                type="warning"
              >
                {{ label }}
              </el-tag>
              <el-empty v-if="!packageChangeImpact.affectedPackageLabels.length" description="暂无" :image-size="36" />
            </div>
          </div>
          <div v-if="packageChangeImpact.unchangedPackageLabels.length" class="package-impact-list">
            <span>保持不变</span>
            <div>
              <el-tag
                v-for="label in packageChangeImpact.unchangedPackageLabels"
                :key="label"
                size="small"
                type="info"
              >
                {{ label }}
              </el-tag>
            </div>
          </div>
          <div v-if="packageChangeImpact.bindingLabels.length" class="package-impact-list">
            <span>需复核绑定</span>
            <div>
              <el-tag
                v-for="label in packageChangeImpact.bindingLabels"
                :key="label"
                size="small"
              >
                {{ label }}
              </el-tag>
            </div>
          </div>
          <div v-if="packageChangeImpact.coverageGapLabels.length" class="package-impact-list">
            <span>已有覆盖缺口</span>
            <div>
              <el-tag
                v-for="label in packageChangeImpact.coverageGapLabels"
                :key="label"
                size="small"
                type="danger"
              >
                {{ label }}
              </el-tag>
            </div>
          </div>
          <el-alert
            v-if="packageChangeImpact.notice"
            :title="packageChangeImpact.notice"
            type="warning"
            :closable="false"
            show-icon
          />
        </div>
        <el-radio-group v-model="packageChangeDecision" class="package-change-options">
          <el-radio label="sync" data-testid="network-editor-package-change-sync" border>
            <strong>同步到共享状态包</strong>
            <span>所有使用该状态包的高级状态包都会看到本次成员变化。</span>
          </el-radio>
          <el-radio label="fork" data-testid="network-editor-package-change-fork" border>
            <strong>分叉当前状态包</strong>
            <span>创建新分支给当前使用方，其他使用方继续保持原状态包不变。</span>
          </el-radio>
        </el-radio-group>
        <div v-if="packageChangeDecision === 'fork'" class="package-fork-form">
          <el-form label-width="96px" @submit.prevent>
            <el-form-item label="当前使用方">
              <el-select v-model="packageForkParentId" filterable style="width: 100%">
                <el-option
                  v-for="parent in packageChangeReferenceParents"
                  :key="parent.id"
                  :label="nodeLabel(parent)"
                  :value="parent.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="分支名称">
              <el-input v-model="packageForkName" maxlength="128" />
            </el-form-item>
            <el-form-item label="分支说明">
              <el-input
                v-model="packageForkReason"
                type="textarea"
                :rows="3"
                maxlength="256"
                show-word-limit
                placeholder="说明为什么当前使用方需要与共享状态包不同"
              />
            </el-form-item>
          </el-form>
        </div>
      </div>
      <template #footer>
        <el-button data-testid="network-editor-package-change-back" @click="closePackageChangeDialog">返回编辑</el-button>
        <el-button type="primary" :loading="savingState" data-testid="network-editor-package-change-confirm" @click="confirmPackageChangeDecision">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="batchBindingDialogVisible"
      title="批量绑定状态"
      width="620px"
      destroy-on-close
      data-testid="network-editor-batch-binding-dialog"
    >
      <el-form label-width="104px" @submit.prevent>
        <el-form-item label="活动">
          <el-input :model-value="selectedActivityLabel" disabled />
        </el-form-item>
        <el-form-item :label="batchInputRoleLabel">
          <el-select
            v-model="batchBindingForm.input_state_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择一个或多个前置状态"
          >
            <el-option v-for="item in stateSelectOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="batchOutputRoleLabel">
          <el-select
            v-model="batchBindingForm.output_state_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            style="width: 100%"
            placeholder="选择一个或多个产出状态"
          >
            <el-option v-for="item in stateSelectOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="batchBindingActivity?.atomic_activity_id" label="规则">
          <el-select
            v-model="batchBindingForm.op_rule_id"
            filterable
            clearable
            style="width: 100%"
            placeholder="选择原子活动规则"
          >
            <el-option
              v-for="item in batchOpRuleOptions"
              :key="item.id"
              :label="`${item.code} ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button data-testid="network-editor-batch-binding-cancel" @click="batchBindingDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!canSubmitBatchBindings" data-testid="network-editor-batch-binding-submit" @click="queueBatchBindings">
          加入草稿
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="activityDrawerVisible"
      :title="activityDrawerTitle"
      size="460px"
      destroy-on-close
      data-testid="network-editor-activity-drawer"
    >
      <el-form label-width="110px" @submit.prevent>
        <el-form-item label="编码">
          <el-input v-model="activityForm.code" placeholder="留空自动生成" maxlength="64" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="activityForm.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="activityForm.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="层级">
          <el-segmented
            v-model="activityForm.level"
            data-testid="network-editor-activity-level-segmented"
            aria-label="活动层级"
            :options="[
              { label: '一级', value: 1 },
              { label: '二级', value: 2 },
            ]"
            @change="onActivityLevelChange"
          />
        </el-form-item>
        <el-form-item v-if="activityForm.level === 2" label="所属一级活动">
          <el-select v-model="activityForm.parent_id" filterable style="width: 100%">
            <el-option v-for="item in activityParentOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="activityForm.activity_category" style="width: 100%">
            <el-option label="普通" value="normal" />
            <el-option label="维修" value="repair" />
            <el-option label="维护" value="maintenance" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="activityForm.sort_order" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="activityForm.is_active" />
        </el-form-item>
        <template v-if="!activityEditId">
          <el-form-item label="上下文输入">
            <el-select
              v-model="activityForm.context_state_ids"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              placeholder="创建后自动绑定为上下文输入"
            >
              <el-option v-for="item in stateSelectOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="声明输出">
            <el-select
              v-model="activityForm.output_state_ids"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              placeholder="创建后自动绑定为声明输出"
            >
              <el-option v-for="item in stateSelectOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button data-testid="network-editor-activity-drawer-cancel" @click="activityDrawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingActivity" data-testid="network-editor-activity-drawer-save" @click="saveQuickActivityNode">保存</el-button>
      </template>
    </el-drawer>

    <el-drawer
      v-model="atomicDrawerVisible"
      :title="atomicDrawerTitle"
      size="460px"
      destroy-on-close
      data-testid="network-editor-atomic-drawer"
    >
      <el-form label-width="110px" @submit.prevent>
        <el-form-item label="编码">
          <el-input v-model="atomicForm.code" placeholder="留空自动生成" maxlength="64" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="atomicForm.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="atomicForm.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="所属活动包">
          <el-select v-model="atomicForm.package_id" clearable filterable style="width: 100%" :disabled="!!atomicEditId">
            <el-option v-for="item in level2ActivityPackages" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="atomicForm.activity_category" style="width: 100%">
            <el-option label="普通" value="normal" />
            <el-option label="维修" value="repair" />
            <el-option label="维护" value="maintenance" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="atomicForm.sort_order" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="atomicForm.is_active" />
        </el-form-item>
        <template v-if="!atomicEditId">
          <el-form-item label="输入状态">
            <el-select
              v-model="atomicForm.input_state_ids"
              data-testid="network-editor-atomic-input-states"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              placeholder="创建后自动绑定为输入"
            >
              <el-option v-for="item in stateSelectOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="产出状态">
            <el-select
              v-model="atomicForm.output_state_ids"
              data-testid="network-editor-atomic-output-states"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              style="width: 100%"
              placeholder="创建后自动绑定为产出，并生成规则效果"
              @change="onAtomicOutputStatesChange"
            >
              <el-option v-for="item in stateSelectOptions" :key="item.id" :label="nodeLabel(item)" :value="item.id" />
            </el-select>
            <div v-if="atomicOutputCoverageRows.length" class="atomic-output-coverage-list">
              <div
                v-for="row in atomicOutputCoverageRows"
                :key="row.stateId"
                class="atomic-output-coverage-row"
              >
                <div class="coverage-row-title">
                  <span>{{ row.label }}</span>
                  <small>{{ row.summary }}</small>
                </div>
                <el-segmented
                  v-model="row.coverage.coverage_mode"
                  data-testid="network-editor-atomic-output-coverage-segmented"
                  aria-label="原子活动产出覆盖范围"
                  :options="[
                    { label: '全部当前成员', value: 'all' },
                    { label: '选择部分成员', value: 'partial' },
                  ]"
                  @change="onAtomicOutputCoverageModeChange(row.stateId)"
                />
                <el-select
                  v-if="row.coverage.coverage_mode === 'partial'"
                  v-model="row.coverage.covered_leaf_state_ids"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  style="width: 100%"
                  placeholder="选择产出的叶子状态"
                >
                  <el-option
                    v-for="leaf in row.leafOptions"
                    :key="leaf.id"
                    :label="leaf.label"
                    :value="leaf.id"
                  />
                </el-select>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="规则时长">
            <el-input-number v-model="atomicForm.duration_min" :min="1" style="width: 100%" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button data-testid="network-editor-atomic-drawer-cancel" @click="atomicDrawerVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="savingAtomic"
          :disabled="!canSaveAtomicActivity"
          data-testid="network-editor-atomic-drawer-save"
          @click="saveQuickAtomicActivity"
        >
          保存
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Close, EditPen, Link, Plus, Refresh, Search } from '@element-plus/icons-vue'
import {
  analyzeNetworkEditorImpact,
  commitNetworkEditorDraft,
  getActivityNodes,
  getActivityPackageAtomicRefs,
  getActivityStateBindings,
  getAtomicActivities,
  getFeatureDefs,
  getMachineTypes,
  getOpRules,
  getStateNodeReferences,
  getStateNodes,
  precheckNetworkEditorSolver,
  previewNetworkEditorGraph,
  validateNetworkEditor,
} from '../../api/masterData'
import { buildHierarchyTree } from '../../utils/hierarchyTree'
import NetworkEditorX6Canvas from './components/NetworkEditorX6Canvas.vue'

const emit = defineEmits(['open-workspace'])

const MACHINE_TYPE_RECENTS_KEY = 'networkEditor.recentMachineTypeIds'
const MACHINE_TYPE_RECENT_LIMIT = 5
const DRAFT_STATE_ID_PREFIX = 'draft-state:'
const DRAFT_ACTIVITY_ID_PREFIX = 'draft-activity:'
const DRAFT_ATOMIC_ACTIVITY_ID_PREFIX = 'draft-atomic-activity:'

const machineTypes = ref([])
const machineTypeId = ref(null)
const recentMachineTypeIds = ref(readRecentMachineTypeIds())
const viewMode = ref('implementation')
const includeInactive = ref(false)
const loading = ref(false)
const keyword = ref('')
const selectedStateRootIds = ref([])
const selectedActivityScopeIds = ref([])
const stateDepth = ref(1)
const activityDepth = ref(2)
const stateNodes = ref([])
const activityNodes = ref([])
const atomicActivities = ref([])
const atomicRefsByPackage = ref(new Map())
const stateFeatureDefs = ref([])
const opRules = ref([])
const stateReferences = ref([])
const bindings = ref([])
const graph = ref(null)
const validationResult = ref(null)
const solverPrecheck = ref(null)
const solverPrecheckReady = computed(() => solverPrecheck.value?.status === 'ready')
const impactResult = ref(null)
const impactLoading = ref(false)
const selectedStateId = ref(null)
const selectedActivityGraphId = ref(null)
const selectedBinding = ref(null)
const selectionFocus = ref('')
const contextMenu = ref(null)
const collapsedStateContainerKeys = ref(new Set())
const collapsedActivityContainerKeys = ref(new Set())
const multiSelectedStateIds = ref([])
const stagedInputStateIds = ref([])
const stagedOutputStateIds = ref([])
const canvasDrag = ref(null)
const dragOverTarget = ref(null)
const layoutDrag = ref(null)
const layoutDraft = ref({})
const containerMove = ref(null)
const containerResize = ref(null)
const containerDraft = ref({})
const editorMode = ref('preview')
const draftChanges = ref([])
const pendingBindingPreview = ref(null)
const draftSubmitting = ref(false)
const draftSequence = ref(0)
const editBaselineRevision = ref(null)
const referenceForm = ref({ state_node_id: null, parent_state_node_id: null })
const bindingForm = ref(defaultBindingForm())
const stateDrawerVisible = ref(false)
const activityDrawerVisible = ref(false)
const atomicDrawerVisible = ref(false)
const duplicateStateDialogVisible = ref(false)
const duplicateStateCandidates = ref([])
const duplicateStateSelectedId = ref(null)
const pendingStatePayload = ref(null)
const pendingStateLayout = ref(null)
const batchBindingDialogVisible = ref(false)
const batchBindingForm = ref({ input_state_ids: [], output_state_ids: [], op_rule_id: null })
const packageChangeDialogVisible = ref(false)
const packageChangeDecision = ref('sync')
const packageForkParentId = ref(null)
const packageForkName = ref('')
const packageForkReason = ref('')
const pendingPackageChange = ref(null)
const savingState = ref(false)
const savingActivity = ref(false)
const savingAtomic = ref(false)
const stateEditId = ref(null)
const activityEditId = ref(null)
const atomicEditId = ref(null)
const stateForm = ref(defaultStateForm())
const activityForm = ref(defaultActivityForm())
const atomicForm = ref(defaultAtomicForm())

const canvasWidth = 820
const canvasZoomMin = 0.6
const canvasZoomMax = 1.6
const canvasZoomStep = 0.1
const canvasZoom = ref(1)
const nodeWidth = 220
const rowHeight = 76
const topPadding = 34
const defaultStateX = 28
const defaultActivityX = 556
const edgeSummaryThreshold = 5
const edgeLaneGap = 7
const impactDebounceMs = 160

let impactDebounceTimer = null
let impactRequestSequence = 0

const ruleMaintenanceIssueCodes = new Set([
  'ACTIVITY_WITHOUT_RULE',
  'ATOMIC_ACTIVITY_WITHOUT_RULE',
  'EXECUTABLE_MISSING_RULE',
  'EXECUTABLE_RULE_AMBIGUOUS',
  'EXECUTABLE_RULE_BINDING_INVALID',
  'EXECUTABLE_RULE_NOT_EXPLICIT',
])

const issueSeverityLabels = {
  error: '错误',
  warning: '警告',
  info: '提示',
}
const issueSeverityTagTypes = {
  error: 'danger',
  warning: 'warning',
  info: 'info',
}
const issueCodeLabels = {
  ACTIVITY_CONTAINER_CYCLE: '活动容器成环',
  ACTIVITY_MISSING_INPUT: '活动缺少输入',
  ACTIVITY_MISSING_OUTPUT: '活动缺少输出',
  ACTIVITY_PACKAGE_WITHOUT_ATOMIC_REF: '活动包没有原子活动',
  ACTIVITY_SOLVER_PARTICIPATION_MISMATCH: '活动求解标记异常',
  ACTIVITY_SCOPE_HAS_NO_LEAF: '活动范围没有原子活动',
  ACTIVITY_WITHOUT_RULE: '活动缺少规则',
  ATOMIC_ACTIVITY_INACTIVE: '原子活动已停用',
  ATOMIC_ACTIVITY_WITHOUT_RULE: '原子活动缺少规则',
  ATOMIC_REF_WITHOUT_ACTIVITY: '原子活动引用失效',
  BINDING_COVERAGE_NOT_COMPLETE: '覆盖未完成',
  BROKEN_CHAIN: '求解链路断裂',
  CONFLICTING_GOAL: '目标状态冲突',
  CROSS_LEVEL_BINDING_MANY: '跨层级绑定较多',
  CROSS_LEVEL_BINDING_NOTICE: '跨层级绑定',
  DUPLICATE_STATE_NAME: '状态重名',
  EXECUTABLE_MISSING_INPUT: '原子活动缺少输入',
  EXECUTABLE_MISSING_OUTPUT: '原子活动缺少输出',
  EXECUTABLE_MISSING_RULE: '原子活动缺少规则',
  EXECUTABLE_RULE_AMBIGUOUS: '规则选择不唯一',
  EXECUTABLE_RULE_BINDING_INVALID: '规则绑定无效',
  EXECUTABLE_RULE_NOT_EXPLICIT: '规则未明确选择',
  GRAPH_DEPENDENCY_CYCLE: '状态-活动依赖成环',
  MULTIPLE_OUTPUT_PROVIDERS: '多个活动产出同一状态',
  MULTI_PARENT_STATE_NOTICE: '状态被多个状态包引用',
  NO_PROVIDER: '缺少状态提供者',
  ORPHAN_ACTIVITY: '孤立活动',
  ORPHAN_STATE: '孤立状态',
  OUTPUT_STATE_UNUSED: '产出状态未被消费',
  LEAF_STATE_WITHOUT_FEATURE: '原子状态缺少特征',
  SELF_DEPENDENCY: '求解自依赖',
  SELECTED_ACTIVITY_INACTIVE: '活动范围已停用',
  SELECTED_STATE_INACTIVE: '目标状态已停用',
  SCOPE_GUARD_WITHOUT_PRECONDITION: '范围约束缺少前置',
  STATE_AGGREGATION_CYCLE: '状态包聚合成环',
  STATE_PACKAGE_COVERAGE_LARGE: '状态包覆盖过宽',
  STATE_REFERENCE_CYCLE: '状态包引用成环',
  TARGET_STATE_HAS_NO_LEAF: '目标状态没有叶子',
  VIRTUAL_ACTIVITY_NOT_DECOMPOSED: '虚拟活动未分解',
  VIRTUAL_OUTPUT_NOT_IMPLEMENTED: '虚拟输出未实现',
}
const issueMessageLabels = {
  ACTIVITY_CONTAINER_CYCLE: '活动容器层级中存在循环引用。',
  ACTIVITY_MISSING_INPUT: '活动已有产出状态，但还没有前置或上下文输入。',
  ACTIVITY_MISSING_OUTPUT: '活动已有输入状态，但还没有产出或声明输出。',
  ACTIVITY_PACKAGE_WITHOUT_ATOMIC_REF: '选中的活动包下没有启用的原子活动引用。',
  ACTIVITY_SOLVER_PARTICIPATION_MISMATCH: '活动类型和求解参与标记不一致。',
  ACTIVITY_SCOPE_HAS_NO_LEAF: '选中的活动范围下没有启用的可执行原子活动。',
  ACTIVITY_WITHOUT_RULE: '活动没有可用的启用规则。',
  ATOMIC_ACTIVITY_INACTIVE: '原子活动已停用，当前默认求解范围会跳过它。',
  ATOMIC_ACTIVITY_WITHOUT_RULE: '原子活动没有可用的启用规则。',
  ATOMIC_REF_WITHOUT_ACTIVITY: '活动包中的原子活动引用没有指向有效原子活动。',
  BINDING_COVERAGE_NOT_COMPLETE: '状态包绑定的覆盖快照不完整或已过期。',
  BROKEN_CHAIN: '求解链路在某个状态上断裂，目标暂时不可达。',
  CONFLICTING_GOAL: '当前目标状态之间存在互相冲突的事实。',
  CROSS_LEVEL_BINDING_MANY: '当前图中存在较多跨层级绑定，阅读和求解复核成本较高。',
  CROSS_LEVEL_BINDING_NOTICE: '状态与活动的层级不同，当前绑定跨层级。',
  DUPLICATE_STATE_NAME: '同一状态包视图下出现了重名状态。',
  EXECUTABLE_MISSING_INPUT: '原子活动缺少输入状态。',
  EXECUTABLE_MISSING_OUTPUT: '原子活动缺少产出状态。',
  EXECUTABLE_MISSING_RULE: '原子活动没有可用的启用规则。',
  EXECUTABLE_RULE_AMBIGUOUS: '同一原子活动的绑定指向了多条不同规则。',
  EXECUTABLE_RULE_BINDING_INVALID: '绑定引用了停用或不属于该原子活动的规则。',
  EXECUTABLE_RULE_NOT_EXPLICIT: '原子活动存在多条启用规则，但绑定没有明确使用哪一条。',
  GRAPH_DEPENDENCY_CYCLE: '状态与活动之间存在循环依赖，求解器无法判断执行顺序。',
  MULTIPLE_OUTPUT_PROVIDERS: '同一状态被多个可执行活动产出。',
  MULTI_PARENT_STATE_NOTICE: '同一状态被多个状态包引用显示。',
  NO_PROVIDER: '目标或前置状态缺少可达的提供者活动。',
  ORPHAN_ACTIVITY: '该活动当前没有连接到任何状态。',
  ORPHAN_STATE: '该状态当前没有连接到任何活动。',
  OUTPUT_STATE_UNUSED: '该产出状态在当前图中没有下游活动消费。',
  LEAF_STATE_WITHOUT_FEATURE: '作为目标展开出来的原子状态缺少 feature_key，不能转换为求解事实。',
  SELF_DEPENDENCY: '求解链路中存在活动依赖自身结果的情况。',
  SELECTED_ACTIVITY_INACTIVE: '选中的活动范围已停用，默认求解预检会跳过它。',
  SELECTED_STATE_INACTIVE: '选中的目标状态已停用，默认求解预检会跳过它。',
  SCOPE_GUARD_WITHOUT_PRECONDITION: '活动范围约束没有配置前置条件。',
  STATE_AGGREGATION_CYCLE: '状态包聚合关系存在循环。',
  STATE_PACKAGE_COVERAGE_LARGE: '该状态包绑定覆盖的叶子状态较多。',
  STATE_REFERENCE_CYCLE: '状态包成员引用关系存在循环。',
  TARGET_STATE_HAS_NO_LEAF: '目标状态下没有启用的原子叶子状态，不能展开为求解目标。',
  VIRTUAL_ACTIVITY_NOT_DECOMPOSED: '虚拟活动下没有可执行原子活动。',
  VIRTUAL_OUTPUT_NOT_IMPLEMENTED: '虚拟活动声明的输出没有被内部原子活动完整实现。',
}
const issueSuggestedActionLabels = {
  ACTIVITY_CONTAINER_CYCLE: '移除或改向其中一个活动归属关系，打断循环。',
  ACTIVITY_MISSING_INPUT: '从状态右端口拖到活动左端口，添加输入或上下文输入。',
  ACTIVITY_MISSING_OUTPUT: '从活动右端口拖到状态左端口，添加产出或声明输出。',
  ACTIVITY_PACKAGE_WITHOUT_ATOMIC_REF: '在该活动包下添加原子活动引用，或调整活动范围。',
  ACTIVITY_SOLVER_PARTICIPATION_MISMATCH: '修正活动类型或求解参与标记；通常虚拟活动仅展示，原子活动参与求解。',
  ACTIVITY_SCOPE_HAS_NO_LEAF: '展开该活动范围，补充下级活动包和原子活动，或改选更具体的范围。',
  ACTIVITY_WITHOUT_RULE: '前往活动能力或规则维护，为该活动创建或启用规则。',
  ATOMIC_ACTIVITY_INACTIVE: '启用该原子活动，或从求解范围中移除它。',
  ATOMIC_ACTIVITY_WITHOUT_RULE: '前往活动能力或规则维护，为该原子活动创建或启用规则。',
  ATOMIC_REF_WITHOUT_ACTIVITY: '删除失效引用，或重新选择有效原子活动。',
  BINDING_COVERAGE_NOT_COMPLETE: '进入编辑模式后定位该绑定，点击“刷新”把覆盖刷新加入草稿，再统一提交。',
  BROKEN_CHAIN: '补齐提供者活动、缩小目标/活动范围，或修正规则事实。',
  CONFLICTING_GOAL: '拆开互斥目标，或调整目标状态事实和值。',
  CROSS_LEVEL_BINDING_MANY: '优先收敛为少量状态包级摘要绑定，关键路径尽量改为同层级绑定。',
  CROSS_LEVEL_BINDING_NOTICE: '确认这是有意的摘要连接；若不是，请改为同层级状态包或原子状态绑定。',
  DUPLICATE_STATE_NAME: '复用已有状态、调整名称，或放到更明确的状态包内。',
  EXECUTABLE_MISSING_INPUT: '为该原子活动添加至少一个输入状态绑定。',
  EXECUTABLE_MISSING_OUTPUT: '为该原子活动添加至少一个产出状态绑定。',
  EXECUTABLE_MISSING_RULE: '前往活动能力或规则维护，为该原子活动创建并启用 op_rule，再回到网络编辑器连接。',
  EXECUTABLE_RULE_AMBIGUOUS: '让该原子活动的输入/输出绑定指向同一条明确规则。',
  EXECUTABLE_RULE_BINDING_INVALID: '把绑定改到该原子活动下的一条启用规则；若没有可用项，请先去活动能力或规则维护补齐。',
  EXECUTABLE_RULE_NOT_EXPLICIT: '在右侧绑定表单中选择一条确切的启用规则，再把修改加入草稿。',
  GRAPH_DEPENDENCY_CYCLE: '删除或改向其中一条前置/产出绑定，打断循环。',
  MULTIPLE_OUTPUT_PROVIDERS: '确认多个活动都能产出该状态，或拆分为更具体的状态。',
  MULTI_PARENT_STATE_NOTICE: '这是引用状态的正常提示；确认复用范围正确即可。',
  NO_PROVIDER: '新增能够产出该状态的原子活动，或调整目标/范围使已有活动可达。',
  ORPHAN_ACTIVITY: '为该活动添加输入和输出状态，或删除未使用活动。',
  ORPHAN_STATE: '把该状态连到一个活动，或确认它只是暂存/候选状态。',
  OUTPUT_STATE_UNUSED: '把该状态作为下游活动输入，或确认它是终点/目标状态。',
  LEAF_STATE_WITHOUT_FEATURE: '在状态抽屉中补齐 feature_key 和目标值，或不要把该状态作为目标叶子。',
  SELF_DEPENDENCY: '拆分状态或调整活动输入/输出，避免活动依赖自身产出。',
  SELECTED_ACTIVITY_INACTIVE: '启用该活动范围，或重新选择一个启用的活动范围。',
  SELECTED_STATE_INACTIVE: '启用该目标状态，或重新选择一个启用的目标状态。',
  SCOPE_GUARD_WITHOUT_PRECONDITION: '补充范围约束的前置条件，或删除无效约束。',
  STATE_AGGREGATION_CYCLE: '移除或改向其中一个状态包成员关系，打断循环。',
  STATE_PACKAGE_COVERAGE_LARGE: '确认覆盖范围是否过宽；必要时改成更小状态包或部分叶子覆盖。',
  STATE_REFERENCE_CYCLE: '移除指回自身后代的状态包成员引用。',
  TARGET_STATE_HAS_NO_LEAF: '为该状态包补充启用的原子状态，或直接选择可求解的原子状态作为目标。',
  VIRTUAL_ACTIVITY_NOT_DECOMPOSED: '在虚拟活动容器内新增下级活动包或原子活动。',
  VIRTUAL_OUTPUT_NOT_IMPLEMENTED: '在虚拟活动内部新增原子活动产出缺失叶子状态，或调整声明输出。',
}
const coverageStatusLabels = {
  complete: '完整',
  partial: '部分覆盖',
  stale: '已过期',
  unknown: '未知',
  none: '无',
}
const networkEditorStatusLabels = {
  ready: '就绪',
  blocked: '阻塞',
  warning: '需复核',
  pending: '待校验',
  none: '未预检',
}
const issueNodeTypeLabels = {
  state_node: '状态',
  activity_node: '虚拟活动',
  atomic_activity: '原子活动',
  scope_guard: '范围约束',
  activity_package_atomic_ref: '原子活动引用',
}

const isEditMode = computed(() => editorMode.value === 'edit')
const canMutate = computed(() => !!machineTypeId.value && isEditMode.value && !draftSubmitting.value)
const editorModeLabel = computed(() => (isEditMode.value ? '编辑模式' : '预览模式'))
const draftChangeCount = computed(() => draftChanges.value.length)
const hasDraftChanges = computed(() => draftChangeCount.value > 0)
const machineTypeById = computed(() => new Map(machineTypes.value.map((item) => [String(item.id), item])))
const stateFeatureDefByKey = computed(() =>
  new Map(stateFeatureDefs.value.map((item) => [item.feature_key, item])),
)
const stateFeatureOptions = computed(() =>
  stateFeatureDefs.value
    .filter((item) => item?.feature_key && !String(item.feature_key).includes('__'))
    .sort((a, b) => String(a.feature_name || a.feature_key).localeCompare(String(b.feature_name || b.feature_key))),
)
const selectedStateFeatureDef = computed(() =>
  stateFeatureDefByKey.value.get(stateForm.value.feature_key) || null,
)
const stateTargetOptions = computed(() =>
  normalizeAllowedValues(selectedStateFeatureDef.value?.allowed_values),
)
const machineTypeOptionGroups = computed(() => {
  const recentItems = recentMachineTypeIds.value
    .map((id) => machineTypeById.value.get(String(id)))
    .filter(Boolean)
  const recentSet = new Set(recentItems.map((item) => String(item.id)))
  const remaining = machineTypes.value.filter((item) => !recentSet.has(String(item.id)))
  const businessItems = remaining.filter((item) => !isLikelyTestMachineType(item))
  const testItems = remaining.filter(isLikelyTestMachineType)

  return [
    { label: '最近使用', items: recentItems },
    { label: '业务设备类型', items: businessItems },
    { label: '测试 / 样例设备类型', items: testItems },
  ].filter((group) => group.items.length)
})
const contextMenuStyle = computed(() => {
  if (!contextMenu.value) return {}
  return {
    left: `${contextMenu.value.x}px`,
    top: `${contextMenu.value.y}px`,
  }
})
const contextMenuTitle = computed(() => {
  const node = contextMenu.value?.node
  if (!node) return ''
  return nodeLabel(node)
})
const multiSelectedStateSet = computed(() => new Set(multiSelectedStateIds.value))
const stagedInputStateSet = computed(() => new Set(stagedInputStateIds.value))
const stagedOutputStateSet = computed(() => new Set(stagedOutputStateIds.value))
const stateMultiSelectToolbarVisible = computed(() =>
  isEditMode.value &&
  (multiSelectedStateIds.value.length > 0 || stagedInputStateIds.value.length > 0 || stagedOutputStateIds.value.length > 0),
)
const stateMultiSelectToolbarStyle = computed(() => {
  const nodes = visibleStateNodes.value.filter((node) => multiSelectedStateSet.value.has(node.state_node_id))
  if (!nodes.length) return { left: '14px', top: '10px' }
  const bounds = nodeBounds(nodes, 'state')
  return {
    left: `${Math.min(Math.max(8, bounds.left), canvasWidth - 430)}px`,
    top: `${Math.max(8, bounds.top - 46)}px`,
  }
})
const canCreateActivityFromStateSelection = computed(() =>
  canMutate.value && (!!stagedInputStateIds.value.length || !!stagedOutputStateIds.value.length),
)
const graphSummary = computed(() => graph.value?.summary || {})
const validationSummary = computed(() => graph.value?.validation_summary || validationResult.value?.summary || {})
const baseVisibleStateNodes = computed(() => graph.value?.state_nodes || [])
const draftStateGraphNodes = computed(() => {
  const nodes = []
  const graphByStateId = new Map(baseVisibleStateNodes.value.map((node) => [node.state_node_id, node]))
  for (const change of draftChanges.value) {
    if (change.entity_type !== 'state_node' || change.operation !== 'create') continue
    const node = draftStateGraphNode(change, graphByStateId)
    if (!node) continue
    nodes.push(node)
    graphByStateId.set(node.state_node_id, node)
  }
  return nodes
})
const visibleStateNodes = computed(() => [
  ...baseVisibleStateNodes.value,
  ...draftStateGraphNodes.value,
])
const baseVisibleActivityNodes = computed(() => graph.value?.activity_nodes || [])
const draftActivityGraphNodes = computed(() => {
  const nodes = []
  const graphByActivityId = new Map(baseVisibleActivityNodes.value.map((node) => [node.activity_node_id, node]))
  for (const change of draftChanges.value) {
    if (change.entity_type !== 'activity_node' || change.operation !== 'create') continue
    const node = draftActivityGraphNode(change, graphByActivityId)
    if (!node) continue
    nodes.push(node)
    graphByActivityId.set(node.activity_node_id, node)
  }
  for (const change of draftChanges.value) {
    if (change.entity_type !== 'atomic_activity' || change.operation !== 'create') continue
    const node = draftAtomicActivityGraphNode(change, graphByActivityId)
    if (!node) continue
    nodes.push(node)
  }
  return nodes
})
const visibleActivityNodes = computed(() => [
  ...baseVisibleActivityNodes.value,
  ...draftActivityGraphNodes.value,
])
const x6VisibleStateNodes = computed(() =>
  visibleStateNodes.value
    .filter(isStateVisibleInX6)
    .map(nodeWithDraftLayout),
)
const x6VisibleActivityNodes = computed(() =>
  visibleActivityNodes.value
    .filter(isActivityVisibleInX6)
    .map(nodeWithDraftLayout),
)
const baseVisibleEdges = computed(() => graph.value?.edges || [])
const draftBindingEdges = computed(() => {
  const edges = draftChanges.value
    .map((change, index) => draftBindingEdge(change, index))
    .filter(Boolean)
  const pendingEdge = pendingBindingPreview.value ? pendingBindingPreviewEdge(pendingBindingPreview.value) : null
  if (pendingEdge && !edges.some((edge) => edge.id === pendingEdge.id)) {
    edges.push(pendingEdge)
  }
  return edges
})
const visibleEdges = computed(() => [
  ...baseVisibleEdges.value,
  ...draftBindingEdges.value,
])
const renderedEdges = computed(() => buildRenderedEdges(visibleEdges.value))
const x6RenderedEdges = computed(() => renderedEdges.value.map((edge) => ({
  ...edge,
  displayLabel: edgeDisplayLabel(edge),
  title: edgeTitle(edge),
})))
const incidentGraphIds = computed(() => {
  const ids = new Set()
  for (const edge of visibleEdges.value) {
    ids.add(edge.source_id)
    ids.add(edge.target_id)
  }
  return ids
})
const rawUnplacedStateNodes = computed(() =>
  visibleStateNodes.value.filter((node) => node.is_active !== false && !incidentGraphIds.value.has(node.id)),
)
const rawUnplacedActivityNodes = computed(() =>
  visibleActivityNodes.value.filter((node) => node.is_active !== false && !incidentGraphIds.value.has(node.id)),
)
const unplacedStateNodes = computed(() =>
  rawUnplacedStateNodes.value.filter((node) => matchesNodeKeyword(node, keyword.value)),
)
const unplacedActivityNodes = computed(() =>
  rawUnplacedActivityNodes.value.filter((node) => matchesNodeKeyword(node, keyword.value)),
)
const unplacedNodeCount = computed(() => unplacedStateNodes.value.length + unplacedActivityNodes.value.length)
const unplacedEmptyDescription = computed(() =>
  keyword.value.trim() ? '当前搜索无未布置节点' : '当前视图无孤立节点',
)
const canvasHeight = computed(() => {
  const positions = [
    ...visibleStateNodes.value.map((node, index) => nodePosition(node, index, 'state')),
    ...visibleActivityNodes.value.map((node, index) => nodePosition(node, index, 'activity')),
  ]
  const maxY = positions.reduce((value, pos) => Math.max(value, pos.y), topPadding)
  const containerBottom = [
    ...statePackageContainers.value.map((container) => container.top + container.height),
    ...virtualActivityContainers.value.map((container) => container.top + container.height),
  ].reduce((value, bottom) => Math.max(value, bottom), 0)
  return Math.max(420, maxY + rowHeight + topPadding, containerBottom + topPadding)
})
const canvasZoomPercent = computed(() => `${Math.round(canvasZoom.value * 100)}%`)
const canvasSurfaceStyle = computed(() => ({
  width: `${Math.ceil(canvasWidth * canvasZoom.value)}px`,
  minHeight: `${Math.ceil(canvasHeight.value * canvasZoom.value)}px`,
}))
const canvasContentStyle = computed(() => ({
  width: `${canvasWidth}px`,
  minHeight: `${canvasHeight.value}px`,
  transform: `scale(${canvasZoom.value})`,
}))
const statePackageContainers = computed(() => {
  const containers = []
  for (const node of visibleStateNodes.value) {
    if (node.is_leaf) continue
    const nodeIndex = visibleStateNodes.value.findIndex((item) => item.id === node.id)
    const childIndices = visibleStateNodes.value
      .map((candidate, index) => ({ candidate, index }))
      .filter(({ candidate }) =>
        candidate.id !== node.id &&
        candidate.state_node_id !== node.state_node_id &&
        statePathContains(candidate, node.state_node_id),
      )
      .map(({ index }) => index)
    if (!childIndices.length) continue
    const indices = [nodeIndex, ...childIndices].filter((index) => index >= 0)
    const visibleMembers = indices.map((index) => visibleStateNodes.value[index]).filter(Boolean)
    const bounds = nodeBounds(visibleMembers, 'state')
    const levelOffset = Math.max(0, (node.level || 1) - 1)
    const baseHeight = Math.max(78, bounds.bottom - bounds.top + 22)
    const baseWidth = Math.max(246, bounds.right - bounds.left + 44 - levelOffset * 12)
    const size = containerDimensions(node, baseWidth, baseHeight)
    containers.push({
      id: node.id,
      graphId: node.id,
      stateNodeId: node.state_node_id,
      referenceId: node.reference_id || null,
      name: node.name,
      childCount: childIndices.length,
      top: Math.max(8, bounds.top - 12),
      height: size.height,
      left: Math.max(0, bounds.left - 22 + levelOffset * 12),
      width: size.width,
    })
  }
  return containers.sort((a, b) => b.height - a.height)
})
const virtualActivityContainers = computed(() => {
  const containers = []
  for (const node of visibleActivityNodes.value) {
    if (node.activity_type !== 'virtual' || !node.activity_node_id) continue
    const nodeIndex = visibleActivityNodes.value.findIndex((item) => item.id === node.id)
    const childIndices = visibleActivityNodes.value
      .map((candidate, index) => ({ candidate, index }))
      .filter(({ candidate }) => candidate.id !== node.id && activityPathContains(candidate, node.activity_node_id))
      .map(({ index }) => index)
    if (!childIndices.length) continue
    const indices = [nodeIndex, ...childIndices].filter((index) => index >= 0)
    const visibleMembers = indices.map((index) => visibleActivityNodes.value[index]).filter(Boolean)
    const bounds = nodeBounds(visibleMembers, 'activity')
    const levelOffset = Math.max(0, (node.level || 1) - 1)
    const metrics = activityNodeMetrics(node)
    const baseHeight = Math.max(78, bounds.bottom - bounds.top + 22)
    const baseWidth = Math.max(246, bounds.right - bounds.left + 44 - levelOffset * 12)
    const size = containerDimensions(node, baseWidth, baseHeight)
    containers.push({
      id: node.id,
      activityNodeId: node.activity_node_id,
      name: node.name,
      childCount: childIndices.length,
      contextCount: metrics.inheritedInputCount,
      declaredOutputCount: metrics.declaredOutputCount,
      implementedOutputCount: metrics.implementedOutputCount,
      missingOutputCount: metrics.missingOutputCount,
      top: Math.max(8, bounds.top - 12),
      height: size.height,
      left: Math.max(0, bounds.left - 22 + levelOffset * 12),
      width: size.width,
    })
  }
  return containers.sort((a, b) => b.height - a.height)
})
const draftStateResourceNodes = computed(() =>
  draftChanges.value
    .filter((change) => change.entity_type === 'state_node' && change.operation === 'create')
    .map(draftStateResourceNode)
    .filter(Boolean),
)
const allStateNodes = computed(() => [
  ...stateNodes.value,
  ...draftStateResourceNodes.value,
])
const stateSelectOptions = computed(() =>
  allStateNodes.value.filter((node) => node.is_active !== false),
)
const draftActivityResourceNodes = computed(() =>
  draftChanges.value
    .filter((change) => change.entity_type === 'activity_node' && change.operation === 'create')
    .map(draftActivityResourceNode)
    .filter(Boolean),
)
const allActivityNodes = computed(() => [
  ...activityNodes.value,
  ...draftActivityResourceNodes.value,
])
const stateTree = computed(() => buildHierarchyTree(allStateNodes.value))
const activityTree = computed(() => buildActivityResourceTree())
const baseStateById = computed(() => new Map(stateNodes.value.map((item) => [item.id, item])))
const stateById = computed(() => new Map(allStateNodes.value.map((item) => [item.id, item])))
const stateChildrenByParent = computed(() => {
  const groups = new Map()
  for (const node of allStateNodes.value) {
    const key = node.parent_id || null
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(node)
  }
  return groups
})
const stateReferenceChildrenByParent = computed(() => {
  const groups = new Map()
  const knownStates = stateById.value
  for (const ref of stateReferences.value) {
    if (ref.is_active === false) continue
    const child = knownStates.get(ref.state_node_id)
    const parent = knownStates.get(ref.parent_state_node_id)
    if (!child || !parent) continue
    const key = ref.parent_state_node_id
    if (!groups.has(key)) groups.set(key, [])
    if (!groups.get(key).some((item) => item.id === child.id)) {
      groups.get(key).push(child)
    }
  }
  return groups
})
const activityChildrenByParent = computed(() => {
  const groups = new Map()
  for (const node of allActivityNodes.value) {
    const key = node.parent_id || null
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(node)
  }
  return groups
})
const activityNodeById = computed(() => new Map(allActivityNodes.value.map((item) => [item.id, item])))
const graphActivityById = computed(() => new Map(visibleActivityNodes.value.map((item) => [item.id, item])))
const baseGraphStateById = computed(() => new Map(baseVisibleStateNodes.value.map((item) => [item.state_node_id, item])))
const graphStateById = computed(() => new Map(visibleStateNodes.value.map((item) => [item.state_node_id, item])))
const bindingById = computed(() => new Map(bindings.value.map((item) => [item.id, item])))
const statePackageCoverageById = computed(() => {
  const coverage = new Map()
  for (const node of visibleStateNodes.value) {
    const packageBindings = bindings.value.filter((binding) =>
      binding.state_node_id === node.state_node_id && binding.binding_type === 'state_package',
    )
    if (!packageBindings.length) continue
    const leafIds = leafStateIdsUnder(node.state_node_id, { activeOnly: true })
    const leafSet = new Set(leafIds)
    const coveredIds = new Set()
    const statusPriority = { complete: 0, partial: 1, stale: 2 }
    let worstStatus = 'complete'
    for (const binding of packageBindings) {
      for (const id of binding.covered_leaf_state_ids || []) {
        const numericId = Number(id)
        if (leafSet.has(numericId)) coveredIds.add(numericId)
      }
      const bindingStatus = binding.coverage_status || 'stale'
      if ((statusPriority[bindingStatus] ?? 2) > statusPriority[worstStatus]) {
        worstStatus = bindingStatus
      }
    }
    coverage.set(node.state_node_id, {
      bindingCount: packageBindings.length,
      coveredCount: coveredIds.size,
      leafCount: leafIds.length,
      status: worstStatus,
    })
  }
  return coverage
})
const stateNodeMetricsById = computed(() => {
  const metrics = new Map()
  const visibleStateIds = new Set(visibleStateNodes.value.map((node) => node.state_node_id))
  for (const node of visibleStateNodes.value) {
    const directChildren = displayStateChildren(node.state_node_id, { activeOnly: false })
      .filter((child) => visibleStateIds.has(child.id))
    const descendantIds = stateDescendantNodeIds(node.state_node_id, { activeOnly: false })
    const descendantLevels = descendantIds
      .map((id) => stateById.value.get(id)?.level)
      .filter((level) => Number.isFinite(Number(level)))
    const relatedActivityIds = new Set()
    const coveredGraphIds = new Set([node.id])
    for (const stateId of descendantIds) {
      if (visibleStateIds.has(stateId)) coveredGraphIds.add(`state_node:${stateId}`)
    }
    for (const edge of visibleEdges.value) {
      if (!coveredGraphIds.has(edge.source_id) && !coveredGraphIds.has(edge.target_id)) continue
      const activityId = String(edge.source_id).startsWith('state_node:') ? edge.target_id : edge.source_id
      if (graphActivityById.value.has(activityId)) relatedActivityIds.add(activityId)
    }
    metrics.set(node.state_node_id, {
      childCount: directChildren.length,
      maxDescendantDepth: Math.max(0, ...descendantLevels.map((level) => Number(level) - Number(node.level || 0))),
      relatedActivityCount: relatedActivityIds.size,
    })
  }
  return metrics
})
const activityNodeMetricsById = computed(() => {
  const metrics = new Map()
  const ensure = (activityId) => {
    if (!metrics.has(activityId)) {
      metrics.set(activityId, {
        inputStateIds: new Set(),
        inheritedStateIds: new Set(),
        outputStateIds: new Set(),
        childCount: 0,
        maxDescendantDepth: 0,
        crossLevel: false,
        crossLevelBindingIds: new Set(),
        declaredOutputLeafIds: new Set(),
        implementedOutputLeafIds: new Set(),
      })
    }
    return metrics.get(activityId)
  }

  for (const edge of visibleEdges.value) {
    const activityId = edge.type === 'STATE_TO_ACTIVITY' ? edge.target_id : edge.source_id
    const stateId = edge.type === 'STATE_TO_ACTIVITY' ? edge.source_id : edge.target_id
    if (!graphActivityById.value.has(activityId) || !String(stateId).startsWith('state_node:')) continue
    const item = ensure(activityId)
    if (edge.type === 'STATE_TO_ACTIVITY') {
      if (edge.binding_role === 'context_input' || edge.is_inherited || edge.source_kind === 'inherited_context_binding') {
        item.inheritedStateIds.add(stateId)
      } else {
        item.inputStateIds.add(stateId)
      }
    } else if (edge.binding_role === 'output' || edge.binding_role === 'declared_output') {
      item.outputStateIds.add(stateId)
    }
  }

  for (const binding of bindings.value) {
    const state = stateById.value.get(binding.state_node_id)
    const activityId = binding.atomic_activity_id
      ? `atomic_activity:${binding.atomic_activity_id}`
      : `activity_node:${binding.activity_node_id}`
    const activity = graphActivityById.value.get(activityId)
    if (state && activity && state.level !== activity.level) {
      const item = ensure(activityId)
      item.crossLevel = true
      item.crossLevelBindingIds.add(binding.id || `${activityId}:${binding.state_node_id}:${binding.binding_role}`)
    }
  }

  for (const node of visibleActivityNodes.value) {
    if (node.activity_type !== 'virtual' || !node.activity_node_id) continue
    const descendants = visibleActivityNodes.value.filter((candidate) =>
      candidate.id !== node.id && activityPathContains(candidate, node.activity_node_id),
    )
    const item = ensure(node.id)
    item.childCount = descendants.length
    item.maxDescendantDepth = Math.max(...descendants.map((candidate) => candidate.level || 0), 0)
    for (const binding of bindings.value) {
      if (binding.activity_node_id === node.activity_node_id && binding.binding_role === 'declared_output') {
        for (const stateId of binding.covered_leaf_state_ids || []) {
          item.declaredOutputLeafIds.add(stateId)
        }
      }
    }
    const descendantActivityIds = new Set(activityDescendantNodeIds(node.activity_node_id))
    const descendantAtomicIds = atomicIdsUnderActivityNode(node.activity_node_id)
    for (const binding of bindings.value) {
      if (binding.binding_role !== 'output') continue
      const isDescendantAtomic = binding.atomic_activity_id && descendantAtomicIds.has(binding.atomic_activity_id)
      const isLegacyDescendant = binding.activity_node_id && descendantActivityIds.has(binding.activity_node_id)
      if (!isDescendantAtomic && !isLegacyDescendant) continue
      for (const stateId of binding.covered_leaf_state_ids || []) {
        item.implementedOutputLeafIds.add(stateId)
      }
    }
  }

  const result = new Map()
  for (const [activityId, item] of metrics.entries()) {
    const implementedDeclaredCount = [...item.declaredOutputLeafIds]
      .filter((stateId) => item.implementedOutputLeafIds.has(stateId)).length
    result.set(activityId, {
      inputCount: item.inputStateIds.size,
      inheritedInputCount: item.inheritedStateIds.size,
      outputCount: item.outputStateIds.size,
      childCount: item.childCount,
      maxDescendantDepth: item.maxDescendantDepth,
      crossLevel: item.crossLevel,
      crossLevelCount: item.crossLevelBindingIds.size,
      declaredOutputCount: item.declaredOutputLeafIds.size,
      implementedOutputCount: implementedDeclaredCount,
      missingOutputCount: Math.max(0, item.declaredOutputLeafIds.size - implementedDeclaredCount),
    })
  }
  return result
})
const selectedBindingActivity = computed(() => graphActivityById.value.get(bindingForm.value.activity_graph_id) || null)
const activitySelectOptions = computed(() => visibleActivityNodes.value)
const activityScopeOptions = computed(() => allActivityNodes.value.filter((node) => node.level <= 2))
const opRuleOptions = computed(() => {
  const atomicId = selectedBindingActivity.value?.atomic_activity_id
  if (!atomicId) return []
  return activeOpRulesForAtomicActivity(atomicId)
})
const roleOptions = computed(() => {
  const activity = selectedBindingActivity.value
  if (activity?.activity_type === 'virtual') {
    return [
      { label: '上下文输入', value: 'context_input' },
      { label: '声明输出', value: 'declared_output' },
    ]
  }
  return [
    { label: '输入', value: 'input' },
    { label: '输出', value: 'output' },
  ]
})
const bindingFormLeafStateIds = computed(() => {
  const stateNodeId = bindingForm.value.state_node_id
  if (!stateNodeId) return []
  return leafStateIdsUnder(stateNodeId, { activeOnly: true })
})
const bindingFormIsStatePackage = computed(() => {
  const stateNodeId = bindingForm.value.state_node_id
  if (!stateNodeId) return false
  return stateHasCoverageChoice(stateNodeId)
})
const bindingFormShowsCoverageSelector = computed(() =>
  bindingFormIsStatePackage.value,
)
const bindingFormLeafStateOptions = computed(() =>
  bindingFormLeafStateIds.value
    .map((id) => {
      const state = stateById.value.get(id)
      return { id, label: state ? nodeLabel(state) : `#${id}` }
    }),
)
const bindingFormCoveredLeafStateIds = computed(() => {
  if (!bindingFormShowsCoverageSelector.value || bindingForm.value.coverage_mode !== 'partial') return null
  const allowed = stateIdSet(bindingFormLeafStateIds.value)
  return normalisedStateIds(bindingForm.value.covered_leaf_state_ids).filter((id) => allowed.has(String(id)))
})
const bindingFormCoverageSelectionValid = computed(() =>
  !bindingFormShowsCoverageSelector.value ||
  bindingForm.value.coverage_mode !== 'partial' ||
  bindingFormCoveredLeafStateIds.value.length > 0,
)
const bindingFormCoverageSummary = computed(() => {
  const total = bindingFormLeafStateIds.value.length
  if (!bindingFormShowsCoverageSelector.value) return ''
  if (bindingForm.value.coverage_mode === 'partial') {
    return `已选择 ${bindingFormCoveredLeafStateIds.value.length} / ${total} 个叶子状态`
  }
  return `将覆盖该状态包当前 ${total} 个启用叶子状态`
})
const canCreateBinding = computed(() =>
  canMutate.value &&
  !!bindingForm.value.state_node_id &&
  !!bindingForm.value.activity_graph_id &&
  bindingRoleAllowedForActivity(selectedBindingActivity.value, bindingForm.value.binding_role) &&
  canResolveOpRuleForActivity(selectedBindingActivity.value, bindingForm.value.op_rule_id) &&
  bindingFormCoverageSelectionValid.value,
)
const canUpdateBinding = computed(() => !!selectedBinding.value && canCreateBinding.value)
const canQuickConnect = computed(() =>
  canMutate.value &&
  !!selectedStateId.value &&
  !!selectedActivityGraphId.value &&
  supportsGraphActivityBinding(selectedGraphActivity.value),
)
const canOpenBatchBinding = computed(() =>
  canMutate.value &&
  !!selectedGraphActivity.value &&
  supportsGraphActivityBinding(selectedGraphActivity.value),
)
const batchBindingActivity = computed(() => selectedGraphActivity.value)
const batchBindingRoles = computed(() => {
  const activity = batchBindingActivity.value
  return activity?.activity_type === 'virtual'
    ? { input: 'context_input', output: 'declared_output' }
    : { input: 'input', output: 'output' }
})
const batchInputRoleLabel = computed(() =>
  batchBindingRoles.value.input === 'context_input' ? '上下文输入' : '输入状态',
)
const batchOutputRoleLabel = computed(() =>
  batchBindingRoles.value.output === 'declared_output' ? '声明输出' : '产出状态',
)
const batchOpRuleOptions = computed(() => {
  const atomicId = batchBindingActivity.value?.atomic_activity_id
  if (!atomicId) return []
  return activeOpRulesForAtomicActivity(atomicId)
})
const canSubmitBatchBindings = computed(() => {
  if (!canOpenBatchBinding.value) return false
  const hasStates = !!batchBindingForm.value.input_state_ids.length || !!batchBindingForm.value.output_state_ids.length
  if (!hasStates) return false
  if (!batchBindingActivity.value?.atomic_activity_id) return true
  return batchOpRuleOptions.value.length === 1 || !!batchBindingForm.value.op_rule_id
})
const atomicOutputCoverageRows = computed(() => {
  const coverages = atomicForm.value.output_coverages || {}
  return normalisedStateIds(atomicForm.value.output_state_ids)
    .filter((stateId) => stateHasCoverageChoice(stateId))
    .map((stateId) => {
      const leafIds = leafStateIdsUnder(stateId, { activeOnly: true })
      const coverage = coverages[String(stateId)] || defaultStateCoverageSelection()
      const leafIdSet = stateIdSet(leafIds)
      const selectedCount = normalisedStateIds(coverage.covered_leaf_state_ids)
        .filter((id) => leafIdSet.has(String(id))).length
      return {
        stateId,
        label: nodeLabel(stateById.value.get(stateId)),
        coverage,
        leafIds,
        leafOptions: leafIds.map((id) => ({
          id,
          label: nodeLabel(stateById.value.get(id)),
        })),
        summary: coverage.coverage_mode === 'partial'
        ? `产出 ${selectedCount} / ${leafIds.length} 个叶子状态`
        : `产出当前 ${leafIds.length} 个启用叶子状态`,
      }
    })
})
const atomicOutputCoverageSelectionValid = computed(() =>
  atomicOutputCoverageRows.value.every((row) =>
    row.coverage.coverage_mode !== 'partial' ||
    normalisedNumericIds(row.coverage.covered_leaf_state_ids)
      .some((id) => row.leafIds.includes(id)),
  ),
)
const canSaveAtomicActivity = computed(() =>
  !savingAtomic.value && (!!atomicEditId.value || atomicOutputCoverageSelectionValid.value),
)
const inputEdgeLabel = computed(() =>
  selectedGraphActivity.value?.activity_type === 'virtual' ? '状态 -> 上下文' : '状态 -> 输入',
)
const outputEdgeLabel = computed(() =>
  selectedGraphActivity.value?.activity_type === 'virtual' ? '活动 -> 声明输出' : '活动 -> 产出',
)
const dragHintLabel = computed(() => {
  if (canvasDrag.value) {
    return canvasDrag.value.type === 'state'
      ? '释放到活动输入端口，创建输入或上下文绑定'
      : '释放到状态输出端口，创建产出或声明输出绑定'
  }
  if (!machineTypeId.value) return '先选择设备类型。'
  if (!isEditMode.value) return '预览模式可查看、定位和展开；点击“进入编辑”后才能连接状态与活动。'
  if (!selectedStateId.value && !selectedActivityGraphId.value) {
    return '先选一个状态，再选一个虚拟/原子活动；也可按 Ctrl/Shift/Cmd 多选状态后创建活动。'
  }
  if (selectedStateId.value && !selectedActivityGraphId.value) {
    return '已选状态：再选一个活动，然后点“状态 -> 输入/上下文”，或从状态右端口拖到活动。'
  }
  if (!selectedStateId.value && selectedActivityGraphId.value) {
    return '已选活动：再选一个状态，然后点快捷连接，或从活动右端口拖到状态。'
  }
  if (!supportsGraphActivityBinding(selectedGraphActivity.value)) {
    return '当前活动不能直接绑定，请选择虚拟活动或原子活动。'
  }
  return `已选状态和活动：点击“${inputEdgeLabel.value}”或“${outputEdgeLabel.value}”加入编辑草稿。`
})
const canCreateReference = computed(() =>
  canMutate.value &&
  !!referenceForm.value.state_node_id &&
  !!referenceForm.value.parent_state_node_id &&
  referenceForm.value.state_node_id !== referenceForm.value.parent_state_node_id,
)
const selectedStateLabel = computed(() => {
  const node = stateById.value.get(selectedStateId.value) || graphStateById.value.get(selectedStateId.value)
  return node ? nodeLabel(node) : '-'
})
const selectedActivityLabel = computed(() => {
  const node = graphActivityById.value.get(selectedActivityGraphId.value)
  return node ? `${node.code} ${node.name}` : '-'
})
const selectedStateGraphNode = computed(() => graphStateById.value.get(selectedStateId.value) || null)
const selectedStatePrimaryParentLabel = computed(() => {
  const parentId = selectedStateGraphNode.value?.parent_id
  if (!parentId) return '未加入状态包'
  return nodeLabel(stateById.value.get(parentId))
})
const selectedStateReferenceParentLabels = computed(() =>
  (selectedStateGraphNode.value?.reference_parent_ids || [])
    .map((id) => nodeLabel(stateById.value.get(id)))
    .filter((label) => label && label !== '-'),
)
const packageChangeReferenceParents = computed(() => {
  const sourceId = pendingPackageChange.value?.sourceStateNodeId
  if (!sourceId) return []
  return stateReferences.value
    .filter((ref) => ref.is_active !== false && ref.state_node_id === sourceId)
    .map((ref) => stateById.value.get(ref.parent_state_node_id))
    .filter(Boolean)
})
const pendingPackageSourceLabel = computed(() =>
  nodeLabel(stateById.value.get(pendingPackageChange.value?.sourceStateNodeId)),
)
const packageChangeImpact = computed(() => {
  const change = pendingPackageChange.value
  const empty = {
    changedStateLabel: '-',
    affectedPackageLabels: [],
    unchangedPackageLabels: [],
    bindingLabels: [],
    coverageGapLabels: [],
    bindingCount: 0,
    coverageGapCount: 0,
    notice: '',
  }
  if (!change?.sourceStateNodeId) return empty

  const sourceId = Number(change.sourceStateNodeId)
  const referenceParents = packageChangeReferenceParents.value
  const selectedParentId = Number(packageForkParentId.value || 0)
  const parentIds = referenceParents.map((parent) => Number(parent.id))
  const uniqueIds = (ids) => Array.from(new Set(ids.filter((id) => Number.isFinite(id) && id > 0)))
  const affectedIds = uniqueIds(packageChangeDecision.value === 'fork'
    ? parentIds.filter((id) => id === selectedParentId)
    : [sourceId, ...parentIds])
  const unchangedIds = uniqueIds(packageChangeDecision.value === 'fork'
    ? parentIds.filter((id) => id !== selectedParentId)
    : [])
  const relatedBindings = bindings.value.filter((binding) =>
    affectedIds.some((stateId) => statePackageContainsState(binding.state_node_id, stateId)),
  )
  const coverageGapBindings = relatedBindings.filter((binding) =>
    ['partial', 'stale'].includes(binding.coverage_status),
  )
  const changedStateLabel = packageChangeStateLabel(change)

  return {
    changedStateLabel,
    affectedPackageLabels: affectedIds
      .map((id) => nodeLabel(stateById.value.get(id)))
      .filter((label) => label && label !== '-'),
    unchangedPackageLabels: unchangedIds
      .map((id) => nodeLabel(stateById.value.get(id)))
      .filter((label) => label && label !== '-'),
    bindingLabels: relatedBindings.slice(0, 6).map(bindingLabel),
    coverageGapLabels: coverageGapBindings.slice(0, 6).map((binding) =>
      `${coverageStatusLabel(binding.coverage_status)}：${bindingLabel(binding)}`,
    ),
    bindingCount: relatedBindings.length,
    coverageGapCount: coverageGapBindings.length,
    notice: packageChangeDecision.value === 'sync'
      ? '同步后所有受影响绑定的覆盖快照都应在提交前复核；完整覆盖也可能因新增成员变为已过期。'
      : '分叉只切换当前使用方；其他使用方继续引用原状态包，保持不变。',
  }
})
const selectedGraphActivity = computed(() => graphActivityById.value.get(selectedActivityGraphId.value) || null)
const focusedActivityCanvas = computed(() => {
  if (selectedActivityScopeIds.value.length !== 1) return null
  const node = activityNodeById.value.get(selectedActivityScopeIds.value[0])
  if (!node) return null
  const graphNode = graphActivityById.value.get(`activity_node:${node.id}`) || { id: `activity_node:${node.id}` }
  return {
    node,
    parentId: node.parent_id || null,
    breadcrumb: activityBreadcrumb(node.id),
    contextStates: boundaryStatesForActivity(node.id, ['context_input']),
    outputStates: boundaryStatesForActivity(node.id, ['declared_output']),
    metrics: activityNodeMetrics(graphNode),
  }
})
const selectedEditableLabel = computed(() => {
  if (selectionFocus.value === 'state' && selectedStateId.value) return selectedStateLabel.value
  if (selectionFocus.value === 'activity' && selectedGraphActivity.value) return selectedActivityLabel.value
  if (selectedStateId.value) return selectedStateLabel.value
  if (selectedGraphActivity.value) return selectedActivityLabel.value
  return ''
})
const selectedDeleteActionLabel = computed(() => {
  const kind = focusedSelectionKind()
  if (kind === 'state') return '删除状态本体'
  if (kind === 'activity') {
    return selectedGraphActivity.value?.atomic_activity_id ? '删除原子活动' : '删除虚拟活动'
  }
  return '删除选中'
})
const selectedDeleteConfirmText = computed(() => {
  const kind = focusedSelectionKind()
  if (kind === 'state') {
    return `确认删除状态本体「${selectedStateLabel.value}」？这不是移出状态包，相关引用和绑定需要一并复核。`
  }
  if (kind === 'activity') {
    const label = selectedGraphActivity.value?.atomic_activity_id ? '原子活动' : '虚拟活动'
    return `确认删除${label}「${selectedActivityLabel.value}」？`
  }
  return `确认删除「${selectedEditableLabel.value}」？`
})
const stateDrawerTitle = computed(() => (stateEditId.value ? '编辑状态' : '新建状态'))
const activityDrawerTitle = computed(() => (activityEditId.value ? '编辑虚拟活动' : '新建虚拟活动'))
const atomicDrawerTitle = computed(() => (atomicEditId.value ? '编辑原子活动' : '新建原子活动'))
const canvasStatusType = computed(() => {
  const blocking = validationSummary.value.blocking_count || 0
  if (blocking) return 'danger'
  if ((validationSummary.value.solver_ready_issue_count || 0) || (validationSummary.value.modeling_issue_count || 0)) return 'warning'
  return 'success'
})
const canvasStatusLabel = computed(() => {
  const blocking = validationSummary.value.blocking_count || 0
  if (blocking) return `阻塞 ${blocking}`
  return graph.value ? '已投影' : '空'
})
const solverReadinessType = computed(() => {
  if (!graph.value) return 'info'
  const blocking = validationSummary.value.blocking_count || 0
  if (blocking) return 'danger'
  if ((validationSummary.value.solver_ready_issue_count || 0) || (validationSummary.value.modeling_issue_count || 0)) return 'warning'
  return 'success'
})
const solverReadinessClass = computed(() => `is-${solverReadinessType.value}`)
const solverReadinessTitle = computed(() => {
  if (!graph.value) return '未加载网络'
  if (solverReadinessType.value === 'danger') return '暂不可求解'
  if (solverReadinessType.value === 'warning') return '提交/求解前需复核'
  return '求解输入就绪'
})
const solverReadinessDetail = computed(() => {
  if (!graph.value) return '请选择设备类型。'
  const summary = validationSummary.value
  const blocking = summary.blocking_count || 0
  const solverIssues = summary.solver_ready_issue_count || 0
  const modelingIssues = summary.modeling_issue_count || 0
  const parts = [
    `阻塞 ${blocking}`,
    `求解器问题 ${solverIssues}`,
    `建模提示 ${modelingIssues}`,
  ]
  if (graphSummary.value.coverage_gap_count) parts.push(`覆盖缺口 ${graphSummary.value.coverage_gap_count}`)
  if (graphSummary.value.partial_virtual_activity_count) parts.push(`部分实现虚拟活动 ${graphSummary.value.partial_virtual_activity_count}`)
  return parts.join(' · ')
})
const solverReadinessButtonType = computed(() => (solverReadinessType.value === 'danger' ? 'danger' : 'primary'))
const filteredStateTree = computed(() => filterTree(stateTree.value, keyword.value))
const filteredActivityTree = computed(() => filterTree(activityTree.value, keyword.value))
const stateParentOptions = computed(() => allStateNodes.value.filter((node) => node.state_kind === 'aggregate' || !node.feature_key))
const activityParentOptions = computed(() => allActivityNodes.value.filter((node) => node.level === 1))
const level2ActivityPackages = computed(() => allActivityNodes.value.filter((node) => node.level === 2))
const localSelectedImpact = computed(() => {
  if (selectionFocus.value === 'activity' && selectedActivityGraphId.value) {
    const inputEdges = visibleEdges.value.filter((edge) => edge.target_id === selectedActivityGraphId.value)
    const outputEdges = visibleEdges.value.filter((edge) => edge.source_id === selectedActivityGraphId.value)
    return {
      upstream: inputEdges.map((edge) => graphStateById.value.get(graphIdNumber(edge.source_id))).filter(Boolean),
      downstream: outputEdges.map((edge) => graphStateById.value.get(graphIdNumber(edge.target_id))).filter(Boolean),
      bindings: bindings.value.filter((item) =>
        selectedActivityGraphId.value === (item.atomic_activity_id ? `atomic_activity:${item.atomic_activity_id}` : `activity_node:${item.activity_node_id}`),
      ),
    }
  }
  if (selectedStateId.value) {
    const upstreamEdges = visibleEdges.value.filter((edge) =>
      String(edge.target_id).startsWith('state_node:') && graphIdNumber(edge.target_id) === Number(selectedStateId.value),
    )
    const downstreamEdges = visibleEdges.value.filter((edge) =>
      String(edge.source_id).startsWith('state_node:') && graphIdNumber(edge.source_id) === Number(selectedStateId.value),
    )
    return {
      upstream: upstreamEdges.map((edge) => graphActivityById.value.get(edge.source_id)).filter(Boolean),
      downstream: downstreamEdges.map((edge) => graphActivityById.value.get(edge.target_id)).filter(Boolean),
      bindings: bindings.value.filter((item) => item.state_node_id === selectedStateId.value),
    }
  }
  if (selectedActivityGraphId.value) {
    const inputEdges = visibleEdges.value.filter((edge) => edge.target_id === selectedActivityGraphId.value)
    const outputEdges = visibleEdges.value.filter((edge) => edge.source_id === selectedActivityGraphId.value)
    return {
      upstream: inputEdges.map((edge) => graphStateById.value.get(graphIdNumber(edge.source_id))).filter(Boolean),
      downstream: outputEdges.map((edge) => graphStateById.value.get(graphIdNumber(edge.target_id))).filter(Boolean),
      bindings: bindings.value.filter((item) =>
        selectedActivityGraphId.value === (item.atomic_activity_id ? `atomic_activity:${item.atomic_activity_id}` : `activity_node:${item.activity_node_id}`),
      ),
    }
  }
  return { upstream: [], downstream: [], bindings: [] }
})
const selectedImpact = computed(() => {
  if (!impactResult.value) return localSelectedImpact.value
  if (impactResult.value.selection_type === 'state') {
    return {
      upstream: impactResult.value.upstream_activities || [],
      downstream: impactResult.value.downstream_activities || [],
      bindings: impactResult.value.bindings || [],
    }
  }
  return {
    upstream: impactResult.value.direct_precondition_states || [],
    downstream: impactResult.value.output_states || [],
    bindings: impactResult.value.bindings || [],
  }
})
const impactHighlights = computed(() => {
  const stateIds = new Set()
  const activityIds = new Set()

  if (selectedStateId.value) stateIds.add(`state_node:${selectedStateId.value}`)
  if (selectedActivityGraphId.value) activityIds.add(selectedActivityGraphId.value)

  const addState = (item) => {
    if (!item) return
    if (item.id && String(item.id).startsWith('state_node:')) stateIds.add(item.id)
    else if (item.state_node_id) stateIds.add(`state_node:${item.state_node_id}`)
  }
  const addActivity = (item) => {
    if (!item) return
    if (item.id && (String(item.id).startsWith('activity_node:') || String(item.id).startsWith('atomic_activity:'))) {
      activityIds.add(item.id)
    } else if (item.atomic_activity_id) {
      activityIds.add(`atomic_activity:${item.atomic_activity_id}`)
    } else if (item.activity_node_id) {
      activityIds.add(`activity_node:${item.activity_node_id}`)
    }
  }

  if (impactResult.value?.selection_type === 'state') {
    ;(impactResult.value.upstream_activities || []).forEach(addActivity)
    ;(impactResult.value.downstream_activities || []).forEach(addActivity)
    ;(impactResult.value.affected_virtual_activities || []).forEach(addActivity)
    ;(impactResult.value.affected_executable_activities || []).forEach(addActivity)
    ;(impactResult.value.parent_state_chain || []).forEach(addState)
    ;(impactResult.value.reference_parent_states || []).forEach(addState)
  } else if (impactResult.value?.selection_type === 'activity') {
    ;(impactResult.value.direct_precondition_states || []).forEach(addState)
    ;(impactResult.value.inherited_precondition_states || []).forEach(addState)
    ;(impactResult.value.output_states || []).forEach(addState)
    ;(impactResult.value.downstream_activities || []).forEach(addActivity)
    ;(impactResult.value.owner_virtual_activities || []).forEach(addActivity)
    ;(impactResult.value.affected_parent_states || []).forEach(addState)
  } else {
    localSelectedImpact.value.upstream.forEach((item) => {
      if (selectionFocus.value === 'activity') addState(item)
      else addActivity(item)
    })
    localSelectedImpact.value.downstream.forEach((item) => {
      if (selectionFocus.value === 'activity') addState(item)
      else addActivity(item)
    })
  }

  return { stateIds, activityIds }
})
const impactMetricLabels = computed(() => {
  if (impactResult.value?.selection_type === 'activity') {
    return { upstream: '前置', downstream: '产出', bindings: '绑定' }
  }
  return { upstream: '上游', downstream: '下游', bindings: '绑定' }
})
const impactStateCoverage = computed(() => {
  if (impactResult.value?.selection_type !== 'state') return null
  const coverage = impactResult.value.child_coverage
  if (!coverage || !coverage.state_node_id) return null
  return coverage
})
const impactSections = computed(() => {
  const impact = impactResult.value
  if (!impact) return []
  if (impact.selection_type === 'state') {
    return [
      { label: '所在状态包路径', items: impact.parent_state_chain || [], type: 'info' },
      { label: '其他出现位置', items: impact.reference_parent_states || [], type: 'warning' },
      { label: '影响虚拟活动', items: impact.affected_virtual_activities || [], type: 'info' },
      { label: '影响原子活动', items: impact.affected_executable_activities || [], type: 'success' },
      { label: '问题', items: impact.issues || [], type: 'danger', issue: true },
    ].filter((section) => section.items.length)
  }
  return [
    { label: '直接前置状态', items: impact.direct_precondition_states || [], type: 'primary' },
    { label: '继承前置状态', items: impact.inherited_precondition_states || [], type: 'warning' },
    { label: '产出状态', items: impact.output_states || [], type: 'success' },
    { label: '所属虚拟活动', items: impact.owner_virtual_activities || [], type: 'info' },
    { label: '受影响状态包', items: impact.affected_parent_states || [], type: 'info' },
    { label: '下游活动', items: impact.downstream_activities || [], type: 'success' },
    { label: '问题', items: impact.issues || [], type: 'danger', issue: true },
  ].filter((section) => section.items.length)
})
const selectedCoverage = computed(() => {
  const binding = selectedBinding.value
  if (!binding) {
    return {
      coverageStatus: 'none',
      boundStateLabel: '-',
      currentLeafCount: 0,
      coveredActiveCount: 0,
      coveredLeaves: [],
      missingLeaves: [],
      staleLeafIds: [],
    }
  }
  const boundState = stateById.value.get(binding.state_node_id)
  const currentLeafIds = leafStateIdsUnder(binding.state_node_id, { activeOnly: true })
  const currentLeafSet = new Set(currentLeafIds)
  const coveredIds = (binding.covered_leaf_state_ids || []).map((id) => Number(id))
  const coveredSet = new Set(coveredIds)
  const coveredLeaves = coveredIds
    .map((id) => stateById.value.get(id))
    .filter(Boolean)
  const missingLeaves = currentLeafIds
    .filter((id) => !coveredSet.has(id))
    .map((id) => stateById.value.get(id))
    .filter(Boolean)
  const staleLeafIds = coveredIds.filter((id) => !currentLeafSet.has(id))
  return {
    coverageStatus: binding.coverage_status || 'unknown',
    boundStateLabel: boundState ? nodeLabel(boundState) : `#${binding.state_node_id}`,
    currentLeafCount: currentLeafIds.length,
    coveredActiveCount: coveredIds.filter((id) => currentLeafSet.has(id)).length,
    coveredLeaves,
    missingLeaves,
    staleLeafIds,
  }
})

function defaultBindingForm(overrides = {}) {
  return {
    binding_role: 'input',
    state_node_id: null,
    activity_graph_id: null,
    op_rule_id: null,
    coverage_mode: 'all',
    covered_leaf_state_ids: [],
    ...overrides,
  }
}

function defaultStateCoverageSelection() {
  return {
    coverage_mode: 'all',
    covered_leaf_state_ids: [],
  }
}

function normalisedNumericIds(ids) {
  const result = []
  const seen = new Set()
  for (const rawId of ids || []) {
    const id = Number(rawId)
    if (!Number.isFinite(id) || seen.has(id)) continue
    seen.add(id)
    result.push(id)
  }
  return result
}

function normalisedStateIds(ids) {
  const result = []
  const seen = new Set()
  for (const rawId of ids || []) {
    let id = null
    if (isDraftStateId(rawId)) {
      id = rawId
    } else {
      const numericId = Number(rawId)
      if (Number.isFinite(numericId)) id = numericId
    }
    if (id == null) continue
    const key = String(id)
    if (seen.has(key)) continue
    seen.add(key)
    result.push(id)
  }
  return result
}

function sameStateId(left, right) {
  return String(left || '') === String(right || '')
}

function stateIdSet(ids) {
  return new Set((ids || []).map((id) => String(id)))
}

function stateHasCoverageChoice(stateNodeId) {
  if (!stateNodeId) return false
  return displayStateChildren(stateNodeId, { activeOnly: true }).length > 0 &&
    leafStateIdsUnder(stateNodeId, { activeOnly: true }).length > 1
}

function resetBindingCoverageSelection() {
  bindingForm.value.coverage_mode = 'all'
  bindingForm.value.covered_leaf_state_ids = []
}

function setBindingCoverageSelectionForState(stateNodeId, coveredIds = null) {
  const activeLeafIds = leafStateIdsUnder(stateNodeId, { activeOnly: true })
  if (!activeLeafIds.length || !Array.isArray(coveredIds) || !coveredIds.length) {
    resetBindingCoverageSelection()
    return
  }
  const activeLeafSet = stateIdSet(activeLeafIds)
  const selectedIds = normalisedStateIds(coveredIds).filter((id) => activeLeafSet.has(String(id)))
  if (!selectedIds.length || selectedIds.length === activeLeafSet.size) {
    resetBindingCoverageSelection()
    return
  }
  bindingForm.value.coverage_mode = 'partial'
  bindingForm.value.covered_leaf_state_ids = selectedIds
}

function sanitizeAtomicOutputCoverages() {
  const selectedOutputIds = normalisedStateIds(atomicForm.value.output_state_ids)
  const current = atomicForm.value.output_coverages || {}
  const next = {}
  for (const stateId of selectedOutputIds) {
    if (!stateHasCoverageChoice(stateId)) continue
    const existing = current[String(stateId)] || defaultStateCoverageSelection()
    const leafSet = stateIdSet(leafStateIdsUnder(stateId, { activeOnly: true }))
    const coveredLeafIds = normalisedStateIds(existing.covered_leaf_state_ids)
      .filter((id) => leafSet.has(String(id)))
    next[String(stateId)] = {
      coverage_mode: existing.coverage_mode === 'partial' ? 'partial' : 'all',
      covered_leaf_state_ids: existing.coverage_mode === 'partial' ? coveredLeafIds : [],
    }
  }
  atomicForm.value.output_coverages = next
}

function onAtomicOutputStatesChange() {
  sanitizeAtomicOutputCoverages()
}

function onAtomicOutputCoverageModeChange(stateId) {
  const coverage = atomicForm.value.output_coverages?.[String(stateId)]
  if (!coverage) return
  if (coverage.coverage_mode !== 'partial') {
    coverage.covered_leaf_state_ids = []
    return
  }
  const leafIds = stateIdSet(leafStateIdsUnder(stateId, { activeOnly: true }))
  coverage.covered_leaf_state_ids = normalisedStateIds(coverage.covered_leaf_state_ids)
    .filter((id) => leafIds.has(String(id)))
}

function atomicOutputCoveredLeafStateIds(stateId) {
  const coverage = atomicForm.value.output_coverages?.[String(stateId)]
  if (!coverage || coverage.coverage_mode !== 'partial') return null
  const leafSet = stateIdSet(leafStateIdsUnder(stateId, { activeOnly: true }))
  return normalisedStateIds(coverage.covered_leaf_state_ids)
    .filter((id) => leafSet.has(String(id)))
}

function defaultStateForm(parent = null) {
  const level = parent ? parent.level + 1 : 1
  return {
    code: '',
    name: '',
    description: '',
    parent_id: parent?.id || null,
    level,
    state_kind: 'atomic',
    feature_key: '',
    target_value: '',
    sort_order: nextSortOrder(stateNodes.value.filter((node) => node.parent_id === (parent?.id || null))),
    is_active: true,
  }
}

function normalizeAllowedValues(values) {
  if (Array.isArray(values)) return values.map((item) => String(item).trim()).filter(Boolean)
  if (typeof values === 'string') {
    try {
      const parsed = JSON.parse(values)
      if (Array.isArray(parsed)) return parsed.map((item) => String(item).trim()).filter(Boolean)
    } catch {
      return values.split(',').map((item) => item.trim()).filter(Boolean)
    }
  }
  return []
}

function stateFeatureLabel(item) {
  if (!item) return ''
  const name = item.feature_name || item.feature_key
  return name === item.feature_key ? item.feature_key : `${name} (${item.feature_key})`
}

function defaultTargetValueForFeature(featureKey) {
  const options = normalizeAllowedValues(stateFeatureDefByKey.value.get(featureKey)?.allowed_values)
  if (options.includes('true')) return 'true'
  if (options.includes('done')) return 'done'
  if (options.length === 1) return options[0]
  return ''
}

function defaultActivityForm(parent = null) {
  const level = parent ? 2 : 1
  const parentId = parent?.id || null
  return {
    code: '',
    name: '',
    description: '',
    parent_id: parentId,
    level,
    activity_category: 'normal',
    sort_order: nextSortOrder(activityNodes.value.filter((node) => String(node.parent_id || '') === String(parentId || ''))),
    is_active: true,
    context_state_ids: [],
    output_state_ids: [],
  }
}

function defaultAtomicForm(packageId = null) {
  return {
    code: '',
    name: '',
    description: '',
    package_id: packageId,
    activity_category: 'normal',
    sort_order: nextSortOrder(atomicActivities.value),
    is_active: true,
    input_state_ids: [],
    output_state_ids: [],
    output_coverages: {},
    duration_min: 30,
  }
}

function nextSortOrder(items) {
  if (!items.length) return 10
  return Math.max(...items.map((item) => Number(item.sort_order || 0))) + 10
}

function filterTree(tree, text) {
  const query = text.trim().toLowerCase()
  if (!query) return tree
  const keep = (items) =>
    items
      .map((item) => ({ ...item, children: keep(item.children || []) }))
      .filter((item) =>
        item.code?.toLowerCase().includes(query) ||
        item.name?.toLowerCase().includes(query) ||
        item.children.length,
      )
  return keep(tree)
}

function matchesNodeKeyword(node, text) {
  const query = text.trim().toLowerCase()
  if (!query) return true
  return node.code?.toLowerCase().includes(query) || node.name?.toLowerCase().includes(query)
}

function buildActivityResourceTree() {
  const packageTree = buildHierarchyTree(allActivityNodes.value).map((node) => ({ ...node }))
  const cloneChildren = (items) => items.map((item) => ({
    ...item,
    resource_type: 'activity_node',
    children: cloneChildren(item.children || []),
  }))
  const tree = cloneChildren(packageTree)
  const packageNodeById = new Map()
  const indexPackages = (items) => {
    for (const item of items) {
      packageNodeById.set(item.id, item)
      indexPackages(item.children || [])
    }
  }
  indexPackages(tree)
  const atomicById = new Map(atomicActivities.value.map((item) => [item.id, item]))
  for (const [packageId, refs] of atomicRefsByPackage.value.entries()) {
    const packageNode = packageNodeById.get(packageId)
    if (!packageNode) continue
    const atomicChildren = refs
      .filter((ref) => ref.is_active !== false)
      .map((ref) => {
        const atomic = atomicById.get(ref.atomic_activity_id)
        if (!atomic) return null
        return {
          ...atomic,
          id: `atomic_ref:${ref.id}`,
          raw_id: atomic.id,
          resource_type: 'atomic_activity',
          package_id: packageId,
          parent_id: packageId,
          level: 3,
          sort_order: ref.sort_order ?? atomic.sort_order ?? 0,
          reference_id: ref.id,
          children: [],
          pathLabel: `${packageNode.pathLabel || nodeLabel(packageNode)} / ${nodeLabel(atomic)}`,
          displayLabel: `原子 ${nodeLabel(atomic)}`,
        }
      })
      .filter(Boolean)
      .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0) || Number(a.raw_id || 0) - Number(b.raw_id || 0))
    packageNode.children = [...(packageNode.children || []), ...atomicChildren]
  }
  const draftAtomicChildren = draftChanges.value
    .filter((change) => change.entity_type === 'atomic_activity' && change.operation === 'create')
    .map((change) => draftAtomicActivityResourceNode(change, packageNodeById))
    .filter(Boolean)
    .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0))
  for (const child of draftAtomicChildren) {
    const packageNode = packageNodeById.get(child.package_id)
    if (!packageNode) continue
    packageNode.children = [...(packageNode.children || []), child]
  }
  return tree
}

function nodeLabel(node) {
  if (!node) return '-'
  return `${node.code} ${node.name}`.trim()
}

function machineTypeOptionLabel(item) {
  return `${item.name} (${item.code})`
}

function isLikelyTestMachineType(item) {
  const text = `${item?.code || ''} ${item?.name || ''}`.toLowerCase()
  return /test|demo|sample|fixture|mock|测试|样例|示例|验证/.test(text)
}

function readRecentMachineTypeIds() {
  try {
    const raw = window.localStorage?.getItem(MACHINE_TYPE_RECENTS_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.map((id) => String(id)).slice(0, MACHINE_TYPE_RECENT_LIMIT) : []
  } catch (_) {
    return []
  }
}

function rememberMachineType(id) {
  if (!id) return
  const next = [
    String(id),
    ...recentMachineTypeIds.value.filter((item) => String(item) !== String(id)),
  ].slice(0, MACHINE_TYPE_RECENT_LIMIT)
  recentMachineTypeIds.value = next
  try {
    window.localStorage?.setItem(MACHINE_TYPE_RECENTS_KEY, JSON.stringify(next))
  } catch (_) {
    // 最近使用只是展示增强，存储失败不影响建模。
  }
}

function issueSeverityLabel(severity) {
  return issueSeverityLabels[severity] || severity || '提示'
}

function issueSeverityTagType(severity) {
  return issueSeverityTagTypes[severity] || 'info'
}

function issueCodeLabel(code) {
  const normalised = String(code || '').toUpperCase()
  return issueCodeLabels[normalised] || code || '未分类问题'
}

function coverageStatusLabel(status) {
  return coverageStatusLabels[status] || status || '-'
}

function networkEditorStatusLabel(status) {
  return networkEditorStatusLabels[status] || status || '-'
}

function runtimeFieldLabel(fields) {
  if (!fields?.length) return '无需运行时补齐'
  return `需补齐：${fields.join(', ')}`
}

function solveTemplateStatusLabel(template) {
  const status = template?.model_status || solverPrecheck.value?.status
  const blockingCount = template?.blocking_issue_count ?? solverPrecheck.value?.summary?.blocking_issue_count ?? 0
  if (template?.solver_handoff_ready === false || status === 'blocked') {
    return blockingCount ? `仅预检摘要：阻塞 ${blockingCount} 项` : '仅预检摘要：不可直接求解'
  }
  return '数据库交接就绪'
}

function solveTemplateStatusTagType(template) {
  const status = template?.model_status || solverPrecheck.value?.status
  return template?.solver_handoff_ready === false || status === 'blocked' ? 'warning' : 'success'
}

function issueNodeTypeLabel(nodeType) {
  return issueNodeTypeLabels[nodeType] || nodeType || '对象'
}

function issueDetailStateId(issue) {
  const details = issue?.details || {}
  const directId = details.state_node_id ?? details.source_state_node_id ?? details.target_state_node_id
  if (Number.isFinite(Number(directId))) return Number(directId)
  if (details.node_type === 'state_node' && Number.isFinite(Number(details.node_id))) {
    return Number(details.node_id)
  }
  return null
}

function issueDetailActivityGraphId(issue) {
  const details = issue?.details || {}
  if (Number.isFinite(Number(details.atomic_activity_id))) {
    return `atomic_activity:${Number(details.atomic_activity_id)}`
  }
  const activityNodeId = details.activity_node_id ?? details.scope_activity_node_id ?? details.source_activity_node_id ?? details.guarded_activity_node_id
  if (Number.isFinite(Number(activityNodeId))) {
    const numericId = Number(activityNodeId)
    return numericId < 0 ? `atomic_activity:${Math.abs(numericId)}` : `activity_node:${numericId}`
  }
  if (Number.isFinite(Number(details.op_rule_id))) {
    const rule = opRules.value.find((item) => Number(item.id) === Number(details.op_rule_id))
    if (rule?.atomic_activity_id) return `atomic_activity:${rule.atomic_activity_id}`
    if (rule?.activity_node_id) return `activity_node:${rule.activity_node_id}`
  }
  if (Number.isFinite(Number(details.node_id))) {
    if (details.node_type === 'atomic_activity') return `atomic_activity:${Number(details.node_id)}`
    if (details.node_type === 'activity_node' || details.node_type === 'legacy_activity_node') {
      return `activity_node:${Number(details.node_id)}`
    }
  }
  return ''
}

function issueStateLabel(issue) {
  const stateId = issue?.related_state_ids?.find((id) => Number.isFinite(Number(id))) ?? issueDetailStateId(issue)
  if (stateId === undefined || stateId === null) return ''
  const numericId = Number(stateId)
  const node = graphStateById.value.get(numericId) || stateById.value.get(numericId)
  return node ? nodeLabel(node) : `#${numericId}`
}

function issueActivityLabel(issue) {
  const activityId = issue?.related_activity_ids?.find(Boolean) || issueDetailActivityGraphId(issue)
  if (!activityId) return ''
  const graphId = String(activityId)
  const graphActivity = graphActivityById.value.get(graphId)
  if (graphActivity) return nodeLabel(graphActivity)
  if (graphId.startsWith('atomic_activity:')) {
    const atomic = atomicActivities.value.find((item) => item.id === graphIdNumber(graphId))
    return atomic ? nodeLabel(atomic) : graphId
  }
  if (graphId.startsWith('activity_node:')) {
    const activity = activityNodeById.value.get(graphIdNumber(graphId))
    return activity ? nodeLabel(activity) : graphId
  }
  return graphId
}

function issueEntitySummary(issue) {
  const bindingId = Number(issue?.details?.binding_id)
  if (Number.isFinite(bindingId) && bindingById.value.has(bindingId)) {
    return `对象：${bindingLabel(bindingById.value.get(bindingId))}`
  }
  const parts = []
  const state = issueStateLabel(issue)
  const activity = issueActivityLabel(issue)
  if (state) parts.push(`状态 ${state}`)
  if (activity) parts.push(`活动 ${activity}`)
  return parts.length ? `对象：${parts.join('，')}` : ''
}

function issueDetailHint(issue) {
  const details = issue?.details || {}
  const hints = []
  if (details.binding_id) hints.push(`绑定 #${details.binding_id}`)
  if (details.coverage_status) hints.push(`覆盖状态：${coverageStatusLabel(details.coverage_status)}`)
  if (Number.isFinite(Number(details.covered_leaf_count))) hints.push(`覆盖叶子：${details.covered_leaf_count}`)
  if (Number.isFinite(Number(details.cross_level_binding_count))) {
    hints.push(`跨层级绑定：${details.cross_level_binding_count}`)
  }
  if (Array.isArray(details.missing_leaf_state_ids) && details.missing_leaf_state_ids.length) {
    hints.push(`缺失叶子：${details.missing_leaf_state_ids.length}`)
  }
  if (Array.isArray(details.op_rule_ids) && details.op_rule_ids.length) {
    hints.push(`规则：${details.op_rule_ids.join(', ')}`)
  }
  if (details.node_id && details.node_type && !issueEntitySummary(issue)) {
    hints.push(`${issueNodeTypeLabel(details.node_type)} #${details.node_id}`)
  }
  if (details.feature_key) {
    const operator = details.operator || ''
    const target = details.target_value ?? ''
    hints.push(`事实：${[details.feature_key, operator, target].filter((item) => item !== '').join(' ')}`)
  }
  return hints.length ? `（${hints.join('；')}）` : ''
}

function issueMessageText(issue) {
  const code = String(issue?.code || '').toUpperCase()
  const message = issueMessageLabels[code] || issue?.message || '系统返回了需要复核的问题。'
  return [message, issueDetailHint(issue), issueEntitySummary(issue)].filter(Boolean).join(' ')
}

function issueSuggestedActionText(issue) {
  const code = String(issue?.code || '').toUpperCase()
  return issueSuggestedActionLabels[code] ||
    '定位问题对象后，根据说明补齐缺失关系或确认该结构是否符合建模意图。'
}

function validationIssuesBySeverity(validation, severity) {
  if (!validation) return []
  return [
    ...(validation.modeling_issues || []),
    ...(validation.solver_ready_issues || []),
  ].filter((issue) => issue?.severity === severity)
}

function validationIssueReviewMessage(validation, severity = 'warning') {
  const issues = validationIssuesBySeverity(validation, severity)
  if (!issues.length) return ''
  const visibleIssues = issues.slice(0, 5)
  const issueLines = visibleIssues.map((issue, index) =>
    `${index + 1}. ${issueCodeLabel(issue.code)}：${issueMessageText(issue)} 建议：${issueSuggestedActionText(issue)}`,
  )
  if (issues.length > visibleIssues.length) {
    issueLines.push(`还有 ${issues.length - visibleIssues.length} 个问题，请在底部校验列表继续查看。`)
  }
  return issueLines.join('\n')
}

function activityBreadcrumb(activityNodeId) {
  const result = []
  const seen = new Set()
  let current = activityNodeById.value.get(activityNodeId)
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    result.unshift(current)
    current = current.parent_id ? activityNodeById.value.get(current.parent_id) : null
  }
  return result
}

function boundaryStatesForActivity(activityNodeId, roles) {
  const roleSet = new Set(roles)
  const seen = new Set()
  const result = []
  for (const binding of bindings.value) {
    if (binding.activity_node_id !== activityNodeId || !roleSet.has(binding.binding_role)) continue
    const state = stateById.value.get(binding.state_node_id)
    if (!state || seen.has(state.id)) continue
    seen.add(state.id)
    result.push(state)
  }
  return result
}

function statePackageCoverage(node) {
  return statePackageCoverageById.value.get(node?.state_node_id) || null
}

function stateNodeMetrics(node) {
  return stateNodeMetricsById.value.get(node?.state_node_id) || {
    childCount: 0,
    maxDescendantDepth: 0,
    relatedActivityCount: 0,
  }
}

function activityNodeMetrics(node) {
  return activityNodeMetricsById.value.get(node?.id) || {
    inputCount: 0,
    inheritedInputCount: 0,
    outputCount: 0,
    childCount: 0,
    maxDescendantDepth: 0,
    crossLevel: false,
    crossLevelCount: 0,
    declaredOutputCount: 0,
    implementedOutputCount: 0,
    missingOutputCount: 0,
  }
}

function isImpactEdge(edge) {
  const stateMatches = (graphId) => {
    if (!String(graphId || '').startsWith('state_node:')) return false
    if (impactHighlights.value.stateIds.has(graphId)) return true
    return impactHighlights.value.stateIds.has(`state_node:${graphIdNumber(graphId)}`)
  }
  return (edge.aggregateEdges || [edge]).some((item) => (
    stateMatches(item.source_id) &&
    impactHighlights.value.activityIds.has(item.target_id)
  ) || (
    impactHighlights.value.activityIds.has(item.source_id) &&
    stateMatches(item.target_id)
  ))
}

function displayStateChildren(stateNodeId, { activeOnly = true } = {}) {
  const children = [
    ...(stateChildrenByParent.value.get(stateNodeId) || []),
    ...(stateReferenceChildrenByParent.value.get(stateNodeId) || []),
  ]
  const seen = new Set()
  return children
    .filter((child) => {
      if (!child || seen.has(child.id)) return false
      seen.add(child.id)
      return !activeOnly || child.is_active
    })
    .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0) || Number(a.id || 0) - Number(b.id || 0))
}

function leafStateIdsUnder(stateNodeId, { activeOnly = true } = {}) {
  const root = stateById.value.get(stateNodeId)
  if (!root || (activeOnly && !root.is_active)) return []
  const result = []
  const seen = new Set()
  const visit = (node) => {
    if (!node || seen.has(node.id)) return
    seen.add(node.id)
    const children = displayStateChildren(node.id, { activeOnly })
    if (!children.length) {
      result.push(node.id)
      return
    }
    children.forEach(visit)
  }
  visit(root)
  return result
}

function stateDescendantNodeIds(stateNodeId, { activeOnly = true } = {}) {
  const root = stateById.value.get(stateNodeId)
  if (!root || (activeOnly && !root.is_active)) return []
  const result = []
  const queue = [stateNodeId]
  const seen = new Set()
  while (queue.length) {
    const current = queue.shift()
    if (!current || seen.has(current)) continue
    seen.add(current)
    const children = displayStateChildren(current, { activeOnly })
    for (const child of children) {
      result.push(child.id)
      queue.push(child.id)
    }
  }
  return result
}

function statePackageContainsState(containerStateId, targetStateId) {
  if (!containerStateId || !targetStateId) return false
  if (sameStateId(containerStateId, targetStateId)) return true
  return stateDescendantNodeIds(containerStateId, { activeOnly: true }).some((id) => sameStateId(id, targetStateId))
}

function factStatesForStateIds(stateIds) {
  const result = []
  const seen = new Set()
  for (const stateId of stateIds || []) {
    const leafIds = leafStateIdsUnder(stateId, { activeOnly: true })
    for (const leafId of leafIds) {
      const state = stateById.value.get(leafId)
      if (!state || seen.has(state.id)) continue
      seen.add(state.id)
      if (state.feature_key && state.target_value != null) {
        result.push(state)
      }
    }
  }
  return result
}

function rulePreconditionsForStateIds(stateIds) {
  return factStatesForStateIds(stateIds).map((state) => ({
    feature_key: state.feature_key,
    operator: state.operator || 'eq',
    feature_value: state.target_value,
    value_list: null,
  }))
}

function ruleEffectsForStateIds(stateIds) {
  return factStatesForStateIds(stateIds).map((state) => ({
    feature_key: state.feature_key,
    effect_type: 'set',
    new_value: state.target_value,
    delta_value: null,
  }))
}

function activityDescendantNodeIds(activityNodeId) {
  if (!activityNodeId) return []
  const result = []
  const queue = [activityNodeId]
  const seen = new Set()
  while (queue.length) {
    const current = queue.shift()
    const currentKey = String(current || '')
    if (!currentKey || seen.has(currentKey)) continue
    seen.add(currentKey)
    result.push(current)
    for (const child of activityChildrenByParent.value.get(current) || []) {
      queue.push(child.id)
    }
  }
  return result
}

function atomicIdsUnderActivityNode(activityNodeId) {
  const activityIds = new Set(activityDescendantNodeIds(activityNodeId))
  const atomicIds = new Set()
  for (const [packageId, refs] of atomicRefsByPackage.value.entries()) {
    if (!activityIds.has(packageId)) continue
    for (const ref of refs || []) {
      if (ref.is_active !== false && ref.atomic_activity_id) {
        atomicIds.add(ref.atomic_activity_id)
      }
    }
  }
  for (const node of visibleActivityNodes.value) {
    if (!node.atomic_activity_id || node.is_active === false) continue
    if (activityPathContains(node, activityNodeId)) {
      atomicIds.add(node.atomic_activity_id)
    }
  }
  return atomicIds
}

function supportsGraphActivityBinding(activity) {
  return !!activity && (!!activity.atomic_activity_id || activity.activity_type === 'virtual')
}

function bindingRoleText(role) {
  return {
    context_input: '上下文输入',
    declared_output: '声明输出',
    input: '输入',
    output: '产出',
  }[role] || role || '-'
}

function bindingRoleAllowedForActivity(activity, role) {
  if (!supportsGraphActivityBinding(activity) || !role) return false
  if (activity.atomic_activity_id) return ['input', 'output'].includes(role)
  return ['context_input', 'declared_output'].includes(role)
}

function activeOpRulesForAtomicActivity(atomicActivityId) {
  if (!atomicActivityId) return []
  return opRules.value.filter((item) =>
    item.atomic_activity_id === atomicActivityId && item.is_active !== false,
  )
}

function atomicRuleSelectionWarning(activity, quick = false) {
  const rules = activeOpRulesForAtomicActivity(activity?.atomic_activity_id)
  if (!rules.length) {
    return quick
      ? '快捷原子活动连线需要一条启用规则。请先在活动能力或规则维护中为该原子活动创建并启用 op_rule。'
      : '该原子活动没有启用规则。请先在活动能力或规则维护中创建并启用 op_rule，再回到这里连接。'
  }
  return quick
    ? '快捷原子活动连线需要且只能有一条启用规则；当前存在多条，请在右侧规则下拉框中选择后点击连接。'
    : '该原子活动存在多条启用规则，请在右侧规则下拉框中选择一条明确规则。'
}

function canResolveOpRuleForActivity(activity, opRuleId = null) {
  if (!activity?.atomic_activity_id) return true
  const rules = activeOpRulesForAtomicActivity(activity.atomic_activity_id)
  if (opRuleId) return rules.some((item) => item.id === opRuleId)
  return rules.length === 1
}

function errorMessage(error) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg || item.detail || String(item)).join('; ')
  if (detail && typeof detail === 'object') return networkEditorPayloadMessage(detail) || detail.message || JSON.stringify(detail)
  const errorMessagePayload = error?.response?.data?.error_message
  if (Array.isArray(errorMessagePayload)) return errorMessagePayload.map((item) => item.msg || item.detail || String(item)).join('; ')
  if (errorMessagePayload && typeof errorMessagePayload === 'object') {
    return networkEditorPayloadMessage(errorMessagePayload) || errorMessagePayload.message || JSON.stringify(errorMessagePayload)
  }
  if (errorMessagePayload) return errorMessagePayload
  return detail || error?.message || '操作失败'
}

function networkEditorErrorPayload(error) {
  const data = error?.response?.data
  const payload = data?.detail ?? data?.error_message
  return payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : null
}

function networkEditorPayloadMessage(payload) {
  if (!payload || typeof payload !== 'object') return ''
  if (payload.validation) {
    const errorCount = Number(payload.error_count || 0)
    const warningCount = Number(payload.warning_count || 0)
    const solverReadyErrorCount = Number(payload.solver_ready_error_count || 0)
    if (errorCount) {
      return `网络编辑器校验阻止统一提交：结构错误 ${errorCount} 个，需复核 ${warningCount} 个。请查看底部校验列表。`
    }
    if (solverReadyErrorCount) {
      return `当前模型可保存，但存在 ${solverReadyErrorCount} 个求解准备阻塞项，提交后仍不可直接求解。`
    }
    return `网络编辑器校验需要复核：提示 ${warningCount} 个。请查看底部校验列表。`
  }
  if (payload.base_revision && payload.current_revision) {
    return '网络数据已被其他会话修改，本次草稿未提交。请刷新已提交数据或取消后重新进入编辑。'
  }
  return ''
}

function notifyOperationError(action, error) {
  ElMessage.error(`${action}: ${errorMessage(error)}`)
}

function isUserCancel(error) {
  return error === 'cancel' || error === 'close' || error?.message === 'cancel' || error?.message === 'close'
}

function requireEditMode(action = '该操作') {
  if (canMutate.value) return true
  ElMessage.warning(`${action}需要先进入编辑模式`)
  return false
}

function mergeDraftPayload(existingPayload = {}, nextPayload = {}) {
  const merged = { ...existingPayload, ...nextPayload }
  const existingMetadata = existingPayload.metadata_json
  const nextMetadata = nextPayload.metadata_json
  const existingMetadataObject = existingMetadata && typeof existingMetadata === 'object' && !Array.isArray(existingMetadata)
  const nextMetadataObject = nextMetadata && typeof nextMetadata === 'object' && !Array.isArray(nextMetadata)
  if (existingMetadataObject && nextMetadataObject) {
    merged.metadata_json = { ...existingMetadata, ...nextMetadata }
  } else if (existingMetadataObject && nextMetadata == null) {
    merged.metadata_json = existingMetadata
  } else if (nextMetadataObject) {
    merged.metadata_json = nextMetadata
  }
  return merged
}

function draftStateId(clientId) {
  return `${DRAFT_STATE_ID_PREFIX}${clientId}`
}

function isDraftStateId(value) {
  return typeof value === 'string' && value.startsWith(DRAFT_STATE_ID_PREFIX)
}

function draftStateClientId(value) {
  return isDraftStateId(value) ? value.slice(DRAFT_STATE_ID_PREFIX.length) : null
}

function draftActivityId(clientId) {
  return `${DRAFT_ACTIVITY_ID_PREFIX}${clientId}`
}

function isDraftActivityId(value) {
  return typeof value === 'string' && value.startsWith(DRAFT_ACTIVITY_ID_PREFIX)
}

function draftActivityClientId(value) {
  return isDraftActivityId(value) ? value.slice(DRAFT_ACTIVITY_ID_PREFIX.length) : null
}

function draftAtomicActivityId(clientId) {
  return `${DRAFT_ATOMIC_ACTIVITY_ID_PREFIX}${clientId}`
}

function isDraftAtomicActivityId(value) {
  return typeof value === 'string' && value.startsWith(DRAFT_ATOMIC_ACTIVITY_ID_PREFIX)
}

function draftAtomicActivityClientId(value) {
  return isDraftAtomicActivityId(value) ? value.slice(DRAFT_ATOMIC_ACTIVITY_ID_PREFIX.length) : null
}

function draftStateResourceNode(change) {
  const payload = change?.payload || {}
  const clientId = change?.client_id
  if (!clientId || !payload.name) return null
  const parentId = payload.parent_id || null
  const parent = parentId && !isDraftStateId(parentId) ? baseStateById.value.get(parentId) : null
  return {
    id: draftStateId(clientId),
    draft_client_id: clientId,
    is_draft: true,
    machine_type_id: payload.machine_type_id || machineTypeId.value,
    parent_id: parentId,
    level: payload.level || (parent ? Number(parent.level || 0) + 1 : 1),
    code: payload.code || null,
    name: payload.name,
    feature_key: payload.feature_key || null,
    operator: payload.operator || 'eq',
    target_value: payload.target_value ?? null,
    state_kind: payload.state_kind || (payload.feature_key ? 'atomic' : 'aggregate'),
    sort_order: payload.sort_order || 0,
    is_active: payload.is_active !== false,
    metadata_json: payload.metadata_json || {},
  }
}

function draftActivityResourceNode(change) {
  const payload = change?.payload || {}
  const clientId = change?.client_id
  if (!clientId || !payload.name) return null
  const parentId = payload.parent_id || null
  return {
    id: draftActivityId(clientId),
    draft_client_id: clientId,
    is_draft: true,
    machine_type_id: payload.machine_type_id || machineTypeId.value,
    parent_id: parentId,
    level: payload.level || (parentId ? 2 : 1),
    code: payload.code || null,
    name: payload.name,
    description: payload.description || '',
    activity_category: payload.activity_category || 'normal',
    sort_order: payload.sort_order || 0,
    is_active: payload.is_active !== false,
    metadata_json: payload.metadata_json || {},
  }
}

function draftAtomicActivityResourceNode(change, packageNodeById = new Map()) {
  const payload = change?.payload || {}
  const clientId = change?.client_id
  if (!clientId || !payload.name) return null
  const packageId = payload.package_id || null
  const packageNode = packageId ? packageNodeById.get(packageId) : null
  const atomicId = draftAtomicActivityId(clientId)
  return {
    id: `atomic_ref:${atomicId}`,
    raw_id: atomicId,
    atomic_activity_id: atomicId,
    draft_client_id: clientId,
    is_draft: true,
    resource_type: 'atomic_activity',
    machine_type_id: payload.machine_type_id || machineTypeId.value,
    package_id: packageId,
    parent_id: packageId,
    level: 3,
    code: payload.code || null,
    name: payload.name,
    description: payload.description || '',
    activity_category: payload.activity_category || 'normal',
    sort_order: payload.sort_order || 0,
    is_active: payload.is_active !== false,
    metadata_json: payload.metadata_json || {},
    reference_id: null,
    children: [],
    pathLabel: packageNode ? `${packageNode.pathLabel || nodeLabel(packageNode)} / ${nodeLabel(payload)}` : nodeLabel(payload),
    displayLabel: `Draft ${nodeLabel(payload)}`,
  }
}

function draftStateGraphNode(change, graphByStateId = baseGraphStateById.value) {
  const payload = change?.payload || {}
  const clientId = change?.client_id
  if (!clientId || !payload.name) return null
  const stateNodeId = draftStateId(clientId)
  const parentId = payload.parent_id || null
  const parentGraphNode = parentId ? graphByStateId.get(parentId) : null
  const parentPathIds = Array.isArray(parentGraphNode?.path_ids) ? parentGraphNode.path_ids : []
  const parentPath = parentPathIds.some((item) => Array.isArray(item))
    ? (parentPathIds[0] || [])
    : parentPathIds
  const pathIds = parentId
    ? [
      ...parentPath,
      ...(String(parentPath[parentPath.length - 1] || '') === String(parentId) ? [] : [parentId]),
      stateNodeId,
    ]
    : [stateNodeId]
  const isAggregate = payload.state_kind === 'aggregate' || !payload.feature_key
  return {
    id: `state_node:${stateNodeId}`,
    state_node_id: stateNodeId,
    draft_client_id: clientId,
    is_draft: true,
    machine_type_id: payload.machine_type_id || machineTypeId.value,
    parent_id: parentId,
    parent_state_node_id: parentId,
    reference_id: null,
    reference_ids: [],
    reference_parent_ids: [],
    path_ids: pathIds,
    level: payload.level || (parentGraphNode ? Number(parentGraphNode.level || 0) + 1 : 1),
    code: payload.code || null,
    name: payload.name,
    feature_key: payload.feature_key || null,
    operator: payload.operator || 'eq',
    target_value: payload.target_value ?? null,
    state_kind: payload.state_kind || (payload.feature_key ? 'atomic' : 'aggregate'),
    sort_order: payload.sort_order || 0,
    is_active: payload.is_active !== false,
    is_leaf: !isAggregate,
    leaf_count: isAggregate ? 0 : 1,
    metadata_json: payload.metadata_json || {},
  }
}

function draftActivityGraphNode(change, graphByActivityId) {
  const payload = change?.payload || {}
  const clientId = change?.client_id
  if (!clientId || !payload.name) return null
  const activityNodeId = draftActivityId(clientId)
  const parentId = payload.parent_id || null
  const parentGraphNode = parentId ? graphByActivityId.get(parentId) : null
  const parentPathIds = Array.isArray(parentGraphNode?.path_ids) ? parentGraphNode.path_ids : []
  const parentPath = parentPathIds.some((item) => Array.isArray(item))
    ? (parentPathIds[0] || [])
    : parentPathIds
  const pathIds = parentId
    ? [
      ...parentPath,
      ...(String(parentPath[parentPath.length - 1] || '') === String(parentId) ? [] : [parentId]),
      activityNodeId,
    ]
    : [activityNodeId]
  const parentActivityIds = parentId
    ? [
      ...parentPath,
      ...(String(parentPath[parentPath.length - 1] || '') === String(parentId) ? [] : [parentId]),
    ]
    : []
  return {
    id: `activity_node:${activityNodeId}`,
    activity_node_id: activityNodeId,
    atomic_activity_id: null,
    draft_client_id: clientId,
    is_draft: true,
    machine_type_id: payload.machine_type_id || machineTypeId.value,
    parent_id: parentId,
    parent_graph_id: parentGraphNode?.id || null,
    parent_activity_node_ids: parentActivityIds,
    child_activity_node_ids: [],
    level: payload.level || (parentGraphNode ? Number(parentGraphNode.level || 0) + 1 : 1),
    code: payload.code || null,
    name: payload.name,
    description: payload.description || '',
    activity_type: 'virtual',
    activity_category: payload.activity_category || 'normal',
    solver_participation: false,
    sort_order: payload.sort_order || 0,
    is_active: payload.is_active !== false,
    path_ids: pathIds,
    metadata_json: payload.metadata_json || {},
  }
}

function draftAtomicActivityGraphNode(change, graphByActivityId) {
  const payload = change?.payload || {}
  const clientId = change?.client_id
  if (!clientId || !payload.name) return null
  const atomicActivityId = draftAtomicActivityId(clientId)
  const packageId = payload.package_id || null
  const packageGraphNode = packageId ? graphByActivityId.get(packageId) : null
  const packagePathIds = Array.isArray(packageGraphNode?.path_ids) ? packageGraphNode.path_ids : []
  const packagePath = packagePathIds.some((item) => Array.isArray(item))
    ? (packagePathIds[0] || [])
    : packagePathIds
  const parentActivityIds = packageId
    ? [
      ...packagePath,
      ...(String(packagePath[packagePath.length - 1] || '') === String(packageId) ? [] : [packageId]),
    ]
    : []
  const pathIds = parentActivityIds.length
    ? [[...parentActivityIds, atomicActivityId]]
    : [[atomicActivityId]]
  return {
    id: `atomic_activity:${atomicActivityId}`,
    activity_node_id: null,
    atomic_activity_id: atomicActivityId,
    draft_client_id: clientId,
    is_draft: true,
    machine_type_id: payload.machine_type_id || machineTypeId.value,
    parent_id: null,
    parent_graph_id: packageGraphNode?.id || null,
    parent_activity_node_ids: parentActivityIds,
    child_activity_node_ids: [],
    level: packageGraphNode ? Number(packageGraphNode.level || 0) + 1 : 3,
    code: payload.code || null,
    name: payload.name,
    description: payload.description || '',
    activity_type: 'executable',
    activity_category: payload.activity_category || 'normal',
    solver_participation: true,
    sort_order: payload.sort_order || 0,
    is_active: payload.is_active !== false,
    path_ids: pathIds,
    metadata_json: payload.metadata_json || {},
  }
}

function draftBindingEdge(change, index = 0) {
  if (change?.entity_type !== 'activity_state_binding' || change.operation !== 'create') return null
  return bindingPayloadEdge(change.payload, {
    idPrefix: `draft-binding:${change.client_id || index}`,
    sourceKind: 'draft_activity_state_binding',
    isDraft: true,
  })
}

function pendingBindingPreviewEdge(preview) {
  return bindingPayloadEdge(preview, {
    idPrefix: 'pending-binding-preview',
    sourceKind: 'pending_activity_state_binding',
    isPending: true,
  })
}

function bindingPayloadEdge(payload, { idPrefix, sourceKind, isDraft = false, isPending = false } = {}) {
  if (!payload?.state_node_id || !payload?.binding_role) return null
  const stateGraphId = graphIdForBindingState(payload.state_node_id)
  const activityGraphId = graphIdForBindingActivity(payload)
  if (!stateGraphId || !activityGraphId) return null
  const isOutput = ['output', 'declared_output'].includes(payload.binding_role)
  const type = isOutput ? 'ACTIVITY_TO_STATE' : 'STATE_TO_ACTIVITY'
  return {
    id: `${idPrefix}:${type}:${stateGraphId}:${activityGraphId}:${payload.binding_role}`,
    source_id: isOutput ? activityGraphId : stateGraphId,
    target_id: isOutput ? stateGraphId : activityGraphId,
    type,
    binding_id: null,
    binding_role: payload.binding_role,
    source_kind: sourceKind,
    coverage_status: 'draft',
    is_draft: isDraft,
    is_pending: isPending,
  }
}

function graphIdForBindingState(stateNodeId) {
  if (!stateNodeId) return null
  const match = visibleStateNodes.value.find((node) =>
    String(node.state_node_id || '') === String(stateNodeId),
  )
  return match?.id || `state_node:${stateNodeId}`
}

function graphIdForBindingActivity(payload) {
  if (payload?.atomic_activity_id) {
    const atomicActivityId = atomicActivityRefComparableId(payload.atomic_activity_id)
    return atomicActivityId ? `atomic_activity:${atomicActivityId}` : null
  }
  const activityNodeId = activityRefComparableId(payload?.activity_node_id)
  if (!activityNodeId) return null
  const match = visibleActivityNodes.value.find((node) =>
    String(node.activity_node_id || '') === String(activityNodeId),
  )
  return match?.id || `activity_node:${activityNodeId}`
}

function committedStateIdForImpact(stateId) {
  if (!stateId || isDraftStateId(stateId)) return null
  const numericId = Number(stateId)
  return Number.isInteger(numericId) && numericId > 0 ? numericId : null
}

function committedActivityGraphIdForImpact(activityGraphId) {
  const graphId = String(activityGraphId || '')
  return /^(activity_node|atomic_activity):[1-9]\d*$/.test(graphId) ? graphId : null
}

function resetImpactRequestState() {
  impactRequestSequence += 1
  impactResult.value = null
  impactLoading.value = false
}

function updateDraftStateLayout(node, pos) {
  if (!node?.is_draft || !node.draft_client_id) return false
  const draftIndex = draftChanges.value.findIndex((change) =>
    change.client_id === node.draft_client_id &&
    change.entity_type === 'state_node' &&
    change.operation === 'create',
  )
  if (draftIndex < 0) return false
  const existing = draftChanges.value[draftIndex]
  draftChanges.value.splice(draftIndex, 1, {
    ...existing,
    payload: mergeDraftPayload(existing.payload, {
      metadata_json: metadataWithLayout(existing.payload?.metadata_json, pos),
    }),
  })
  invalidateDerivedResults()
  return true
}

function updateDraftActivityLayout(node, pos) {
  if (!node?.is_draft || !node.draft_client_id) return false
  const entityType = node.atomic_activity_id ? 'atomic_activity' : 'activity_node'
  const draftIndex = draftChanges.value.findIndex((change) =>
    change.client_id === node.draft_client_id &&
    change.entity_type === entityType &&
    change.operation === 'create',
  )
  if (draftIndex < 0) return false
  const existing = draftChanges.value[draftIndex]
  draftChanges.value.splice(draftIndex, 1, {
    ...existing,
    payload: mergeDraftPayload(existing.payload, {
      metadata_json: metadataWithLayout(existing.payload?.metadata_json, pos),
    }),
  })
  invalidateDerivedResults()
  return true
}

function serializeStateRefForCommit(stateId) {
  const clientId = draftStateClientId(stateId)
  return clientId ? { _draft_ref: clientId } : stateId
}

function serializeStateRefsForCommit(stateIds) {
  if (!Array.isArray(stateIds)) return stateIds
  return stateIds.map((stateId) => serializeStateRefForCommit(stateId))
}

function serializeActivityRefForCommit(activityNodeId) {
  const clientId = draftActivityClientId(activityNodeId)
  return clientId ? { _draft_ref: clientId } : activityNodeId
}

function serializeAtomicActivityRefForCommit(atomicActivityId) {
  const clientId = draftAtomicActivityClientId(atomicActivityId)
  return clientId ? { _draft_ref: clientId } : atomicActivityId
}

function serializeDraftChangeForCommit(change) {
  if (!change.payload) {
    return change
  }
  if (change.entity_type === 'state_node' && Object.prototype.hasOwnProperty.call(change.payload, 'parent_id')) {
    return {
      ...change,
      payload: {
        ...change.payload,
        parent_id: serializeStateRefForCommit(change.payload.parent_id),
      },
    }
  }
  if (change.entity_type === 'activity_node' && Object.prototype.hasOwnProperty.call(change.payload, 'parent_id')) {
    return {
      ...change,
      payload: {
        ...change.payload,
        parent_id: serializeActivityRefForCommit(change.payload.parent_id),
      },
    }
  }
  if (change.entity_type === 'atomic_activity' && Object.prototype.hasOwnProperty.call(change.payload, 'package_id')) {
    return {
      ...change,
      payload: {
        ...change.payload,
        package_id: serializeActivityRefForCommit(change.payload.package_id),
      },
    }
  }
  if (change.entity_type === 'activity_state_binding') {
    const payload = { ...change.payload }
    if (Object.prototype.hasOwnProperty.call(payload, 'activity_node_id')) {
      payload.activity_node_id = serializeActivityRefForCommit(payload.activity_node_id)
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'atomic_activity_id')) {
      payload.atomic_activity_id = serializeAtomicActivityRefForCommit(payload.atomic_activity_id)
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'state_node_id')) {
      payload.state_node_id = serializeStateRefForCommit(payload.state_node_id)
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'covered_leaf_state_ids')) {
      payload.covered_leaf_state_ids = serializeStateRefsForCommit(payload.covered_leaf_state_ids)
    }
    return {
      ...change,
      payload,
    }
  }
  if (change.entity_type === 'op_rule') {
    const payload = { ...change.payload }
    if (Object.prototype.hasOwnProperty.call(payload, 'activity_node_id')) {
      payload.activity_node_id = serializeActivityRefForCommit(payload.activity_node_id)
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'atomic_activity_id')) {
      payload.atomic_activity_id = serializeAtomicActivityRefForCommit(payload.atomic_activity_id)
    }
    return {
      ...change,
      payload,
    }
  }
  return {
    ...change,
  }
}

function queueDraftChange({ entityType, operation, entityId = null, payload = {}, label = '' }) {
  if (!requireEditMode('加入编辑草稿')) return null
  if (operation === 'update' && entityId) {
    const existingIndex = draftChanges.value.findIndex((change) =>
      change.entity_type === entityType &&
      change.operation === 'update' &&
      change.entity_id === entityId,
    )
    if (existingIndex >= 0) {
      const existing = draftChanges.value[existingIndex]
      draftChanges.value.splice(existingIndex, 1, {
        ...existing,
        payload: mergeDraftPayload(existing.payload, payload),
        label: existing.label || label,
      })
      invalidateDerivedResults()
      return existing.client_id
    }
  }
  draftSequence.value += 1
  const clientId = `draft-${draftSequence.value}`
  draftChanges.value.push({
    client_id: clientId,
    entity_type: entityType,
    operation,
    entity_id: entityId,
    payload,
    label,
  })
  invalidateDerivedResults()
  return clientId
}

function upsertDraftUpdate({ entityType, entityId, payload, label }) {
  queueDraftChange({ entityType, operation: 'update', entityId, payload, label })
}

function invalidateDerivedResults() {
  validationResult.value = null
  solverPrecheck.value = null
}

function startEditSession() {
  if (!machineTypeId.value) return
  closeContextMenu()
  editorMode.value = 'edit'
  editBaselineRevision.value = graph.value?.revision || null
  draftChanges.value = []
  draftSequence.value = 0
  pendingBindingPreview.value = null
  layoutDraft.value = {}
  containerDraft.value = {}
  pendingStateLayout.value = null
  resetCollapsedStateContainers()
  resetCollapsedActivityContainers()
  resetStateActivityCreationSelection()
  batchBindingDialogVisible.value = false
  batchBindingForm.value = { input_state_ids: [], output_state_ids: [], op_rule_id: null }
  ElMessage.success('已进入编辑模式')
}

async function cancelEditSession() {
  if (!isEditMode.value) return
  closeContextMenu()
  if (hasDraftChanges.value) {
    try {
      await ElMessageBox.confirm('取消编辑会丢弃本次草稿，是否继续？', '取消编辑', {
        type: 'warning',
        confirmButtonText: '丢弃草稿',
        cancelButtonText: '返回编辑',
      })
    } catch (error) {
      if (isUserCancel(error)) return
      throw error
    }
  }
  draftChanges.value = []
  draftSequence.value = 0
  pendingBindingPreview.value = null
  editBaselineRevision.value = null
  layoutDraft.value = {}
  containerDraft.value = {}
  pendingStateLayout.value = null
  resetCollapsedStateContainers()
  resetCollapsedActivityContainers()
  resetStateActivityCreationSelection()
  batchBindingDialogVisible.value = false
  batchBindingForm.value = { input_state_ids: [], output_state_ids: [], op_rule_id: null }
  editorMode.value = 'preview'
  await loadAll()
  ElMessage.success('已取消编辑，回到预览模式')
}

async function submitDraftChanges() {
  if (!machineTypeId.value || !hasDraftChanges.value) return
  draftSubmitting.value = true
  try {
    const buildCommitPayload = (allowWarnings) => ({
      changes: draftChanges.value.map(serializeDraftChangeForCommit),
      base_revision: editBaselineRevision.value,
      allow_warnings: allowWarnings,
      validate_after_apply: true,
      validation_payload: graphPayload(),
    })
    let response = null
    try {
      response = await commitNetworkEditorDraft(machineTypeId.value, buildCommitPayload(false))
    } catch (error) {
      const payload = networkEditorErrorPayload(error)
      const validation = payload?.validation || null
      if (validation) validationResult.value = validation
      const warningOnly = payload && Number(payload.error_count || 0) === 0 && Number(payload.warning_count || 0) > 0
      if (!warningOnly) throw error
      const solverReadyErrorCount = Number(payload.solver_ready_error_count || 0)
      const reviewMessage = [
        solverReadyErrorCount
          ? `当前模型可以保存，但提交后仍有 ${solverReadyErrorCount} 个求解准备阻塞项，暂不可直接求解。`
          : `提交前发现 ${payload.warning_count} 个非阻断提示。`,
        validationIssueReviewMessage(validation, 'warning'),
        solverReadyErrorCount ? validationIssueReviewMessage(validation, 'error') : '',
        solverReadyErrorCount
          ? '这些问题不会阻止保存模型，但会阻止求解；确认后可继续保存。'
          : '这些提示不会阻止提交，但建议确认后再继续。',
      ].filter(Boolean).join('\n\n')
      try {
        await ElMessageBox.confirm(
          reviewMessage,
          '提交前复核',
          {
            type: 'warning',
            confirmButtonText: '继续提交',
            cancelButtonText: '返回编辑',
            customClass: 'network-submit-review',
            customStyle: { maxWidth: '720px' },
            dangerouslyUseHTMLString: false,
          },
        )
      } catch (confirmError) {
        if (isUserCancel(confirmError)) {
          ElMessage.info('已返回编辑，草稿保留')
          return
        }
        throw confirmError
      }
      response = await commitNetworkEditorDraft(machineTypeId.value, buildCommitPayload(true))
    }
    validationResult.value = response.validation || null
    draftChanges.value = []
    draftSequence.value = 0
    pendingBindingPreview.value = null
    editBaselineRevision.value = response.revision || null
    layoutDraft.value = {}
    containerDraft.value = {}
    pendingStateLayout.value = null
    resetCollapsedStateContainers()
    resetCollapsedActivityContainers()
    resetStateActivityCreationSelection()
    closeContextMenu()
    batchBindingDialogVisible.value = false
    batchBindingForm.value = { input_state_ids: [], output_state_ids: [], op_rule_id: null }
    editorMode.value = 'preview'
    ElMessage.success(`统一提交成功，已应用 ${response.applied_change_count || 0} 项变更`)
    await loadAll()
  } catch (error) {
    notifyOperationError('统一提交失败，草稿已保留', error)
  } finally {
    draftSubmitting.value = false
  }
}

async function refreshWorkspace() {
  closeContextMenu()
  if (isEditMode.value) {
    if (hasDraftChanges.value) {
      try {
        await ElMessageBox.confirm('刷新会丢弃当前未提交草稿，并回到预览模式，是否继续？', '刷新已提交数据', {
          type: 'warning',
          confirmButtonText: '丢弃草稿',
          cancelButtonText: '返回编辑',
        })
      } catch (error) {
        if (isUserCancel(error)) return
        throw error
      }
    }
    draftChanges.value = []
    draftSequence.value = 0
    pendingBindingPreview.value = null
    editBaselineRevision.value = null
    layoutDraft.value = {}
    containerDraft.value = {}
    pendingStateLayout.value = null
    resetCollapsedStateContainers()
    resetCollapsedActivityContainers()
    resetStateActivityCreationSelection()
    editorMode.value = 'preview'
  }
  await loadAll()
}

function selectedAggregateState() {
  const node = stateById.value.get(selectedStateId.value)
  if (!node) return null
  return node.state_kind === 'aggregate' || !node.feature_key ? node : null
}

function selectedLevelOneActivity() {
  const node = graphActivityById.value.get(selectedActivityGraphId.value)
  if (!node?.activity_node_id || node.level !== 1) return null
  return activityNodeById.value.get(node.activity_node_id) || null
}

function selectedLevelTwoActivity() {
  const node = graphActivityById.value.get(selectedActivityGraphId.value)
  if (!node?.activity_node_id || node.level !== 2) return null
  return activityNodeById.value.get(node.activity_node_id) || null
}

function openCreateState(parent = null, options = {}) {
  if (!requireEditMode('新建状态')) return
  stateEditId.value = null
  pendingStateLayout.value = options.layout || null
  stateForm.value = defaultStateForm(parent || selectedAggregateState())
  stateDrawerVisible.value = true
}

function openEditState(node) {
  if (!requireEditMode('编辑状态')) return
  if (!node) return
  stateEditId.value = node.id
  pendingStateLayout.value = null
  stateForm.value = {
    code: node.code || '',
    name: node.name || '',
    parent_id: node.parent_id || null,
    level: node.level,
    state_kind: node.state_kind || (node.feature_key ? 'atomic' : 'aggregate'),
    feature_key: node.feature_key || '',
    target_value: node.target_value || '',
    sort_order: node.sort_order || 0,
    is_active: node.is_active,
  }
  stateDrawerVisible.value = true
}

function isGraphStateAggregate(node) {
  return !!node && (node.state_kind === 'aggregate' || !node.feature_key)
}

function graphStateSource(node) {
  if (!node?.state_node_id) return null
  return stateById.value.get(node.state_node_id) || null
}

function openEditGraphState(node) {
  const source = graphStateSource(node)
  if (!source) return
  openEditState(source)
}

function childStateLayoutFromGraphState(node) {
  const index = visibleStateNodes.value.findIndex((item) => item.id === node.id)
  const parentPosition = nodePosition(node, Math.max(index, 0), 'state')
  return {
    x: Math.round(Math.min(Math.max(8, parentPosition.x + 28), canvasWidth - nodeWidth)),
    y: Math.round(parentPosition.y + rowHeight),
  }
}

function openCreateStateInside(node) {
  if (!isGraphStateAggregate(node)) return
  const source = graphStateSource(node)
  if (!source) return
  selectedStateId.value = source.id
  selectionFocus.value = 'state'
  openCreateState(source, { layout: childStateLayoutFromGraphState(node) })
}

function closeContextMenu() {
  contextMenu.value = null
}

function mergeStateIds(currentIds, nextIds) {
  return Array.from(new Set([
    ...normalisedNumericIds(currentIds),
    ...normalisedNumericIds(nextIds),
  ]))
}

function toggleMultiSelectedState(node) {
  const stateId = Number(node?.state_node_id)
  if (!stateId) return
  const selected = new Set(multiSelectedStateIds.value)
  if (selected.has(stateId)) {
    selected.delete(stateId)
  } else {
    selected.add(stateId)
  }
  multiSelectedStateIds.value = Array.from(selected)
}

function clearStateMultiSelection(includeStaged = false) {
  multiSelectedStateIds.value = []
  if (includeStaged) {
    stagedInputStateIds.value = []
    stagedOutputStateIds.value = []
  }
}

function stageSelectedStatesAsInput() {
  if (!requireEditMode('标记前置状态')) return
  if (!multiSelectedStateIds.value.length) return
  const selected = normalisedNumericIds(multiSelectedStateIds.value)
  const selectedSet = new Set(selected)
  stagedInputStateIds.value = mergeStateIds(stagedInputStateIds.value, selected)
  stagedOutputStateIds.value = normalisedNumericIds(stagedOutputStateIds.value).filter((id) => !selectedSet.has(id))
  ElMessage.success(`已标记 ${multiSelectedStateIds.value.length} 个前置状态`)
}

function stageSelectedStatesAsOutput() {
  if (!requireEditMode('标记产出状态')) return
  if (!multiSelectedStateIds.value.length) return
  const selected = normalisedNumericIds(multiSelectedStateIds.value)
  const selectedSet = new Set(selected)
  stagedOutputStateIds.value = mergeStateIds(stagedOutputStateIds.value, selected)
  stagedInputStateIds.value = normalisedNumericIds(stagedInputStateIds.value).filter((id) => !selectedSet.has(id))
  ElMessage.success(`已标记 ${multiSelectedStateIds.value.length} 个产出状态`)
}

function resetStateActivityCreationSelection() {
  clearStateMultiSelection(true)
}

function createVirtualActivityFromStateSelection() {
  if (!requireEditMode('从多选状态创建虚拟活动')) return
  if (!canCreateActivityFromStateSelection.value) {
    ElMessage.warning('请先把多选状态设为前置或产出')
    return
  }
  openCreateActivityNode(null, {
    contextStateIds: stagedInputStateIds.value,
    outputStateIds: stagedOutputStateIds.value,
  })
  resetStateActivityCreationSelection()
}

function createAtomicActivityFromStateSelection() {
  if (!requireEditMode('从多选状态创建原子活动')) return
  if (!canCreateActivityFromStateSelection.value) {
    ElMessage.warning('请先把多选状态设为前置或产出')
    return
  }
  openCreateAtomicActivity(null, {
    inputStateIds: stagedInputStateIds.value,
    outputStateIds: stagedOutputStateIds.value,
  })
  resetStateActivityCreationSelection()
}

function openStateContextMenu(node, event) {
  selectGraphState(node)
  const point = canvasPointFromEvent(event)
  contextMenu.value = {
    kind: 'state',
    node,
    x: Math.round(Math.min(Math.max(8, point.x), canvasWidth - 156)),
    y: Math.round(Math.max(8, point.y)),
  }
}

function openActivityContextMenu(node, event) {
  selectGraphActivity(node)
  const point = canvasPointFromEvent(event)
  contextMenu.value = {
    kind: 'activity',
    node,
    x: Math.round(Math.min(Math.max(8, point.x), canvasWidth - 156)),
    y: Math.round(Math.max(8, point.y)),
  }
}

async function focusContextState() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  selectGraphState(node)
  await focusCurrentSelection()
}

async function focusContextActivity() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  selectGraphActivity(node)
  await focusCurrentSelection()
}

async function focusContextVirtualActivity() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  await enterActivityFocus(node)
}

function editContextState() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  openEditGraphState(node)
}

function createContextChildState() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  openCreateStateInside(node)
}

function editContextActivity() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  if (node.activity_node_id) {
    const activity = activityNodeById.value.get(node.activity_node_id)
    if (activity) openEditActivityNode(activity)
    return
  }
  if (node.atomic_activity_id) {
    const atomic = atomicActivities.value.find((item) => item.id === node.atomic_activity_id)
    if (atomic) openEditAtomicActivity(atomic)
  }
}

function createContextActivityInside() {
  const node = contextMenu.value?.node
  closeContextMenu()
  if (!node) return
  openCreateActivityInside(node)
}

function onStateKindChange() {
  if (stateForm.value.state_kind === 'aggregate') {
    stateForm.value.feature_key = ''
    stateForm.value.target_value = ''
    return
  }
  if (stateForm.value.feature_key && !stateForm.value.target_value) {
    stateForm.value.target_value = defaultTargetValueForFeature(stateForm.value.feature_key)
  }
}

function onStateFeatureChange(featureKey) {
  const options = normalizeAllowedValues(stateFeatureDefByKey.value.get(featureKey)?.allowed_values)
  if (!options.length) {
    stateForm.value.target_value = ''
    return
  }
  if (!options.includes(stateForm.value.target_value)) {
    stateForm.value.target_value = defaultTargetValueForFeature(featureKey)
  }
}

function onStateParentChange(parentId) {
  const parent = stateById.value.get(parentId) || null
  stateForm.value.level = parent ? parent.level + 1 : 1
  stateForm.value.sort_order = nextSortOrder(allStateNodes.value.filter((node) => node.parent_id === (parent?.id || null)))
}

function normalizeStateText(value) {
  return String(value || '').trim().toLowerCase()
}

function stateDuplicateReasons(node, payload) {
  const reasons = []
  const code = normalizeStateText(payload.code)
  const name = normalizeStateText(payload.name)
  const featureKey = normalizeStateText(payload.feature_key)
  const targetValue = normalizeStateText(payload.target_value)
  const nodeCode = normalizeStateText(node.code)
  const nodeName = normalizeStateText(node.name)
  const nodeFeatureKey = normalizeStateText(node.feature_key)
  const nodeTargetValue = normalizeStateText(node.target_value)
  if (code && nodeCode === code) reasons.push('code')
  if (name && nodeName === name) reasons.push('name')
  if (
    payload.state_kind !== 'aggregate' &&
    featureKey &&
    targetValue &&
    nodeFeatureKey === featureKey &&
    normalizeStateText(node.operator || 'eq') === normalizeStateText(payload.operator || 'eq') &&
    nodeTargetValue === targetValue
  ) {
    reasons.push('fact')
  }
  if (!reasons.length && name && nodeName && (nodeName.includes(name) || name.includes(nodeName))) {
    reasons.push('similar_name')
  }
  return reasons
}

function findDuplicateStateCandidates(payload) {
  const parentId = payload.parent_id || null
  const descendantsOfNewParent = new Set(parentId ? stateDescendantNodeIds(parentId, { activeOnly: false }) : [])
  return stateNodes.value
    .filter((node) => node.id !== stateEditId.value && node.id !== parentId && !descendantsOfNewParent.has(node.id))
    .map((node) => {
      const reasons = stateDuplicateReasons(node, payload)
      if (!reasons.length) return null
      const score = reasons.reduce((value, reason) => {
        if (reason === 'code') return value + 100
        if (reason === 'fact') return value + 80
        if (reason === 'name') return value + 60
        return value + 10
      }, 0)
      return { ...node, duplicate_reasons: reasons, duplicate_score: score }
    })
    .filter(Boolean)
    .sort((a, b) => b.duplicate_score - a.duplicate_score || Number(a.id || 0) - Number(b.id || 0))
}

function isCertainDuplicateStateCandidate(candidate) {
  return (candidate?.duplicate_reasons || []).some((reason) =>
    ['code', 'name', 'fact'].includes(reason),
  )
}

function duplicateCandidateReasonLabel(candidate) {
  const labels = {
    code: '编码完全相同',
    name: '名称完全相同',
    fact: '原子状态特征和值完全相同',
    similar_name: '名称相似',
  }
  return (candidate.duplicate_reasons || []).map((reason) => labels[reason] || reason).join(' / ')
}

function stateHasMembership(stateId, parentId) {
  if (!stateId || !parentId) return false
  const state = stateById.value.get(stateId)
  if (state?.parent_id === parentId) return true
  if (stateReferences.value.some((ref) =>
    ref.is_active !== false &&
    ref.state_node_id === stateId &&
    ref.parent_state_node_id === parentId,
  )) {
    return true
  }
  return draftChanges.value.some((change) =>
    change.entity_type === 'state_node_reference' &&
    change.operation === 'create' &&
    Number(change.payload?.state_node_id) === Number(stateId) &&
    Number(change.payload?.parent_state_node_id) === Number(parentId),
  )
}

function queueStatePayload(payload) {
  const { machine_type_id: _stateMachineTypeId, ...stateUpdatePayload } = payload
  const editingStateId = stateEditId.value
  const clientId = queueDraftChange({
    entityType: 'state_node',
    operation: editingStateId ? 'update' : 'create',
    entityId: editingStateId || null,
    payload: editingStateId ? stateUpdatePayload : payload,
    label: `${stateEditId.value ? '更新状态' : '新建状态'}：${payload.name}`,
  })
  stateDrawerVisible.value = false
  if (editingStateId) {
    selectedStateId.value = editingStateId
    selectionFocus.value = 'state'
  } else if (clientId) {
    selectedStateId.value = draftStateId(clientId)
    selectionFocus.value = 'state'
    expandStateContainerForDraftChild(payload.parent_id)
  }
  ElMessage.success(stateEditId.value ? '状态更新已加入草稿' : '状态创建已加入草稿')
  stateEditId.value = null
  pendingStateLayout.value = null
}

function openDuplicateStateDialog(payload, candidates) {
  pendingStatePayload.value = payload
  duplicateStateCandidates.value = candidates
  duplicateStateSelectedId.value = candidates[0]?.id || null
  duplicateStateDialogVisible.value = true
}

function closeDuplicateStateDialog() {
  duplicateStateDialogVisible.value = false
}

function completeDuplicateStateDialog() {
  duplicateStateDialogVisible.value = false
  duplicateStateCandidates.value = []
  duplicateStateSelectedId.value = null
  pendingStatePayload.value = null
  pendingStateLayout.value = null
}

function activeStatePackageReferences(packageId) {
  if (!packageId) return []
  return stateReferences.value.filter((ref) =>
    ref.is_active !== false && ref.state_node_id === packageId,
  )
}

function statePackageChangeNeedsDecision(parentId) {
  const parent = stateById.value.get(parentId)
  return !!parent && !parent.feature_key && activeStatePackageReferences(parentId).length > 0
}

function sharedPackageParentMoveWarning(payload) {
  if (!stateEditId.value) return ''
  const current = stateById.value.get(stateEditId.value)
  if (!current) return ''
  const currentParentId = current.parent_id || null
  const nextParentId = payload.parent_id || null
  if (Number(currentParentId || 0) === Number(nextParentId || 0)) return ''
  if (currentParentId && statePackageChangeNeedsDecision(currentParentId)) {
    return '当前状态属于已被复用的状态包，不能在状态抽屉中直接移出。请在「状态包成员」表使用「移除引用」，并选择同步或分叉。'
  }
  if (nextParentId && statePackageChangeNeedsDecision(nextParentId)) {
    return '目标状态包已被其他状态包复用，不能在状态抽屉中直接加入。请在「状态包成员」表使用「添加」，并选择同步或分叉。'
  }
  return ''
}

function resetPackageChangeDialog() {
  packageChangeDialogVisible.value = false
  packageChangeDecision.value = 'sync'
  packageForkParentId.value = null
  packageForkName.value = ''
  packageForkReason.value = ''
  pendingPackageChange.value = null
}

function closePackageChangeDialog() {
  resetPackageChangeDialog()
}

function openPackageChangeDialog(change) {
  const source = stateById.value.get(change.sourceStateNodeId)
  const referenceParents = activeStatePackageReferences(change.sourceStateNodeId)
  pendingPackageChange.value = change
  packageChangeDecision.value = 'sync'
  packageForkParentId.value = referenceParents[0]?.parent_state_node_id || null
  packageForkName.value = `${source?.name || '状态包'} - 分支`
  packageForkReason.value = ''
  duplicateStateDialogVisible.value = false
  packageChangeDialogVisible.value = true
}

function referenceIdForStatePackageUsage(sourceStateNodeId, parentStateNodeId) {
  return stateReferences.value.find((ref) =>
    ref.is_active !== false &&
    ref.state_node_id === sourceStateNodeId &&
    ref.parent_state_node_id === parentStateNodeId,
  )?.id || null
}

function packageChangeStateLabel(change) {
  if (!change) return '-'
  if (change.mode === 'reuse') return `加入 ${nodeLabel(change.candidate)}`
  if (change.mode === 'remove_reference') {
    const state = stateById.value.get(change.row?.state_node_id)
    return `移除 ${nodeLabel(state) || change.row?.state_node_code || '#'}`
  }
  return `新建 ${[change.payload?.code, change.payload?.name].filter(Boolean).join(' ') || change.payload?.name || '-'}`
}

function clearReferenceFormIfNeeded(change) {
  if (change?.origin === 'reference_form') {
    referenceForm.value = { state_node_id: null, parent_state_node_id: null }
  }
}

function queueStateReferenceRemoval(row) {
  queueDraftChange({
    entityType: 'state_node_reference',
    operation: 'delete',
    entityId: row.id,
    label: `移除状态包成员 #${row.id}`,
  })
  ElMessage.success('状态包成员移除已加入草稿')
}

function queueStateReuseReference(candidate, payload) {
  const parentId = payload.parent_id || null
  if (!parentId) {
    selectedStateId.value = candidate.id
    selectionFocus.value = 'state'
    stateDrawerVisible.value = false
    pendingStateLayout.value = null
    ElMessage.success(`已复用已有状态：${nodeLabel(candidate)}`)
    return
  }
  if (stateHasMembership(candidate.id, parentId)) {
    selectedStateId.value = candidate.id
    selectionFocus.value = 'state'
    stateDrawerVisible.value = false
    pendingStateLayout.value = null
    ElMessage.success('该状态已在当前状态包中，无需重复加入')
    return
  }
  queueDraftChange({
    entityType: 'state_node_reference',
    operation: 'create',
    payload: {
      state_node_id: candidate.id,
      parent_state_node_id: parentId,
      sort_order: payload.sort_order || 0,
      is_active: true,
      metadata_json: {
        _network_editor_reuse: {
          source: 'duplicate_state_detection',
          requested_name: payload.name,
          matched_reasons: candidate.duplicate_reasons || [],
        },
        ...(pendingStateLayout.value ? { _network_editor_layout: pendingStateLayout.value } : {}),
      },
    },
    label: `复用状态：${nodeLabel(candidate)} → ${nodeLabel(stateById.value.get(parentId))}`,
  })
  selectedStateId.value = candidate.id
  selectionFocus.value = 'state'
  expandStateContainerForDraftChild(parentId)
  stateDrawerVisible.value = false
  pendingStateLayout.value = null
  ElMessage.success('状态复用已加入草稿')
}

function handleStateCreatePayload(payload) {
  if (!stateEditId.value && statePackageChangeNeedsDecision(payload.parent_id)) {
    openPackageChangeDialog({
      mode: 'create',
      sourceStateNodeId: payload.parent_id,
      payload,
    })
    return
  }
  queueStatePayload(payload)
}

function handleStateReuse(candidate, payload) {
  if (statePackageChangeNeedsDecision(payload.parent_id)) {
    openPackageChangeDialog({
      mode: 'reuse',
      sourceStateNodeId: payload.parent_id,
      payload,
      candidate,
    })
    return
  }
  queueStateReuseReference(candidate, payload)
  completeDuplicateStateDialog()
}

function createPendingStateDespiteDuplicate() {
  const payload = pendingStatePayload.value
  if (!payload) return
  savingState.value = true
  try {
    handleStateCreatePayload(payload)
    if (!packageChangeDialogVisible.value) completeDuplicateStateDialog()
  } catch (error) {
    notifyOperationError('加入状态草稿失败', error)
  } finally {
    savingState.value = false
  }
}

function reuseDuplicateState() {
  const payload = pendingStatePayload.value
  const candidate = duplicateStateCandidates.value.find((item) => item.id === duplicateStateSelectedId.value)
  if (!payload || !candidate) return
  savingState.value = true
  try {
    handleStateReuse(candidate, payload)
  } catch (error) {
    notifyOperationError('复用状态失败', error)
  } finally {
    savingState.value = false
  }
}

function confirmPackageChangeDecision() {
  const change = pendingPackageChange.value
  if (!change) return
  savingState.value = true
  try {
    if (packageChangeDecision.value === 'sync') {
      if (change.mode === 'remove_reference') {
        queueStateReferenceRemoval(change.row)
      } else if (change.mode === 'reuse') {
        queueStateReuseReference(change.candidate, change.payload)
      } else {
        queueStatePayload(change.payload)
      }
      clearReferenceFormIfNeeded(change)
      resetPackageChangeDialog()
      completeDuplicateStateDialog()
      return
    }

    if (!packageForkParentId.value) {
      ElMessage.warning('请选择当前使用方')
      return
    }
    if (!packageForkName.value.trim()) {
      ElMessage.warning('请填写分支名称')
      return
    }
    if (!packageForkReason.value.trim()) {
      ElMessage.warning('请填写分支说明')
      return
    }
    const source = stateById.value.get(change.sourceStateNodeId)
    const addedState = change.mode === 'remove_reference'
      ? null
      : change.mode === 'reuse'
      ? {
          mode: 'reuse',
          state_node_id: change.candidate.id,
          sort_order: change.payload.sort_order || 0,
          metadata_json: {
            source: 'duplicate_state_detection',
            requested_name: change.payload.name,
            matched_reasons: change.candidate.duplicate_reasons || [],
            ...(pendingStateLayout.value ? { _network_editor_layout: pendingStateLayout.value } : {}),
          },
        }
      : {
          mode: 'create',
          payload: {
            ...change.payload,
            parent_id: null,
            metadata_json: {
              ...(change.payload.metadata_json || {}),
              _network_editor_branch_added_state: true,
            },
          },
        }
    const forkPayload = {
      source_state_node_id: change.sourceStateNodeId,
      current_parent_state_node_id: packageForkParentId.value,
      replace_reference_id: referenceIdForStatePackageUsage(change.sourceStateNodeId, packageForkParentId.value),
      reason: packageForkReason.value.trim(),
      branch: {
        name: packageForkName.value.trim(),
        code: null,
        sort_order: source?.sort_order || 0,
        is_active: true,
      },
    }
    if (addedState) forkPayload.added_state = addedState
    if (change.mode === 'remove_reference') forkPayload.removed_state_node_id = change.row.state_node_id
    queueDraftChange({
      entityType: 'state_package_fork',
      operation: 'create',
      payload: forkPayload,
      label: `分叉状态包：${nodeLabel(source)} → ${packageForkName.value.trim()}`,
    })
    stateDrawerVisible.value = false
    clearReferenceFormIfNeeded(change)
    resetPackageChangeDialog()
    completeDuplicateStateDialog()
    ElMessage.success('状态包分叉已加入草稿')
  } catch (error) {
    notifyOperationError('加入状态包分叉草稿失败', error)
  } finally {
    savingState.value = false
  }
}

async function saveQuickState() {
  if (!requireEditMode('保存状态')) return
  const code = stateForm.value.code?.trim() || null
  const name = stateForm.value.name.trim()
  if (!name) return ElMessage.warning('请填写状态名称')
  const isAtomic = stateForm.value.state_kind !== 'aggregate'
  const featureKey = stateForm.value.feature_key.trim()
  const targetValue = stateForm.value.target_value.trim()
  if (isAtomic && !featureKey) {
    return ElMessage.warning('原子状态需要选择状态维度')
  }
  if (isAtomic && !targetValue) {
    return ElMessage.warning('原子状态需要选择目标值')
  }
  if (isAtomic && stateTargetOptions.value.length && !stateTargetOptions.value.includes(targetValue)) {
    return ElMessage.warning('目标值必须从所选状态维度的允许值中选择')
  }
  savingState.value = true
  try {
    const metadata = !stateEditId.value && pendingStateLayout.value
      ? metadataWithLayout(null, pendingStateLayout.value)
      : null
    const payload = {
      machine_type_id: machineTypeId.value,
      parent_id: stateForm.value.parent_id || null,
      level: stateForm.value.level,
      code,
      name,
      feature_key: isAtomic ? featureKey : null,
      operator: 'eq',
      target_value: isAtomic ? targetValue : null,
      state_kind: isAtomic ? 'atomic' : 'aggregate',
      sort_order: stateForm.value.sort_order,
      is_active: stateForm.value.is_active,
      metadata_json: metadata,
    }
    const parentMoveWarning = sharedPackageParentMoveWarning(payload)
    if (parentMoveWarning) {
      ElMessage.warning(parentMoveWarning)
      return
    }
    if (!stateEditId.value) {
      const duplicateCandidates = findDuplicateStateCandidates(payload)
      if (duplicateCandidates.length) {
        if (duplicateCandidates.length === 1 && isCertainDuplicateStateCandidate(duplicateCandidates[0])) {
          ElMessage.info(`已发现相同状态，将复用：${nodeLabel(duplicateCandidates[0])}`)
          handleStateReuse(duplicateCandidates[0], payload)
          return
        }
        openDuplicateStateDialog(payload, duplicateCandidates)
        return
      }
    }
    handleStateCreatePayload(payload)
  } catch (error) {
    notifyOperationError('加入状态草稿失败', error)
  } finally {
    savingState.value = false
  }
}

function canvasPointFromEvent(event) {
  const canvas = event.currentTarget?.closest?.('.canvas') || event.currentTarget
  const rect = canvas.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left + canvas.scrollLeft) / canvasZoom.value,
    y: (event.clientY - rect.top + canvas.scrollTop) / canvasZoom.value,
  }
}

function setCanvasZoom(value) {
  const clamped = Math.min(canvasZoomMax, Math.max(canvasZoomMin, Number(value) || 1))
  canvasZoom.value = Math.round(clamped * 100) / 100
}

function changeCanvasZoom(delta) {
  setCanvasZoom(canvasZoom.value + delta)
}

function resetCanvasZoom() {
  setCanvasZoom(1)
}

function handleCanvasWheel(event) {
  if (!event.ctrlKey && !event.altKey) return
  event.preventDefault()
  changeCanvasZoom(event.deltaY < 0 ? canvasZoomStep : -canvasZoomStep)
}

function statePackageAtCanvasPoint(point) {
  return statePackageContainers.value
    .filter((container) =>
      point.x >= container.left &&
      point.x <= container.left + container.width &&
      point.y >= container.top &&
      point.y <= container.top + container.height,
    )
    .sort((a, b) => (a.width * a.height) - (b.width * b.height))[0] || null
}

function newStateLayoutFromCanvasPoint(point) {
  return {
    x: Math.round(Math.min(Math.max(8, point.x - nodeWidth / 2), canvasWidth - nodeWidth)),
    y: Math.round(Math.max(8, point.y - 28)),
  }
}

function handleCanvasBlankDoubleClick(event) {
  if (!machineTypeId.value) return
  if (!requireEditMode('画布空白处新建状态')) return
  const point = canvasPointFromEvent(event)
  const container = statePackageAtCanvasPoint(point)
  const parent = container ? stateById.value.get(container.stateNodeId) : selectedAggregateState()
  if (parent) {
    selectedStateId.value = parent.id
    selectionFocus.value = 'state'
  }
  openCreateState(parent || null, { layout: newStateLayoutFromCanvasPoint(point) })
}

function handleX6SelectState(payload) {
  const node = payload?.node || payload
  if (!node) return
  selectGraphState(node, payload?.event || null)
}

function handleX6SelectActivity(payload) {
  const node = payload?.node || payload
  if (!node) return
  selectGraphActivity(node)
}

function handleX6EditActivity(node) {
  if (!node) return
  if (node.activity_node_id) {
    const activity = activityNodeById.value.get(node.activity_node_id)
    if (activity) openEditActivityNode(activity)
    return
  }
  if (node.atomic_activity_id) {
    const atomic = atomicActivities.value.find((item) => item.id === node.atomic_activity_id)
    if (atomic) openEditAtomicActivity(atomic)
  }
}

function handleX6LayoutChange(payload) {
  if (!canMutate.value || !payload?.node || !payload?.position) return
  const position = {
    x: Math.round(payload.position.x),
    y: Math.round(payload.position.y),
  }
  layoutDraft.value = {
    ...layoutDraft.value,
    [layoutKey(payload.node)]: position,
  }
  queueNodeLayoutChange(payload.node, payload.kind, position)
}

function handleX6ContainerResize(payload) {
  if (!canMutate.value || !payload?.node || !payload?.size) return
  const size = {
    width: Math.round(payload.size.width),
    height: Math.round(payload.size.height),
  }
  containerDraft.value = {
    ...containerDraft.value,
    [containerKey(payload.node)]: size,
  }
  queueContainerResizeChange(payload.node, payload.kind, size)
}

function handleX6BlankDoubleClick(payload) {
  if (!machineTypeId.value) return
  if (!requireEditMode('画布空白处新建状态')) return
  if (payload?.kind === 'activity' && payload.containerNode) {
    openCreateActivityInside(payload.containerNode)
    return
  }
  const point = {
    x: finiteNumber(payload?.x) ?? defaultStateX + nodeWidth / 2,
    y: finiteNumber(payload?.y) ?? topPadding,
  }
  const containerNode = payload?.kind === 'state' ? payload.containerNode : null
  const container = containerNode ? null : statePackageAtCanvasPoint(point)
  const parent = containerNode
    ? graphStateSource(containerNode)
    : container
      ? stateById.value.get(container.stateNodeId)
      : selectedAggregateState()
  if (parent) {
    selectedStateId.value = parent.id
    selectionFocus.value = 'state'
  }
  openCreateState(parent || null, { layout: newStateLayoutFromCanvasPoint(point) })
}

function handleStatePackageContainerDoubleClick(container, event) {
  if (!machineTypeId.value) return
  if (!requireEditMode('状态包容器内新建状态')) return
  const parent = stateById.value.get(container.stateNodeId) || null
  if (parent) {
    selectedStateId.value = parent.id
    selectionFocus.value = 'state'
  }
  const point = canvasPointFromEvent(event)
  openCreateState(parent, { layout: newStateLayoutFromCanvasPoint(point) })
}

function openCreateActivityNode(parent = null, options = {}) {
  if (!requireEditMode('新建虚拟活动')) return
  activityEditId.value = null
  const selectedParent = parent || selectedLevelOneActivity()
  const selectedParentId = selectedParent?.id || null
  activityForm.value = {
    ...defaultActivityForm(selectedParent),
    sort_order: nextSortOrder(allActivityNodes.value.filter((node) =>
      String(node.parent_id || '') === String(selectedParentId || ''),
    )),
    context_state_ids: normalisedStateIds(options.contextStateIds),
    output_state_ids: normalisedStateIds(options.outputStateIds),
  }
  if (activityForm.value.level === 2 && !activityForm.value.parent_id && activityParentOptions.value.length) {
    activityForm.value.parent_id = activityParentOptions.value[0].id
  }
  activityDrawerVisible.value = true
}

function openCreateActivityChild(node) {
  if (!requireEditMode('新建子活动')) return
  if (!node || node.resource_type === 'atomic_activity') return
  if (node.level === 1) {
    openCreateActivityNode(activityNodeById.value.get(node.id) || node)
    return
  }
  if (node.level === 2) {
    openCreateAtomicActivity(node)
    return
  }
  ElMessage.warning('旧版可执行活动不能继续添加内部活动')
}

function openCreateActivityInside(node) {
  if (!node?.activity_node_id) return
  const source = activityNodeById.value.get(node.activity_node_id)
  if (!source) return
  if (source.level === 1) {
    openCreateActivityNode(source)
    return
  }
  if (source.level === 2) {
    openCreateAtomicActivity(source)
    return
  }
  ElMessage.warning('当前活动不支持继续添加内部活动')
}

function openEditActivityNode(node) {
  if (!requireEditMode('编辑虚拟活动')) return
  if (!node) return
  activityEditId.value = node.id
  activityForm.value = {
    code: node.code || '',
    name: node.name || '',
    description: node.description || '',
    parent_id: node.parent_id || null,
    level: node.level,
    activity_category: node.activity_category || 'normal',
    sort_order: node.sort_order || 0,
    is_active: node.is_active,
  }
  activityDrawerVisible.value = true
}

function onActivityLevelChange(level) {
  if (level === 1) {
    activityForm.value.parent_id = null
    activityForm.value.sort_order = nextSortOrder(allActivityNodes.value.filter((node) => !node.parent_id))
    return
  }
  if (!activityForm.value.parent_id && activityParentOptions.value.length) {
    activityForm.value.parent_id = activityParentOptions.value[0].id
  }
  activityForm.value.sort_order = nextSortOrder(allActivityNodes.value.filter((node) =>
    String(node.parent_id || '') === String(activityForm.value.parent_id || ''),
  ))
}

async function saveQuickActivityNode() {
  if (!requireEditMode('保存虚拟活动')) return
  const code = activityForm.value.code?.trim() || null
  const name = activityForm.value.name.trim()
  const description = activityForm.value.description?.trim() || null
  if (!name) return ElMessage.warning('请填写活动名称')
  if (activityForm.value.level === 2 && !activityForm.value.parent_id) {
    return ElMessage.warning('二级虚拟活动需要所属一级活动')
  }
  savingActivity.value = true
  try {
    const payload = {
      machine_type_id: machineTypeId.value,
      parent_id: activityForm.value.level === 1 ? null : activityForm.value.parent_id,
      level: activityForm.value.level,
      code,
      name,
      description,
      activity_category: activityForm.value.activity_category,
      sort_order: activityForm.value.sort_order,
      is_active: activityForm.value.is_active,
      metadata_json: null,
    }
    const { machine_type_id: _activityMachineTypeId, ...activityUpdatePayload } = payload
    const activityDraftId = queueDraftChange({
      entityType: 'activity_node',
      operation: activityEditId.value ? 'update' : 'create',
      entityId: activityEditId.value || null,
      payload: activityEditId.value ? activityUpdatePayload : payload,
      label: `${activityEditId.value ? '更新虚拟活动' : '新建虚拟活动'}：${name}`,
    })
    if (!activityEditId.value && activityDraftId) {
      const boundaryBindings = [
        ...(activityForm.value.context_state_ids || []).map((stateNodeId) => ({
          stateNodeId,
          role: 'context_input',
        })),
        ...(activityForm.value.output_state_ids || []).map((stateNodeId) => ({
          stateNodeId,
          role: 'declared_output',
        })),
      ]
      for (const item of boundaryBindings) {
        queueDraftChange({
          entityType: 'activity_state_binding',
          operation: 'create',
          payload: {
            machine_type_id: machineTypeId.value,
            activity_node_id: { _draft_ref: activityDraftId },
            state_node_id: item.stateNodeId,
            binding_role: item.role,
            is_active: true,
          },
          label: `新虚拟活动绑定：${item.role} / ${nodeLabel(stateById.value.get(item.stateNodeId))}`,
        })
      }
      expandActivityContainerForDraftChild(payload.parent_id)
    }
    activityDrawerVisible.value = false
    if (activityEditId.value) {
      selectedActivityGraphId.value = `activity_node:${activityEditId.value}`
      selectionFocus.value = 'activity'
      bindingForm.value.activity_graph_id = selectedActivityGraphId.value
    } else if (activityDraftId) {
      selectedActivityGraphId.value = `activity_node:${draftActivityId(activityDraftId)}`
      selectionFocus.value = 'activity'
      bindingForm.value.activity_graph_id = selectedActivityGraphId.value
    }
    onBindingActivityChange()
    ElMessage.success(activityEditId.value ? '虚拟活动更新已加入草稿' : '虚拟活动创建已加入草稿')
    activityEditId.value = null
  } catch (error) {
      notifyOperationError('加入虚拟活动草稿失败', error)
  } finally {
    savingActivity.value = false
  }
}

function openCreateAtomicActivity(packageNode = null, options = {}) {
  if (!requireEditMode('新建原子活动')) return
  atomicEditId.value = null
  const packageId = typeof packageNode === 'object' ? packageNode?.id : packageNode
  atomicForm.value = {
    ...defaultAtomicForm(packageId || selectedLevelTwoActivity()?.id || null),
    input_state_ids: normalisedStateIds(options.inputStateIds),
    output_state_ids: normalisedStateIds(options.outputStateIds),
  }
  onAtomicOutputStatesChange()
  atomicDrawerVisible.value = true
}

function openEditAtomicActivity(activity) {
  if (!requireEditMode('编辑原子活动')) return
  if (!activity) return
  const packageId = selectedGraphActivity.value?.parent_activity_node_ids?.[0] || null
  atomicEditId.value = activity.id
  atomicForm.value = {
    code: activity.code || '',
    name: activity.name || '',
    description: activity.description || '',
    package_id: packageId,
    activity_category: activity.activity_category || 'normal',
    sort_order: activity.sort_order || 0,
    is_active: activity.is_active,
  }
  atomicDrawerVisible.value = true
}

function focusedSelectionKind() {
  if (selectionFocus.value === 'state' && selectedStateId.value) return 'state'
  if (selectionFocus.value === 'activity' && selectedGraphActivity.value) return 'activity'
  if (selectedGraphActivity.value) return 'activity'
  if (selectedStateId.value) return 'state'
  return ''
}

function editSelected() {
  const kind = focusedSelectionKind()
  if (kind === 'state') {
    openEditState(stateById.value.get(selectedStateId.value))
    return
  }
  if (kind === 'activity') {
    const graphActivity = selectedGraphActivity.value
    if (graphActivity?.atomic_activity_id) {
      openEditAtomicActivity(atomicActivities.value.find((item) => item.id === graphActivity.atomic_activity_id))
    } else if (graphActivity?.activity_node_id) {
      openEditActivityNode(activityNodeById.value.get(graphActivity.activity_node_id))
    }
  }
}

async function deleteSelected() {
  if (!requireEditMode('删除节点')) return
  const kind = focusedSelectionKind()
  if (!kind) return
  const actionLabel = selectedDeleteActionLabel.value
  const confirmText = selectedDeleteConfirmText.value
  try {
    await ElMessageBox.confirm(confirmText, actionLabel, {
      type: 'warning',
      confirmButtonText: actionLabel,
      cancelButtonText: '取消',
    })
    if (kind === 'state') {
      queueDraftChange({
        entityType: 'state_node',
        operation: 'delete',
        entityId: selectedStateId.value,
        label: `删除状态：${selectedStateLabel.value}`,
      })
      selectedStateId.value = null
    } else {
      const graphActivity = selectedGraphActivity.value
      if (graphActivity?.atomic_activity_id) {
        queueDraftChange({
          entityType: 'atomic_activity',
          operation: 'delete',
          entityId: graphActivity.atomic_activity_id,
          label: `删除原子活动：${selectedActivityLabel.value}`,
        })
      } else if (graphActivity?.activity_node_id) {
        queueDraftChange({
          entityType: 'activity_node',
          operation: 'delete',
          entityId: graphActivity.activity_node_id,
          label: `删除虚拟活动：${selectedActivityLabel.value}`,
        })
      }
      selectedActivityGraphId.value = null
    }
    selectedBinding.value = null
    selectionFocus.value = ''
    ElMessage.success(`${actionLabel}已加入草稿`)
  } catch (error) {
    if (!isUserCancel(error)) notifyOperationError('删除失败', error)
  }
}

async function saveQuickAtomicActivity() {
  if (!requireEditMode('保存原子活动')) return
  const code = atomicForm.value.code?.trim() || null
  const name = atomicForm.value.name.trim()
  const description = atomicForm.value.description?.trim() || null
  if (!name) return ElMessage.warning('请填写原子活动名称')
  sanitizeAtomicOutputCoverages()
  if (!atomicOutputCoverageSelectionValid.value) {
    return ElMessage.warning('请选择产出状态包的覆盖成员，或切换为全部当前成员')
  }
  const selectedInputStateIds = normalisedStateIds(atomicForm.value.input_state_ids)
  const selectedOutputStateIds = normalisedStateIds(atomicForm.value.output_state_ids)
  const selectedOutputEffectStateIds = selectedOutputStateIds.flatMap((stateNodeId) =>
    atomicOutputCoveredLeafStateIds(stateNodeId) || [stateNodeId],
  )
  const shouldAutoWire = !atomicEditId.value && (!!selectedInputStateIds.length || !!selectedOutputStateIds.length)
  const preconditions = shouldAutoWire ? rulePreconditionsForStateIds(selectedInputStateIds) : []
  const effects = shouldAutoWire ? ruleEffectsForStateIds(selectedOutputEffectStateIds) : []
  const shouldCreateRule = shouldAutoWire && effects.length > 0
  const pendingRuleReason = shouldAutoWire && !shouldCreateRule
    ? '产出状态缺少可生成规则效果的原子状态事实'
    : ''
  savingAtomic.value = true
  try {
    const payload = {
      machine_type_id: machineTypeId.value,
      code,
      name,
      description,
      activity_category: atomicForm.value.activity_category,
      sort_order: atomicForm.value.sort_order,
      is_active: atomicForm.value.is_active,
      metadata_json: pendingRuleReason
        ? { _network_editor_pending_rule: { reason: pendingRuleReason } }
        : null,
    }
    const { machine_type_id: _atomicMachineTypeId, ...atomicUpdatePayload } = payload
    if (!atomicEditId.value && atomicForm.value.package_id) {
      payload.package_id = atomicForm.value.package_id
    }
    const atomicDraftId = queueDraftChange({
      entityType: 'atomic_activity',
      operation: atomicEditId.value ? 'update' : 'create',
      entityId: atomicEditId.value || null,
      payload: atomicEditId.value ? atomicUpdatePayload : payload,
      label: `${atomicEditId.value ? '更新原子活动' : '新建原子活动'}：${name}`,
    })
    if (shouldAutoWire && atomicDraftId) {
      const ruleDraftId = shouldCreateRule
        ? queueDraftChange({
          entityType: 'op_rule',
          operation: 'create',
          payload: {
            machine_type_id: machineTypeId.value,
            atomic_activity_id: { _draft_ref: atomicDraftId },
            code: null,
            name,
            duration_min: atomicForm.value.duration_min || 30,
            description,
            is_active: atomicForm.value.is_active,
            is_repair: atomicForm.value.activity_category === 'repair',
            preconditions,
            effects,
            resource_reqs: [],
          },
          label: `新建原子活动规则：${name}`,
        })
        : null
      const boundaryBindings = [
        ...selectedInputStateIds.map((stateNodeId) => ({ stateNodeId, role: 'input' })),
        ...selectedOutputStateIds.map((stateNodeId) => ({
          stateNodeId,
          role: 'output',
          coveredLeafStateIds: atomicOutputCoveredLeafStateIds(stateNodeId),
        })),
      ]
      for (const item of boundaryBindings) {
        const bindingPayload = {
          machine_type_id: machineTypeId.value,
          atomic_activity_id: { _draft_ref: atomicDraftId },
          state_node_id: item.stateNodeId,
          binding_role: item.role,
          is_active: true,
        }
        if (ruleDraftId) {
          bindingPayload.op_rule_id = { _draft_ref: ruleDraftId }
        }
        if (Array.isArray(item.coveredLeafStateIds)) {
          bindingPayload.covered_leaf_state_ids = item.coveredLeafStateIds
        }
        queueDraftChange({
          entityType: 'activity_state_binding',
          operation: 'create',
          payload: bindingPayload,
          label: `新原子活动绑定：${item.role} / ${nodeLabel(stateById.value.get(item.stateNodeId))}`,
        })
      }
    }
    if (!atomicEditId.value && atomicDraftId) {
      expandActivityContainerForDraftChild(payload.package_id)
    }
    atomicDrawerVisible.value = false
    if (atomicEditId.value) {
      selectedActivityGraphId.value = `atomic_activity:${atomicEditId.value}`
      selectionFocus.value = 'activity'
    } else if (atomicDraftId) {
      selectedActivityGraphId.value = `atomic_activity:${draftAtomicActivityId(atomicDraftId)}`
      selectionFocus.value = 'activity'
    }
    bindingForm.value.activity_graph_id = selectedActivityGraphId.value
    onBindingActivityChange()
    ElMessage.success(pendingRuleReason
      ? '原子活动已按待补规则加入草稿，提交后需补齐规则才能求解'
      : atomicEditId.value ? '原子活动更新已加入草稿' : '原子活动创建已加入草稿')
    atomicEditId.value = null
  } catch (error) {
    notifyOperationError('加入原子活动草稿失败', error)
  } finally {
    savingAtomic.value = false
  }
}

function nodeTop(index) {
  return topPadding + index * rowHeight
}

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function layoutKey(node) {
  return node?.id || ''
}

function metadataLayout(node) {
  const layout = node?.metadata_json?._network_editor_layout
  if (!layout || typeof layout !== 'object') return null
  const x = finiteNumber(layout.x)
  const y = finiteNumber(layout.y)
  if (x === null || y === null) return null
  return { x, y }
}

function containerKey(node) {
  return `${layoutKey(node)}:container`
}

function metadataContainer(node) {
  const container = node?.metadata_json?._network_editor_container
  if (!container || typeof container !== 'object') return null
  const width = finiteNumber(container.width)
  const height = finiteNumber(container.height)
  if (width === null || height === null) return null
  return { width, height }
}

function containerDimensions(node, baseWidth, baseHeight) {
  const draft = containerDraft.value[containerKey(node)]
  const saved = metadataContainer(node)
  const size = draft || saved || {}
  return {
    width: Math.max(baseWidth, Number(size.width || 0)),
    height: Math.max(baseHeight, Number(size.height || 0)),
  }
}

function defaultNodePosition(index, kind) {
  return {
    x: kind === 'state' ? defaultStateX : defaultActivityX,
    y: nodeTop(index),
  }
}

function nodePosition(node, index = 0, kind = 'state') {
  const draft = layoutDraft.value[layoutKey(node)]
  if (draft) return draft
  return metadataLayout(node) || defaultNodePosition(index, kind)
}

function nodeStyle(node, index, kind) {
  const pos = nodePosition(node, index, kind)
  return {
    left: `${pos.x}px`,
    top: `${pos.y}px`,
  }
}

function metadataWithLayout(metadata, pos) {
  return {
    ...(metadata || {}),
    _network_editor_layout: {
      x: Math.round(pos.x),
      y: Math.round(pos.y),
    },
  }
}

function nodeWithDraftLayout(node) {
  const draft = layoutDraft.value[layoutKey(node)]
  if (!draft) return node
  return {
    ...node,
    metadata_json: metadataWithLayout(node.metadata_json, draft),
  }
}

function metadataWithContainer(metadata, size) {
  return {
    ...(metadata || {}),
    _network_editor_container: {
      width: Math.round(size.width),
      height: Math.round(size.height),
    },
  }
}

function layoutUpdateForNode(node, pos, kind) {
  if (kind === 'state') {
    if (node.is_draft) return null
    if (node.reference_id) {
      const ref = stateReferences.value.find((item) => item.id === node.reference_id)
      if (!ref) return null
      return {
        entityType: 'state_node_reference',
        entityId: ref.id,
        label: `调整状态引用位置：${nodeLabel(stateById.value.get(ref.state_node_id))}`,
        payload: {
          sort_order: ref.sort_order || 0,
          is_active: ref.is_active,
          metadata_json: metadataWithLayout(ref.metadata_json, pos),
        },
      }
    }
    const source = stateById.value.get(node.state_node_id)
    if (!source) return null
    return {
      entityType: 'state_node',
      entityId: source.id,
      label: `调整状态位置：${nodeLabel(source)}`,
      payload: {
        parent_id: source.parent_id || null,
        level: source.level,
        code: source.code || null,
        name: source.name,
        feature_key: source.feature_key || null,
        operator: source.operator || 'eq',
        target_value: source.target_value || null,
        state_kind: source.state_kind || (source.feature_key ? 'atomic' : 'aggregate'),
        sort_order: source.sort_order || 0,
        is_active: source.is_active,
        metadata_json: metadataWithLayout(source.metadata_json, pos),
      },
    }
  }

  if (node.activity_node_id) {
    if (node.is_draft) return null
    const source = activityNodeById.value.get(node.activity_node_id)
    if (!source) return null
    return {
      entityType: 'activity_node',
      entityId: source.id,
      label: `调整虚拟活动位置：${nodeLabel(source)}`,
      payload: {
        parent_id: source.parent_id || null,
        level: source.level,
        code: source.code || null,
        name: source.name,
        activity_category: source.activity_category || 'normal',
        sort_order: source.sort_order || 0,
        is_active: source.is_active,
        metadata_json: metadataWithLayout(source.metadata_json, pos),
      },
    }
  }

  if (node.atomic_activity_id) {
    const source = atomicActivities.value.find((item) => item.id === node.atomic_activity_id)
    if (!source) return null
    return {
      entityType: 'atomic_activity',
      entityId: source.id,
      label: `调整原子活动位置：${nodeLabel(source)}`,
      payload: {
        code: source.code || null,
        name: source.name,
        activity_category: source.activity_category || 'normal',
        sort_order: source.sort_order || 0,
        is_active: source.is_active,
        metadata_json: metadataWithLayout(source.metadata_json, pos),
      },
    }
  }
  return null
}

function containerUpdateForNode(node, size, kind) {
  if (kind === 'state') {
    if (node.is_draft) return null
    if (node.reference_id) {
      const ref = stateReferences.value.find((item) => item.id === node.reference_id)
      if (!ref) return null
      return {
        entityType: 'state_node_reference',
        entityId: ref.id,
        label: `调整状态包引用容器尺寸：${nodeLabel(stateById.value.get(ref.state_node_id))}`,
        payload: {
          sort_order: ref.sort_order || 0,
          is_active: ref.is_active,
          metadata_json: metadataWithContainer(ref.metadata_json, size),
        },
      }
    }
    const source = stateById.value.get(node.state_node_id)
    if (!source) return null
    return {
      entityType: 'state_node',
      entityId: source.id,
      label: `调整状态包容器尺寸：${nodeLabel(source)}`,
      payload: {
        parent_id: source.parent_id || null,
        level: source.level,
        code: source.code || null,
        name: source.name,
        feature_key: source.feature_key || null,
        operator: source.operator || 'eq',
        target_value: source.target_value || null,
        state_kind: source.state_kind || (source.feature_key ? 'atomic' : 'aggregate'),
        sort_order: source.sort_order || 0,
        is_active: source.is_active,
        metadata_json: metadataWithContainer(source.metadata_json, size),
      },
    }
  }

  if (node.activity_node_id) {
    if (node.is_draft) return null
    const source = activityNodeById.value.get(node.activity_node_id)
    if (!source) return null
    return {
      entityType: 'activity_node',
      entityId: source.id,
      label: `调整虚拟活动容器尺寸：${nodeLabel(source)}`,
      payload: {
        parent_id: source.parent_id || null,
        level: source.level,
        code: source.code || null,
        name: source.name,
        activity_category: source.activity_category || 'normal',
        sort_order: source.sort_order || 0,
        is_active: source.is_active,
        metadata_json: metadataWithContainer(source.metadata_json, size),
      },
    }
  }
  return null
}

function queueNodeLayoutChange(node, kind, pos) {
  const update = layoutUpdateForNode(node, pos, kind)
  if (!update) {
    if (kind === 'activity' && updateDraftActivityLayout(node, pos)) {
      ElMessage.success('布局调整已加入草稿')
      return
    }
    if (kind === 'state' && updateDraftStateLayout(node, pos)) {
      ElMessage.success('甯冨眬璋冩暣宸插姞鍏ヨ崏绋?')
      return
    }
    ElMessage.warning('当前节点暂不能保存布局')
    return
  }
  upsertDraftUpdate(update)
  ElMessage.success('布局调整已加入草稿')
}

function containerNodeForResize(container, kind) {
  if (kind === 'state') {
    return visibleStateNodes.value.find((node) => node.id === container.graphId) ||
      visibleStateNodes.value.find((node) => String(node.state_node_id || '') === String(container.stateNodeId || '')) ||
      null
  }
  return visibleActivityNodes.value.find((node) =>
    String(node.activity_node_id || '') === String(container.activityNodeId || ''),
  ) || null
}

function containerMemberNodes(container, kind) {
  if (kind === 'state') {
    return visibleStateNodes.value.filter((node) =>
      node.id === container.graphId ||
      (
        node.id !== container.graphId &&
        node.state_node_id !== container.stateNodeId &&
        statePathContains(node, container.stateNodeId)
      ),
    )
  }
  return visibleActivityNodes.value.filter((node) =>
    node.id === container.id ||
    (
      node.id !== container.id &&
      activityPathContains(node, container.activityNodeId)
    ),
  )
}

function containerMoveStartPositions(container, kind) {
  const source = kind === 'state' ? visibleStateNodes.value : visibleActivityNodes.value
  return containerMemberNodes(container, kind)
    .map((node) => {
      const index = source.findIndex((item) => item.id === node.id)
      const pos = nodePosition(node, Math.max(index, 0), kind)
      return { node, x: pos.x, y: pos.y }
    })
    .filter((item) => item.node)
}

function clampContainerMoveDelta(members, dx, dy) {
  if (!members.length) return { dx: 0, dy: 0 }
  const minX = Math.min(...members.map((item) => item.x))
  const maxX = Math.max(...members.map((item) => item.x))
  const minY = Math.min(...members.map((item) => item.y))
  return {
    dx: Math.min(Math.max(dx, -minX), canvasWidth - nodeWidth - maxX),
    dy: Math.max(dy, 8 - minY),
  }
}

function startContainerMove(container, kind, event) {
  if (!requireEditMode('移动容器')) return
  const rootNode = containerNodeForResize(container, kind)
  if (!rootNode) {
    ElMessage.warning('当前容器暂不能移动')
    return
  }
  const members = containerMoveStartPositions(container, kind)
  if (!members.length) {
    ElMessage.warning('当前容器没有可移动节点')
    return
  }
  if (kind === 'state') {
    selectGraphState(rootNode)
  } else {
    selectGraphActivity(rootNode)
  }
  containerMove.value = {
    container,
    kind,
    members,
    dx: 0,
    dy: 0,
    pointerX: event.clientX,
    pointerY: event.clientY,
  }
  window.addEventListener('pointermove', onContainerMoveMove)
  window.addEventListener('pointerup', endContainerMove)
}

function onContainerMoveMove(event) {
  const move = containerMove.value
  if (!move) return
  const rawDx = (event.clientX - move.pointerX) / canvasZoom.value
  const rawDy = (event.clientY - move.pointerY) / canvasZoom.value
  const { dx, dy } = clampContainerMoveDelta(move.members, rawDx, rawDy)
  move.dx = dx
  move.dy = dy
  const nextLayout = { ...layoutDraft.value }
  for (const member of move.members) {
    nextLayout[layoutKey(member.node)] = {
      x: member.x + dx,
      y: member.y + dy,
    }
  }
  layoutDraft.value = nextLayout
}

function endContainerMove() {
  const move = containerMove.value
  window.removeEventListener('pointermove', onContainerMoveMove)
  window.removeEventListener('pointerup', endContainerMove)
  if (!move) return
  containerMove.value = null
  if (Math.abs(move.dx) < 0.5 && Math.abs(move.dy) < 0.5) return
  let changedCount = 0
  for (const member of move.members) {
    const pos = layoutDraft.value[layoutKey(member.node)] || {
      x: member.x + move.dx,
      y: member.y + move.dy,
    }
    const update = layoutUpdateForNode(member.node, pos, move.kind)
    if (update) {
      upsertDraftUpdate(update)
      changedCount += 1
    }
  }
  if (changedCount) {
    ElMessage.success(`容器移动已加入草稿：${changedCount} 个节点`)
  } else {
    ElMessage.warning('当前容器移动暂不能保存')
  }
}

function queueContainerResizeChange(node, kind, size) {
  const update = containerUpdateForNode(node, size, kind)
  if (!update) {
    ElMessage.warning('当前容器暂不能保存尺寸')
    return
  }
  upsertDraftUpdate(update)
  ElMessage.success('容器尺寸调整已加入草稿')
}

function autoArrangePosition(index, node, kind) {
  const level = Math.max(1, Number(node.level || 1))
  const y = topPadding + index * rowHeight
  if (kind === 'state') {
    return {
      x: Math.min(defaultStateX + (level - 1) * 30, 300),
      y,
    }
  }
  return {
    x: Math.min(420 + (level - 1) * 58, canvasWidth - nodeWidth),
    y,
  }
}

function autoArrangeCanvas() {
  if (!requireEditMode('自动整理画布')) return
  const nextLayout = { ...layoutDraft.value }
  let changedCount = 0
  const arrange = (nodes, kind) => {
    nodes.forEach((node, index) => {
      const pos = autoArrangePosition(index, node, kind)
      nextLayout[layoutKey(node)] = pos
      const update = layoutUpdateForNode(node, pos, kind)
      if (update) {
        upsertDraftUpdate(update)
        changedCount += 1
      }
    })
  }
  arrange(visibleStateNodes.value, 'state')
  arrange(visibleActivityNodes.value, 'activity')
  layoutDraft.value = nextLayout
  if (changedCount) {
    ElMessage.success(`自动整理已加入草稿：${changedCount} 个节点`)
  } else {
    ElMessage.info('当前没有可整理节点')
  }
}

function startContainerResize(container, kind, event) {
  if (!requireEditMode('调整容器尺寸')) return
  const node = containerNodeForResize(container, kind)
  if (!node) {
    ElMessage.warning('当前容器暂不能调整尺寸')
    return
  }
  if (kind === 'state') {
    selectGraphState(node)
  } else {
    selectGraphActivity(node)
  }
  containerResize.value = {
    node,
    kind,
    startWidth: container.width,
    startHeight: container.height,
    pointerX: event.clientX,
    pointerY: event.clientY,
  }
  window.addEventListener('pointermove', onContainerResizeMove)
  window.addEventListener('pointerup', endContainerResize)
}

function onContainerResizeMove(event) {
  const resize = containerResize.value
  if (!resize) return
  const width = Math.max(246, resize.startWidth + (event.clientX - resize.pointerX) / canvasZoom.value)
  const height = Math.max(78, resize.startHeight + (event.clientY - resize.pointerY) / canvasZoom.value)
  containerDraft.value = {
    ...containerDraft.value,
    [containerKey(resize.node)]: { width, height },
  }
}

function endContainerResize() {
  const resize = containerResize.value
  window.removeEventListener('pointermove', onContainerResizeMove)
  window.removeEventListener('pointerup', endContainerResize)
  if (!resize) return
  const size = containerDraft.value[containerKey(resize.node)] || {
    width: resize.startWidth,
    height: resize.startHeight,
  }
  containerResize.value = null
  queueContainerResizeChange(resize.node, resize.kind, size)
}

function nodeBounds(nodes, kind) {
  const positions = nodes.map((node) => {
    const source = kind === 'state' ? visibleStateNodes.value : visibleActivityNodes.value
    const index = source.findIndex((item) => item.id === node.id)
    return nodePosition(node, Math.max(index, 0), kind)
  })
  if (!positions.length) {
    const fallback = defaultNodePosition(0, kind)
    return { left: fallback.x, right: fallback.x + nodeWidth, top: fallback.y, bottom: fallback.y + 56 }
  }
  const left = Math.min(...positions.map((pos) => pos.x))
  const right = Math.max(...positions.map((pos) => pos.x + nodeWidth))
  const top = Math.min(...positions.map((pos) => pos.y))
  const bottom = Math.max(...positions.map((pos) => pos.y + 56))
  return { left, right, top, bottom }
}

function buildRenderedEdges(edges) {
  const groups = new Map()
  for (const edge of edges) {
    const key = edge.type === 'STATE_TO_ACTIVITY'
      ? `input:${edge.target_id}`
      : `output:${edge.source_id}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        type: edge.type,
        activityId: edge.type === 'STATE_TO_ACTIVITY' ? edge.target_id : edge.source_id,
        stateIds: new Set(),
        edges: [],
      })
    }
    const group = groups.get(key)
    group.edges.push(edge)
    group.stateIds.add(edge.type === 'STATE_TO_ACTIVITY' ? edge.source_id : edge.target_id)
  }

  const rendered = []
  for (const group of groups.values()) {
    if (group.edges.length > edgeSummaryThreshold && !shouldExpandEdgeGroup(group)) {
      rendered.push({
        ...group.edges[0],
        id: `aggregate:${group.key}`,
        aggregate: true,
        aggregateCount: group.edges.length,
        aggregateEdges: group.edges,
        aggregateStateIds: Array.from(group.stateIds),
        aggregateActivityId: group.activityId,
        aggregateLabel: group.type === 'STATE_TO_ACTIVITY'
          ? `${group.edges.length} 个输入`
          : `${group.edges.length} 个输出`,
      })
      continue
    }

    const offsets = laneOffsets(group.edges.length)
    group.edges.forEach((edge, index) => {
      rendered.push({
        ...edge,
        renderLaneOffset: offsets[index],
      })
    })
  }
  return rendered
}

function shouldExpandEdgeGroup(group) {
  if (selectedActivityGraphId.value === group.activityId) return true
  if (selectedStateId.value && Array.from(group.stateIds).some((graphId) =>
    String(graphId).startsWith('state_node:') && graphIdNumber(graphId) === Number(selectedStateId.value),
  )) return true
  return group.edges.some((edge) => isImpactEdge(edge))
}

function laneOffsets(count) {
  if (count <= 1) return [0]
  const center = (count - 1) / 2
  return Array.from({ length: count }, (_, index) => Math.round((index - center) * edgeLaneGap))
}

function graphNodeAnchor(graphId, kind, side, yOffset = 0) {
  const source = kind === 'state' ? visibleStateNodes.value : visibleActivityNodes.value
  const index = source.findIndex((node) => node.id === graphId)
  const node = source[Math.max(index, 0)]
  const pos = nodePosition(node, Math.max(index, 0), kind)
  const x = side === 'right' ? pos.x + nodeWidth - 8 : pos.x + 8
  return { x, y: pos.y + 28 + yOffset }
}

function aggregateStateAnchor(stateGraphIds, side) {
  const anchors = stateGraphIds
    .map((graphId) => graphNodeAnchor(graphId, 'state', side))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
  if (!anchors.length) return graphNodeAnchor(null, 'state', side)
  return {
    x: Math.round(anchors.reduce((sum, point) => sum + point.x, 0) / anchors.length),
    y: Math.round(anchors.reduce((sum, point) => sum + point.y, 0) / anchors.length),
  }
}

function edgePoint(edge) {
  if (edge.aggregate) {
    const activity = graphNodeAnchor(edge.aggregateActivityId, 'activity', edge.type === 'STATE_TO_ACTIVITY' ? 'left' : 'right')
    const states = aggregateStateAnchor(edge.aggregateStateIds || [], edge.type === 'STATE_TO_ACTIVITY' ? 'right' : 'left')
    if (edge.type === 'STATE_TO_ACTIVITY') {
      return { x1: states.x, y1: states.y, x2: activity.x, y2: activity.y }
    }
    return { x1: activity.x, y1: activity.y, x2: states.x, y2: states.y }
  }
  const stateIndex = visibleStateNodes.value.findIndex((node) =>
    edge.source_id === node.id || edge.target_id === node.id,
  )
  const activityIndex = visibleActivityNodes.value.findIndex((node) =>
    edge.source_id === node.id || edge.target_id === node.id,
  )
  const stateNode = visibleStateNodes.value[Math.max(stateIndex, 0)]
  const activityNode = visibleActivityNodes.value[Math.max(activityIndex, 0)]
  const statePos = nodePosition(stateNode, Math.max(stateIndex, 0), 'state')
  const activityPos = nodePosition(activityNode, Math.max(activityIndex, 0), 'activity')
  const laneOffset = Number(edge.renderLaneOffset || 0)
  const stateY = statePos.y + 28 + laneOffset
  const activityY = activityPos.y + 28 + laneOffset
  if (edge.type === 'STATE_TO_ACTIVITY') {
    return { x1: statePos.x + nodeWidth - 8, y1: stateY, x2: activityPos.x + 8, y2: activityY }
  }
  return { x1: activityPos.x + nodeWidth - 8, y1: activityY, x2: statePos.x + 8, y2: stateY }
}

function edgePath(edge) {
  const point = edgePoint(edge)
  const direction = point.x2 >= point.x1 ? 1 : -1
  const curve = Math.max(72, Math.abs(point.x2 - point.x1) * 0.32)
  const cp1x = point.x1 + direction * curve
  const cp2x = point.x2 - direction * curve
  return `M ${point.x1} ${point.y1} C ${cp1x} ${point.y1}, ${cp2x} ${point.y2}, ${point.x2} ${point.y2}`
}

function edgeLabelPoint(edge) {
  const point = edgePoint(edge)
  return {
    x: Math.round((point.x1 + point.x2) / 2),
    y: Math.round((point.y1 + point.y2) / 2 - 6),
  }
}

function edgeBinding(edge) {
  if (!edge?.binding_id) return null
  return bindingById.value.get(Number(edge.binding_id)) || null
}

function edgeBindingActivity(edge, binding = null) {
  if (edge?.source_id?.startsWith('activity_node:') || edge?.source_id?.startsWith('atomic_activity:')) {
    return graphActivityById.value.get(edge.source_id) || null
  }
  if (edge?.target_id?.startsWith('activity_node:') || edge?.target_id?.startsWith('atomic_activity:')) {
    return graphActivityById.value.get(edge.target_id) || null
  }
  if (binding?.atomic_activity_id) {
    return graphActivityById.value.get(`atomic_activity:${binding.atomic_activity_id}`) || { level: 3 }
  }
  if (binding?.activity_node_id) {
    const activity = activityNodeById.value.get(binding.activity_node_id)
    return activity ? { ...activity, level: activity.level || 0 } : null
  }
  return null
}

function isCrossLevelEdge(edge, binding = null) {
  const stateId = graphIdNumber(edge?.source_id?.startsWith('state_node:') ? edge.source_id : edge?.target_id)
  const state = stateId ? stateById.value.get(Number(stateId)) : null
  const activity = edgeBindingActivity(edge, binding)
  return !!state && !!activity && Number(state.level) !== Number(activity.level)
}

function edgeSemanticLabel(edge) {
  const binding = edgeBinding(edge)
  const roleLabel = bindingRoleText(edge?.binding_role || binding?.binding_role)
  let label = roleLabel
  if (binding?.binding_type === 'state_package') {
    label = {
      context_input: '状态包上下文',
      declared_output: '状态包声明输出',
      input: '状态包输入',
      output: '状态包产出',
    }[binding.binding_role] || `状态包${roleLabel}`
  }
  if (isCrossLevelEdge(edge, binding)) {
    label = `${label} / 跨层级`
  }
  return label || edge?.type || '-'
}

function edgeDisplayLabel(edge) {
  if (edge.aggregate) return edge.aggregateLabel
  if (edge.is_draft || edge.is_pending) return edgeSemanticLabel(edge)
  const binding = edgeBinding(edge)
  if (binding?.binding_type === 'state_package' || isCrossLevelEdge(edge, binding)) {
    return edgeSemanticLabel(edge)
  }
  return ''
}

function edgeTitle(edge) {
  if (edge.aggregate) return `${edge.aggregateLabel}，选中相关状态或活动后展开具体连线`
  return edgeSemanticLabel(edge)
}

function expandAggregateEdge(edge) {
  if (!edge?.aggregate || !edge.aggregateActivityId) return
  const node = graphActivityById.value.get(edge.aggregateActivityId)
  if (node) {
    selectGraphActivity(node)
  }
}

function setDragData(event, payload) {
  if (!event?.dataTransfer) return
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('application/json', JSON.stringify(payload))
  event.dataTransfer.setData('text/plain', payload.graphId)
}

function startLayoutDrag(node, index, kind, event) {
  if (!requireEditMode('调整节点位置')) return
  const start = nodePosition(node, index, kind)
  layoutDrag.value = {
    node,
    kind,
    startX: start.x,
    startY: start.y,
    pointerX: event.clientX,
    pointerY: event.clientY,
  }
  if (kind === 'state') {
    selectGraphState(node)
  } else {
    selectGraphActivity(node)
  }
  window.addEventListener('pointermove', onLayoutPointerMove)
  window.addEventListener('pointerup', endLayoutDrag)
}

function onLayoutPointerMove(event) {
  const drag = layoutDrag.value
  if (!drag) return
  const x = Math.min(Math.max(0, drag.startX + (event.clientX - drag.pointerX) / canvasZoom.value), canvasWidth - nodeWidth)
  const y = Math.max(8, drag.startY + (event.clientY - drag.pointerY) / canvasZoom.value)
  layoutDraft.value = {
    ...layoutDraft.value,
    [layoutKey(drag.node)]: { x, y },
  }
}

function endLayoutDrag() {
  const drag = layoutDrag.value
  window.removeEventListener('pointermove', onLayoutPointerMove)
  window.removeEventListener('pointerup', endLayoutDrag)
  if (!drag) return
  const pos = layoutDraft.value[layoutKey(drag.node)] || { x: drag.startX, y: drag.startY }
  layoutDrag.value = null
  queueNodeLayoutChange(drag.node, drag.kind, pos)
}

function startStateDrag(node, event) {
  if (!canMutate.value) return
  selectGraphState(node)
  canvasDrag.value = {
    type: 'state',
    graphId: node.id,
    stateNodeId: node.state_node_id,
  }
  setDragData(event, canvasDrag.value)
}

function startActivityDrag(node, event) {
  if (!canMutate.value) return
  selectGraphActivity(node)
  canvasDrag.value = {
    type: 'activity',
    graphId: node.id,
    activityGraphId: node.id,
  }
  setDragData(event, canvasDrag.value)
}

function endCanvasDrag() {
  canvasDrag.value = null
  dragOverTarget.value = null
}

function leaveDropTarget(node) {
  if (dragOverTarget.value === node.id) {
    dragOverTarget.value = null
  }
}

function dragOverActivity(node, event) {
  if (!canMutate.value) return
  if (canvasDrag.value?.type !== 'state' || !supportsGraphActivityBinding(node)) return
  dragOverTarget.value = node.id
  if (event?.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function dragOverState(node, event) {
  if (!canMutate.value) return
  if (canvasDrag.value?.type !== 'activity') return
  const activity = graphActivityById.value.get(canvasDrag.value.activityGraphId)
  if (!supportsGraphActivityBinding(activity)) return
  dragOverTarget.value = node.id
  if (event?.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

async function dropOnActivity(node) {
  if (!requireEditMode('创建绑定')) return endCanvasDrag()
  if (canvasDrag.value?.type !== 'state') return endCanvasDrag()
  selectGraphActivity(node)
  selectedStateId.value = canvasDrag.value.stateNodeId
  bindingForm.value.state_node_id = canvasDrag.value.stateNodeId
  const role = node.activity_type === 'virtual' ? 'context_input' : 'input'
  await confirmDroppedBinding(node, role, canvasDrag.value.stateNodeId)
  endCanvasDrag()
}

async function dropOnState(node) {
  if (!requireEditMode('创建绑定')) return endCanvasDrag()
  if (canvasDrag.value?.type !== 'activity') return endCanvasDrag()
  const activity = graphActivityById.value.get(canvasDrag.value.activityGraphId)
  if (!activity) return endCanvasDrag()
  selectGraphState(node)
  selectedActivityGraphId.value = activity.id
  bindingForm.value.activity_graph_id = activity.id
  const role = activity.activity_type === 'virtual' ? 'declared_output' : 'output'
  await confirmDroppedBinding(activity, role, node.state_node_id)
  endCanvasDrag()
}

async function handleX6ConnectNodes({ source, target }) {
  if (!requireEditMode('创建绑定')) return
  if (source?.kind === 'state' && target?.kind === 'activity') {
    const state = source.node
    const activity = target.node
    if (!state?.state_node_id || !activity) return
    selectGraphState(state)
    selectGraphActivity(activity)
    const role = activity.activity_type === 'virtual' ? 'context_input' : 'input'
    setPendingBindingPreview(activity, role, state.state_node_id)
    await confirmDroppedBinding(activity, role, state.state_node_id)
    if (bindingAlreadyExistsOrQueued(activity, role, state.state_node_id)) {
      clearPendingBindingPreview(activity, role, state.state_node_id)
    }
    return
  }
  if (source?.kind === 'activity' && target?.kind === 'state') {
    const activity = source.node
    const state = target.node
    if (!activity || !state?.state_node_id) return
    selectGraphActivity(activity)
    selectGraphState(state)
    const role = activity.activity_type === 'virtual' ? 'declared_output' : 'output'
    setPendingBindingPreview(activity, role, state.state_node_id)
    await confirmDroppedBinding(activity, role, state.state_node_id)
    if (bindingAlreadyExistsOrQueued(activity, role, state.state_node_id)) {
      clearPendingBindingPreview(activity, role, state.state_node_id)
    }
    return
  }
  ElMessage.warning('请从右侧“产出”端口拉到另一类节点左侧“输入”端口')
}

function graphPayload() {
  return {
    state_root_ids: selectedStateRootIds.value.filter((id) => !isDraftStateId(id)),
    activity_scope_node_ids: selectedActivityScopeIds.value.filter((id) => !isDraftActivityId(id)),
    view_mode: viewMode.value,
    include_inactive: includeInactive.value,
    state_depth: stateDepth.value,
    activity_depth: activityDepth.value,
  }
}

function solverPrecheckPayload() {
  return {
    ...graphPayload(),
    view_mode: 'solver_ready',
    state_depth: 0,
    activity_depth: 0,
  }
}

function graphIdNumber(id) {
  return Number(String(id).split(':')[1])
}

function statePathContains(node, stateNodeId) {
  if (!node || !stateNodeId) return false
  if ((node.reference_parent_ids || []).some((id) => String(id) === String(stateNodeId))) return true
  if (stateDescendantNodeIds(stateNodeId, { activeOnly: false }).includes(node.state_node_id)) return true
  const pathIds = node.path_ids || []
  if (!Array.isArray(pathIds)) return false
  if (pathIds.some((item) => Array.isArray(item))) {
    return pathIds.some((path) =>
      Array.isArray(path) && path.some((id) => String(id) === String(stateNodeId)),
    )
  }
  return pathIds.some((id) => String(id) === String(stateNodeId))
}

function activityPathContains(node, activityNodeId) {
  if (!node || !activityNodeId) return false
  if (String(node.parent_id || '') === String(activityNodeId)) return true
  const pathIds = node.path_ids || []
  if (!Array.isArray(pathIds)) return false
  if (pathIds.some((item) => Array.isArray(item))) {
    return pathIds.some((path) =>
      Array.isArray(path) && path.some((id) => String(id) === String(activityNodeId)),
    )
  }
  if (pathIds.some((id) => String(id) === String(activityNodeId))) return true
  return (node.parent_activity_node_ids || []).some((id) => String(id) === String(activityNodeId))
}

function isStateVisibleInX6(node) {
  if (!node?.state_node_id) return false
  if (isInsideCollapsedStateContainer(node)) return false
  if (stateDepth.value !== 0 && selectedStateRootIds.value.length) {
    return !selectedStateRootIds.value.some((collapsedRootId) =>
      isDraftStateId(collapsedRootId) &&
      String(node.state_node_id) !== String(collapsedRootId) &&
      statePathContains(node, collapsedRootId),
    )
  }
  return true
}

function isActivityVisibleInX6(node) {
  if (!node?.id) return false
  if (isInsideCollapsedActivityContainer(node)) return false
  if (activityDepth.value === 0 || selectedActivityScopeIds.value.length !== 1) return true
  const collapsedRootId = selectedActivityScopeIds.value[0]
  if (!isDraftActivityId(collapsedRootId)) return true
  if (String(node.activity_node_id || '') === String(collapsedRootId)) return true
  return !activityPathContains(node, collapsedRootId)
}

function stateContainerCollapseKey(node) {
  return String(node?.id || node?.state_node_id || '')
}

function activityContainerCollapseKey(node) {
  return String(node?.id || node?.activity_node_id || '')
}

function isInsideCollapsedStateContainer(node) {
  if (!collapsedStateContainerKeys.value.size) return false
  for (const key of collapsedStateContainerKeys.value) {
    if (stateContainerCollapseKey(node) === String(key)) continue
    const container = visibleStateNodes.value.find((item) => stateContainerCollapseKey(item) === String(key))
    if (container && statePathContains(node, container.state_node_id)) return true
  }
  return false
}

function isInsideCollapsedActivityContainer(node) {
  if (!collapsedActivityContainerKeys.value.size) return false
  for (const key of collapsedActivityContainerKeys.value) {
    if (activityContainerCollapseKey(node) === String(key)) continue
    const container = visibleActivityNodes.value.find((item) => activityContainerCollapseKey(item) === String(key))
    if (container && activityPathContains(node, container.activity_node_id)) return true
  }
  return false
}

function isNestedExpandedStateContainer(node) {
  if (!node?.state_node_id) return false
  if (collapsedStateContainerKeys.value.has(stateContainerCollapseKey(node))) return false
  return isStateNestedInExpandedRoot(node)
}

function isStateNestedInExpandedRoot(node) {
  if (!node?.state_node_id) return false
  if (stateDepth.value !== 0 || !selectedStateRootIds.value.length) return false
  return selectedStateRootIds.value.some((rootId) =>
    String(rootId) !== String(node.state_node_id) && statePathContains(node, rootId),
  )
}

function isNestedExpandedActivityContainer(node) {
  if (!node?.activity_node_id) return false
  if (activityDepth.value !== 0 || selectedActivityScopeIds.value.length !== 1) return false
  if (collapsedActivityContainerKeys.value.has(activityContainerCollapseKey(node))) return false
  const rootId = selectedActivityScopeIds.value[0]
  return String(rootId) !== String(node.activity_node_id) && activityPathContains(node, rootId)
}

function collapseNestedStateContainer(node) {
  const key = stateContainerCollapseKey(node)
  if (!key) return false
  collapsedStateContainerKeys.value = new Set([...collapsedStateContainerKeys.value, key])
  return true
}

function collapseNestedActivityContainer(node) {
  const key = activityContainerCollapseKey(node)
  if (!key) return false
  collapsedActivityContainerKeys.value = new Set([...collapsedActivityContainerKeys.value, key])
  return true
}

function expandNestedStateContainer(node) {
  const key = stateContainerCollapseKey(node)
  if (!key || !collapsedStateContainerKeys.value.has(key)) return false
  const next = new Set(collapsedStateContainerKeys.value)
  next.delete(key)
  collapsedStateContainerKeys.value = next
  return true
}

function expandNestedActivityContainer(node) {
  const key = activityContainerCollapseKey(node)
  if (!key || !collapsedActivityContainerKeys.value.has(key)) return false
  const next = new Set(collapsedActivityContainerKeys.value)
  next.delete(key)
  collapsedActivityContainerKeys.value = next
  return true
}

function removeCollapsedStateContainerKey(nodeOrId) {
  const key = stateContainerCollapseKey(nodeOrId)
  if (!key || !collapsedStateContainerKeys.value.has(key)) return
  const next = new Set(collapsedStateContainerKeys.value)
  next.delete(key)
  collapsedStateContainerKeys.value = next
}

function removeCollapsedActivityContainerKey(nodeOrId) {
  const key = activityContainerCollapseKey(nodeOrId)
  if (!key || !collapsedActivityContainerKeys.value.has(key)) return
  const next = new Set(collapsedActivityContainerKeys.value)
  next.delete(key)
  collapsedActivityContainerKeys.value = next
}

function expandStateContainerForDraftChild(parentId) {
  if (!parentId) return
  const parentGraphNode = visibleStateNodes.value.find((node) =>
    String(node.state_node_id || '') === String(parentId),
  )
  const parentRootId = parentGraphNode?.state_node_id || parentId
  selectedStateRootIds.value = [
    ...selectedStateRootIds.value.filter((id) => String(id) !== String(parentRootId)),
    parentRootId,
  ]
  stateDepth.value = 0
  removeCollapsedStateContainerKey(parentGraphNode || { id: `state_node:${parentRootId}` })
}

function expandActivityContainerForDraftChild(parentId) {
  if (!parentId) return
  const parentGraphNode = visibleActivityNodes.value.find((node) =>
    String(node.activity_node_id || '') === String(parentId),
  )
  const parentScopeId = parentGraphNode?.activity_node_id || parentId
  selectedActivityScopeIds.value = [parentScopeId]
  activityDepth.value = 0
  removeCollapsedActivityContainerKey(parentGraphNode || { id: `activity_node:${parentScopeId}` })
}

function resetCollapsedStateContainers() {
  if (!collapsedStateContainerKeys.value.size) return
  collapsedStateContainerKeys.value = new Set()
}

function resetCollapsedActivityContainers() {
  if (!collapsedActivityContainerKeys.value.size) return
  collapsedActivityContainerKeys.value = new Set()
}

function pruneCollapsedStateContainers() {
  if (!collapsedStateContainerKeys.value.size) return
  const visibleKeys = new Set(visibleStateNodes.value.map(stateContainerCollapseKey).filter(Boolean))
  const next = new Set([...collapsedStateContainerKeys.value].filter((key) => visibleKeys.has(String(key))))
  if (next.size !== collapsedStateContainerKeys.value.size) collapsedStateContainerKeys.value = next
}

function pruneCollapsedActivityContainers() {
  if (!collapsedActivityContainerKeys.value.size) return
  const visibleKeys = new Set(visibleActivityNodes.value.map(activityContainerCollapseKey).filter(Boolean))
  const next = new Set([...collapsedActivityContainerKeys.value].filter((key) => visibleKeys.has(String(key))))
  if (next.size !== collapsedActivityContainerKeys.value.size) collapsedActivityContainerKeys.value = next
}

async function focusCurrentSelection() {
  resetCollapsedStateContainers()
  resetCollapsedActivityContainers()
  applySelectionAsGraphFocus()
  await reloadGraph()
}

function isGraphStateExpanded(node) {
  return !!node?.state_node_id &&
    stateDepth.value === 0 &&
    selectedStateRootIds.value.some((id) => String(id) === String(node.state_node_id))
}

function isGraphActivityExpanded(node) {
  return !!node?.activity_node_id &&
    selectedActivityScopeIds.value.length === 1 &&
    String(selectedActivityScopeIds.value[0]) === String(node.activity_node_id) &&
    activityDepth.value === 0
}

async function toggleGraphStateExpansion(node) {
  if (!node?.state_node_id) return
  const wasExpanded = isGraphStateExpanded(node)
  const nodeKey = stateContainerCollapseKey(node)
  closeContextMenu()
  selectedStateId.value = node.state_node_id
  selectionFocus.value = 'state'
  bindingForm.value.state_node_id = node.state_node_id
  resetBindingCoverageSelection()
  const isNestedContainer = isStateNestedInExpandedRoot(node)
  if (isNestedContainer && expandNestedStateContainer(node)) return
  if (isNestedContainer && isNestedExpandedStateContainer(node)) {
    collapseNestedStateContainer(node)
    return
  }
  if (wasExpanded) {
    selectedStateRootIds.value = selectedStateRootIds.value.filter((id) =>
      String(id) !== String(node.state_node_id),
    )
    if (!selectedStateRootIds.value.length) stateDepth.value = 1
    collapsedStateContainerKeys.value = new Set([...collapsedStateContainerKeys.value, nodeKey])
  } else {
    selectedStateRootIds.value = [
      ...selectedStateRootIds.value.filter((id) => String(id) !== String(node.state_node_id)),
      node.state_node_id,
    ]
    stateDepth.value = 0
    if (collapsedStateContainerKeys.value.has(nodeKey)) {
      const next = new Set(collapsedStateContainerKeys.value)
      next.delete(nodeKey)
      collapsedStateContainerKeys.value = next
    }
  }
  if (isDraftStateId(node.state_node_id)) return
  await reloadGraph()
}

async function toggleGraphActivityExpansion(node) {
  if (!node?.activity_node_id) return
  const wasExpanded = isGraphActivityExpanded(node)
  closeContextMenu()
  selectedActivityGraphId.value = node.id
  selectionFocus.value = 'activity'
  bindingForm.value.activity_graph_id = node.id
  onBindingActivityChange()
  if (expandNestedActivityContainer(node)) return
  if (isNestedExpandedActivityContainer(node)) {
    collapseNestedActivityContainer(node)
    return
  }
  resetCollapsedActivityContainers()
  selectedActivityScopeIds.value = [node.activity_node_id]
  activityDepth.value = wasExpanded ? 1 : 0
  if (isDraftActivityId(node.activity_node_id)) return
  await reloadGraph()
}

async function enterActivityFocus(node) {
  if (node?.activity_type !== 'virtual' || !node.activity_node_id) return
  await enterActivityFocusById(node.activity_node_id)
}

async function enterActivityFocusById(activityNodeId) {
  const node = activityNodeById.value.get(activityNodeId)
  if (!node) return
  selectedActivityScopeIds.value = [node.id]
  selectedActivityGraphId.value = `activity_node:${node.id}`
  selectionFocus.value = 'activity'
  bindingForm.value.activity_graph_id = selectedActivityGraphId.value
  activityDepth.value = 0
  onBindingActivityChange()
  await reloadGraph()
}

function applySelectionAsGraphFocus() {
  if (selectedStateId.value) {
    selectedStateRootIds.value = [selectedStateId.value]
  }
  const activity = selectedGraphActivity.value
  if (activity?.activity_node_id) {
    selectedActivityScopeIds.value = [activity.activity_node_id]
  } else if (activity?.parent_activity_node_ids?.length) {
    selectedActivityScopeIds.value = [activity.parent_activity_node_ids[0]]
  }
}

async function collapseCurrentSelection() {
  applySelectionAsGraphFocus()
  if (selectedStateRootIds.value.length) stateDepth.value = 1
  if (selectedActivityScopeIds.value.length) activityDepth.value = 1
  await reloadGraph()
}

async function expandCurrentSelectionOneLevel() {
  applySelectionAsGraphFocus()
  if (selectedStateRootIds.value.length) {
    stateDepth.value = stateDepth.value > 0 ? Math.min(stateDepth.value + 1, 12) : 2
  }
  if (selectedActivityScopeIds.value.length) {
    activityDepth.value = activityDepth.value > 0 ? Math.min(activityDepth.value + 1, 12) : 2
  }
  await reloadGraph()
}

async function expandCurrentSelectionAll() {
  applySelectionAsGraphFocus()
  if (selectedStateRootIds.value.length) stateDepth.value = 0
  if (selectedActivityScopeIds.value.length) activityDepth.value = 0
  await reloadGraph()
}

async function clearGraphFocus() {
  selectedStateRootIds.value = []
  selectedActivityScopeIds.value = []
  await reloadGraph()
}

function selectState(node) {
  selectedStateId.value = node.id
  selectionFocus.value = 'state'
  bindingForm.value.state_node_id = node.id
  resetBindingCoverageSelection()
  loadImpact()
}

async function selectActivityNode(node) {
  if (node?.resource_type === 'atomic_activity') {
    if (node.package_id) {
      selectedActivityScopeIds.value = [node.package_id]
      activityDepth.value = Math.max(activityDepth.value || 0, 3)
    }
    selectedActivityGraphId.value = `atomic_activity:${node.raw_id || node.atomic_activity_id || node.id}`
    selectionFocus.value = 'activity'
    bindingForm.value.activity_graph_id = selectedActivityGraphId.value
    onBindingActivityChange()
    if (node.package_id) await reloadGraph()
    loadImpact()
    return
  }
  selectedActivityGraphId.value = `activity_node:${node.id}`
  selectionFocus.value = 'activity'
  bindingForm.value.activity_graph_id = selectedActivityGraphId.value
  onBindingActivityChange()
  loadImpact()
}

function selectGraphState(node, event = null) {
  closeContextMenu()
  if (isEditMode.value && event && (event.ctrlKey || event.metaKey || event.shiftKey)) {
    toggleMultiSelectedState(node)
    selectedStateId.value = node.state_node_id
    selectionFocus.value = 'state'
    bindingForm.value.state_node_id = node.state_node_id
    resetBindingCoverageSelection()
    loadImpact()
    return
  }
  multiSelectedStateIds.value = []
  selectedStateId.value = node.state_node_id
  selectionFocus.value = 'state'
  bindingForm.value.state_node_id = node.state_node_id
  resetBindingCoverageSelection()
  loadImpact()
}

function selectGraphActivity(node) {
  closeContextMenu()
  selectedActivityGraphId.value = node.id
  selectionFocus.value = 'activity'
  bindingForm.value.activity_graph_id = node.id
  onBindingActivityChange()
  loadImpact()
}

function onBindingActivityChange() {
  const firstRole = roleOptions.value[0]?.value
  if (firstRole && !roleOptions.value.some((item) => item.value === bindingForm.value.binding_role)) {
    bindingForm.value.binding_role = firstRole
  }
  if (opRuleOptions.value.length === 1) {
    bindingForm.value.op_rule_id = opRuleOptions.value[0].id
  } else if (
    bindingForm.value.op_rule_id &&
    !opRuleOptions.value.some((item) => item.id === bindingForm.value.op_rule_id)
  ) {
    bindingForm.value.op_rule_id = null
  } else if (!selectedBindingActivity.value?.atomic_activity_id) {
    bindingForm.value.op_rule_id = null
  }
}

function selectBinding(row) {
  selectedBinding.value = row
  selectedStateId.value = row.state_node_id
  selectedActivityGraphId.value = row.atomic_activity_id
    ? `atomic_activity:${row.atomic_activity_id}`
    : `activity_node:${row.activity_node_id}`
  selectionFocus.value = row.atomic_activity_id || row.activity_node_id ? 'activity' : 'state'
  bindingForm.value.state_node_id = row.state_node_id
  bindingForm.value.binding_role = row.binding_role
  bindingForm.value.activity_graph_id = selectedActivityGraphId.value
  bindingForm.value.op_rule_id = row.op_rule_id
  setBindingCoverageSelectionForState(row.state_node_id, row.covered_leaf_state_ids || [])
  loadImpact()
}

function bindingActivityGraphId(binding) {
  if (!binding) return null
  return binding.atomic_activity_id
    ? `atomic_activity:${binding.atomic_activity_id}`
    : `activity_node:${binding.activity_node_id}`
}

async function revealIssueActivity(activityId) {
  if (!activityId) return null
  let activity = graphActivityById.value.get(activityId)
  if (activity) return activity

  if (activityId.startsWith('atomic_activity:')) {
    const atomicId = graphIdNumber(activityId)
    let packageId = null
    for (const [activityNodeId, refs] of atomicRefsByPackage.value.entries()) {
      if ((refs || []).some((ref) => ref.atomic_activity_id === atomicId && ref.is_active !== false)) {
        packageId = activityNodeId
        break
      }
    }
    selectedActivityScopeIds.value = packageId ? [packageId] : []
    activityDepth.value = 0
  } else if (activityId.startsWith('activity_node:')) {
    selectedActivityScopeIds.value = [graphIdNumber(activityId)]
    activityDepth.value = 0
  }

  await reloadGraph()
  activity = graphActivityById.value.get(activityId)
  return activity || null
}

async function revealIssueState(stateId) {
  if (!stateId) return null
  let graphState = visibleStateNodes.value.find((node) => node.state_node_id === stateId)
  if (graphState) return graphState

  selectedStateRootIds.value = [stateId]
  stateDepth.value = 0
  await reloadGraph()
  graphState = visibleStateNodes.value.find((node) => node.state_node_id === stateId)
  return graphState || null
}

async function revealIssueBinding(binding) {
  if (!binding) return null
  const activityId = bindingActivityGraphId(binding)
  if (activityId) await revealIssueActivity(activityId)
  await revealIssueState(binding.state_node_id)
  const refreshedBinding = bindingById.value.get(Number(binding.id)) || binding
  selectBinding(refreshedBinding)
  return refreshedBinding
}

async function inspectIssue(issue) {
  if (!issue) return
  const bindingId = issue.details?.binding_id
  if (bindingId) {
    const binding = bindingById.value.get(Number(bindingId))
    if (binding) {
      await revealIssueBinding(binding)
      ElMessage.info(`已定位绑定 #${binding.id}`)
      return
    }
  }

  const activityId = issue.related_activity_ids?.find((id) =>
    String(id).startsWith('activity_node:') || String(id).startsWith('atomic_activity:')) ||
    issueDetailActivityGraphId(issue)
  if (activityId) {
    const activity = await revealIssueActivity(activityId)
    if (activity) {
      selectGraphActivity(activity)
      ElMessage.info(`已定位 ${activity.code}`)
      return
    }
  }

  const stateId = Number(
    issue.related_state_ids?.find((id) => stateById.value.has(Number(id))) ??
    issueDetailStateId(issue),
  )
  if (stateId) {
    const graphState = await revealIssueState(stateId)
    if (graphState) {
      selectGraphState(graphState)
    } else {
      selectState(stateById.value.get(stateId))
    }
    ElMessage.info(`已定位 ${stateById.value.get(stateId)?.code || `状态 #${stateId}`}`)
    return
  }

  ElMessage.warning('当前图中没有找到该问题对应的可见节点')
}

function canRefreshIssueCoverage(issue) {
  return canMutate.value &&
    issue?.code === 'BINDING_COVERAGE_NOT_COMPLETE' &&
    !!issue.details?.binding_id &&
    bindingById.value.has(Number(issue.details.binding_id))
}

function canOpenRuleMaintenance(issue) {
  return ruleMaintenanceIssueCodes.has(String(issue?.code || '').toUpperCase())
}

async function openRuleMaintenance(issue) {
  await inspectIssue(issue)
  emit('open-workspace', 'activityCapability')
  ElMessage.info('已切换到活动能力，请为相关原子活动创建或启用规则。')
}

async function refreshOpenPreviews() {
  if (!machineTypeId.value) return
  if (validationResult.value) {
    validationResult.value = await validateNetworkEditor(machineTypeId.value, graphPayload())
  }
  if (solverPrecheck.value) {
    solverPrecheck.value = await precheckNetworkEditorSolver(machineTypeId.value, solverPrecheckPayload())
  }
  await reloadGraph()
}

async function refreshBindingCoverageById(bindingId) {
  if (!requireEditMode('刷新覆盖')) return null
  queueDraftChange({
    entityType: 'activity_state_binding',
    operation: 'refresh_coverage',
    entityId: bindingId,
    label: `刷新绑定覆盖 #${bindingId}`,
  })
  selectedBinding.value = bindings.value.find((item) => item.id === bindingId) || selectedBinding.value
  return selectedBinding.value
}

async function refreshIssueCoverage(issue) {
  if (!canRefreshIssueCoverage(issue)) return inspectIssue(issue)
  try {
    const bindingId = Number(issue.details.binding_id)
    const binding = bindingById.value.get(bindingId)
    if (binding) await revealIssueBinding(binding)
    await refreshBindingCoverageById(bindingId)
    ElMessage.success('覆盖刷新已加入草稿')
  } catch (error) {
    notifyOperationError('刷新覆盖失败', error)
  }
}

async function refreshSelectedCoverage() {
  if (!selectedBinding.value) return
  try {
    await refreshBindingCoverageById(selectedBinding.value.id)
    ElMessage.success('覆盖刷新已加入草稿')
  } catch (error) {
    notifyOperationError('刷新覆盖失败', error)
  }
}

function bindingLabel(row) {
  const state = stateById.value.get(row.state_node_id)
  const activity = row.atomic_activity_id
    ? atomicActivities.value.find((item) => item.id === row.atomic_activity_id)
    : activityNodeById.value.get(row.activity_node_id)
  return `${nodeLabel(state)} -> ${nodeLabel(activity)}`
}

function impactItemLabel(item) {
  if (!item) return '-'
  if (item.code && item.name) return `${item.code} ${item.name}`
  if (item.state_node_code && item.state_node_name) return `${item.state_node_code} ${item.state_node_name}`
  if (item.activity_node_code && item.activity_node_name) return `${item.activity_node_code} ${item.activity_node_name}`
  if (item.atomic_activity_code && item.atomic_activity_name) return `${item.atomic_activity_code} ${item.atomic_activity_name}`
  if (item.code) return item.code
  return item.message || item.id || '-'
}

function coverageTagType(status) {
  if (status === 'complete') return 'success'
  if (status === 'partial') return 'warning'
  return 'danger'
}

function draftOperationLabel(operation) {
  const labels = {
    create: '新建',
    update: '更新',
    delete: '删除',
    refresh_coverage: '刷新覆盖',
  }
  return labels[operation] || operation
}

function draftEntityLabel(entityType) {
  const labels = {
    state_node: '状态',
    activity_node: '虚拟活动',
    atomic_activity: '原子活动',
    activity_state_binding: '状态-活动绑定',
    state_node_reference: '状态包成员引用',
    state_package_fork: '状态包分叉',
    activity_package_atomic_ref: '活动包引用',
  }
  return labels[entityType] || entityType
}

async function onTypeChange() {
  rememberMachineType(machineTypeId.value)
  closeContextMenu()
  selectedStateId.value = null
  selectedActivityGraphId.value = null
  selectedBinding.value = null
  selectionFocus.value = ''
  selectedStateRootIds.value = []
  selectedActivityScopeIds.value = []
  validationResult.value = null
  solverPrecheck.value = null
  impactResult.value = null
  editorMode.value = 'preview'
  draftChanges.value = []
  draftSequence.value = 0
  pendingBindingPreview.value = null
  editBaselineRevision.value = null
  layoutDraft.value = {}
  containerDraft.value = {}
  resetCollapsedStateContainers()
  resetCollapsedActivityContainers()
  resetStateActivityCreationSelection()
  batchBindingDialogVisible.value = false
  batchBindingForm.value = { input_state_ids: [], output_state_ids: [], op_rule_id: null }
  await loadAll()
}

async function loadAll() {
  if (!machineTypeId.value) return
  loading.value = true
  try {
    const [
      states,
      activities,
      atomic,
      refs,
      bindingRows,
      rules,
      featureDefs,
    ] = await Promise.all([
      getStateNodes(machineTypeId.value),
      getActivityNodes(machineTypeId.value),
      getAtomicActivities(machineTypeId.value),
      getStateNodeReferences(machineTypeId.value),
      getActivityStateBindings(machineTypeId.value),
      getOpRules(machineTypeId.value),
      getFeatureDefs(machineTypeId.value),
    ])
    stateNodes.value = states
    activityNodes.value = activities
    atomicActivities.value = atomic
    stateReferences.value = refs
    bindings.value = bindingRows
    opRules.value = rules
    stateFeatureDefs.value = featureDefs
    await loadActivityPackageRefs(activities.filter((item) => item.level === 2))
    await reloadGraph()
  } catch (error) {
    notifyOperationError('加载网络编辑器数据失败', error)
  } finally {
    loading.value = false
  }
}

async function loadActivityPackageRefs(packages) {
  if (!packages.length) {
    atomicRefsByPackage.value = new Map()
    return
  }
  const entries = await Promise.all(
    packages.map(async (item) => [item.id, await getActivityPackageAtomicRefs(item.id)]),
  )
  atomicRefsByPackage.value = new Map(entries)
}

async function reloadGraph() {
  if (!machineTypeId.value) return
  try {
    graph.value = await previewNetworkEditorGraph(machineTypeId.value, graphPayload())
    bindings.value = graph.value.bindings || bindings.value
    pruneCollapsedStateContainers()
    pruneCollapsedActivityContainers()
    await loadImpact()
  } catch (error) {
    notifyOperationError('刷新网络图失败', error)
  }
}

function clearImpactDebounce() {
  if (!impactDebounceTimer) return
  window.clearTimeout(impactDebounceTimer)
  impactDebounceTimer = null
}

function loadImpact({ immediate = false } = {}) {
  clearImpactDebounce()
  if (immediate) return runImpactRequest()
  return new Promise((resolve) => {
    impactDebounceTimer = window.setTimeout(async () => {
      impactDebounceTimer = null
      resolve(await runImpactRequest())
    }, impactDebounceMs)
  })
}

async function runImpactRequest() {
  if (!machineTypeId.value) {
    resetImpactRequestState()
    return
  }
  const payload = { ...graphPayload() }
  if (selectionFocus.value === 'state' && selectedStateId.value) {
    const stateNodeId = committedStateIdForImpact(selectedStateId.value)
    if (!stateNodeId || (graph.value && !visibleStateNodes.value.some((node) => String(node.state_node_id) === String(stateNodeId)))) {
      resetImpactRequestState()
      return
    }
    payload.state_node_id = stateNodeId
  } else if (selectionFocus.value === 'activity' && selectedActivityGraphId.value) {
    const activityGraphId = committedActivityGraphIdForImpact(selectedActivityGraphId.value)
    if (!activityGraphId || (graph.value && !graphActivityById.value.has(activityGraphId))) {
      resetImpactRequestState()
      return
    }
    payload.activity_graph_id = activityGraphId
  } else if (selectedStateId.value) {
    const stateNodeId = committedStateIdForImpact(selectedStateId.value)
    if (!stateNodeId || (graph.value && !visibleStateNodes.value.some((node) => String(node.state_node_id) === String(stateNodeId)))) {
      resetImpactRequestState()
      return
    }
    payload.state_node_id = stateNodeId
  } else if (selectedActivityGraphId.value) {
    const activityGraphId = committedActivityGraphIdForImpact(selectedActivityGraphId.value)
    if (!activityGraphId || (graph.value && !graphActivityById.value.has(activityGraphId))) {
      resetImpactRequestState()
      return
    }
    payload.activity_graph_id = activityGraphId
  } else {
    resetImpactRequestState()
    return
  }

  const requestId = impactRequestSequence + 1
  impactRequestSequence = requestId
  const requestMachineTypeId = machineTypeId.value
  impactLoading.value = true
  try {
    const result = await analyzeNetworkEditorImpact(requestMachineTypeId, payload)
    if (requestId === impactRequestSequence && requestMachineTypeId === machineTypeId.value) {
      impactResult.value = result
    }
  } catch (error) {
    if (requestId === impactRequestSequence && requestMachineTypeId === machineTypeId.value) {
      impactResult.value = null
      if (isIgnorableImpactError(error)) return
      notifyOperationError('加载影响分析失败', error)
    }
  } finally {
    if (requestId === impactRequestSequence && requestMachineTypeId === machineTypeId.value) {
      impactLoading.value = false
    }
  }
}

function isIgnorableImpactError(error) {
  const status = Number(error?.status || error?.response?.status || error?.data?.status)
  const code = String(error?.errorCode || error?.data?.code || '')
  const message = String(error?.message || '')
  return status === 404 || code === 'HTTP_404' || message.includes('HTTP_404') || message.includes('HTTP 404')
}

async function runValidation() {
  if (!machineTypeId.value) return
  try {
    validationResult.value = await validateNetworkEditor(machineTypeId.value, graphPayload())
    ElMessage.success('校验完成')
    await reloadGraph()
  } catch (error) {
    notifyOperationError('校验失败', error)
  }
}

async function runSolverPrecheck() {
  if (!machineTypeId.value) return
  try {
    solverPrecheck.value = await precheckNetworkEditorSolver(machineTypeId.value, solverPrecheckPayload())
    if (solverPrecheck.value.status === 'ready') {
      ElMessage.success('求解预检已就绪')
    } else {
      ElMessage.warning('求解预检仍有阻塞项')
    }
  } catch (error) {
    notifyOperationError('求解预检失败', error)
  }
}

async function createBindingFromForm() {
  const activity = selectedBindingActivity.value
  if (!activity) return
  await createBindingForActivity(activity, bindingForm.value.binding_role, {
    stateNodeId: bindingForm.value.state_node_id,
    opRuleId: bindingForm.value.op_rule_id,
    coveredLeafStateIds: bindingFormCoveredLeafStateIds.value,
  })
}

async function createSelectedInputEdge() {
  const activity = selectedGraphActivity.value
  const role = activity?.activity_type === 'virtual' ? 'context_input' : 'input'
  await createBindingForActivity(activity, role, { stateNodeId: selectedStateId.value, quick: true })
}

async function createSelectedOutputEdge() {
  const activity = selectedGraphActivity.value
  const role = activity?.activity_type === 'virtual' ? 'declared_output' : 'output'
  await createBindingForActivity(activity, role, { stateNodeId: selectedStateId.value, quick: true })
}

function openBatchBindingDialog() {
  if (!requireEditMode('批量绑定')) return
  if (!supportsGraphActivityBinding(batchBindingActivity.value)) {
    ElMessage.warning('请先选择可绑定的虚拟活动或原子活动')
    return
  }
  batchBindingForm.value = {
    input_state_ids: [],
    output_state_ids: [],
    op_rule_id: batchOpRuleOptions.value.length === 1 ? batchOpRuleOptions.value[0].id : null,
  }
  batchBindingDialogVisible.value = true
}

function bindingMatchesActivity(binding, activity) {
  if (!binding || !activity) return false
  if (activity.atomic_activity_id) {
    return String(atomicActivityRefComparableId(binding.atomic_activity_id) || '') === String(activity.atomic_activity_id || '')
  }
  return String(activityRefComparableId(binding.activity_node_id) || '') === String(activity.activity_node_id || '')
}

function activityRefComparableId(value) {
  if (value && typeof value === 'object' && !Array.isArray(value) && value._draft_ref) {
    return draftActivityId(value._draft_ref)
  }
  return value
}

function atomicActivityRefComparableId(value) {
  if (value && typeof value === 'object' && !Array.isArray(value) && value._draft_ref) {
    return draftAtomicActivityId(value._draft_ref)
  }
  return value
}

function setPendingBindingPreview(activity, role, stateNodeId, opRuleId = null) {
  if (!activity || !role || !stateNodeId) {
    pendingBindingPreview.value = null
    return
  }
  const preview = {
    machine_type_id: machineTypeId.value,
    state_node_id: stateNodeId,
    binding_role: role,
  }
  if (activity.atomic_activity_id) {
    preview.atomic_activity_id = activity.atomic_activity_id
    if (opRuleId) preview.op_rule_id = opRuleId
  } else {
    preview.activity_node_id = activity.activity_node_id
  }
  pendingBindingPreview.value = preview
}

function clearPendingBindingPreview(activity = null, role = null, stateNodeId = null) {
  if (!pendingBindingPreview.value) return
  if (!activity && !role && !stateNodeId) {
    pendingBindingPreview.value = null
    return
  }
  if (pendingBindingPreviewMatches(pendingBindingPreview.value, activity, role, stateNodeId)) {
    pendingBindingPreview.value = null
  }
}

function pendingBindingPreviewMatches(preview, activity, role, stateNodeId) {
  if (!preview) return false
  if (role && preview.binding_role !== role) return false
  if (stateNodeId && !sameStateId(preview.state_node_id, stateNodeId)) return false
  if (activity && !bindingMatchesActivity(preview, activity)) return false
  return true
}

function bindingAlreadyExistsOrQueued(activity, role, stateNodeId) {
  const matches = (item) =>
    item &&
    bindingMatchesActivity(item, activity) &&
    item.binding_role === role &&
    sameStateId(item.state_node_id, stateNodeId)
  if (bindings.value.some(matches)) return true
  return draftChanges.value.some((change) =>
    change.entity_type === 'activity_state_binding' &&
    change.operation === 'create' &&
    matches(change.payload),
  )
}

function prefillBindingForm(activity, role, stateNodeId, opRuleId = null) {
  bindingForm.value = defaultBindingForm({
    binding_role: role,
    state_node_id: stateNodeId,
    activity_graph_id: activity?.id || null,
    op_rule_id: opRuleId,
  })
  if (activity?.atomic_activity_id && !opRuleId) {
    const rules = activeOpRulesForAtomicActivity(activity.atomic_activity_id)
    if (rules.length === 1) bindingForm.value.op_rule_id = rules[0].id
  }
}

function bindingCoveragePreviewText(stateNodeId) {
  const leafIds = leafStateIdsUnder(stateNodeId, { activeOnly: true })
  const state = stateById.value.get(stateNodeId)
  const childCount = displayStateChildren(stateNodeId, { activeOnly: true }).length
  if (!leafIds.length) return '覆盖范围：无启用叶子状态'
  if (leafIds.length === 1 && !childCount) return `覆盖范围：${nodeLabel(state)}`
  const labels = leafIds
    .slice(0, 4)
    .map((id) => nodeLabel(stateById.value.get(id)))
    .join('、')
  return `覆盖范围：状态包当前 ${leafIds.length} 个启用叶子${labels ? `（${labels}${leafIds.length > 4 ? '...' : ''}）` : ''}`
}

async function confirmDroppedBinding(activity, role, stateNodeId) {
  if (!requireEditMode('创建绑定')) return
  if (!activity || !stateNodeId) return
  const rules = activity.atomic_activity_id
    ? activeOpRulesForAtomicActivity(activity.atomic_activity_id)
    : []
  const opRuleId = rules.length === 1 ? rules[0].id : null
  prefillBindingForm(activity, role, stateNodeId, opRuleId)
  setPendingBindingPreview(activity, role, stateNodeId, opRuleId)
  if (bindingAlreadyExistsOrQueued(activity, role, stateNodeId)) {
    ElMessage.info('已存在相同绑定或已在草稿中，右侧表单已预填')
    return
  }
  if (activity.atomic_activity_id && !opRuleId) {
    ElMessage.warning(`拖线端点已预填。${atomicRuleSelectionWarning(activity)}`)
    return
  }
  const stateLabel = nodeLabel(stateById.value.get(stateNodeId))
  const activityLabel = `${activity.code || ''} ${activity.name || ''}`.trim()
  const ruleLabel = opRuleId ? nodeLabel(rules.find((item) => item.id === opRuleId)) : '无'
  const hasCoverageChoice = stateHasCoverageChoice(stateNodeId)
  const message = [
    `状态：${stateLabel}`,
    `活动：${activityLabel}`,
    `角色：${bindingRoleText(role)}`,
    `规则：${activity.atomic_activity_id ? ruleLabel : '虚拟活动无需规则'}`,
    bindingCoveragePreviewText(stateNodeId),
  ].join('\n')
  try {
    await ElMessageBox.confirm(message, '确认创建绑定', {
      type: 'info',
      confirmButtonText: hasCoverageChoice ? '全部当前成员' : '加入草稿',
      cancelButtonText: hasCoverageChoice ? '选择部分成员' : '仅预填表单',
      distinguishCancelAndClose: true,
    })
  } catch (error) {
    if (hasCoverageChoice && error === 'cancel') {
      bindingForm.value.coverage_mode = 'partial'
      bindingForm.value.covered_leaf_state_ids = []
      ElMessage.info('请在右侧选择覆盖成员后点击连接')
      return
    }
    if (isUserCancel(error)) {
      ElMessage.info('绑定信息已预填，可在右侧确认后点击连接')
      return
    }
    throw error
  }
  await createBindingForActivity(activity, role, { stateNodeId, opRuleId })
}

async function queueBatchBindings() {
  if (!requireEditMode('批量绑定')) return
  const activity = batchBindingActivity.value
  if (!supportsGraphActivityBinding(activity)) return
  const candidates = [
    ...batchBindingForm.value.input_state_ids.map((stateNodeId) => ({
      stateNodeId,
      role: batchBindingRoles.value.input,
    })),
    ...batchBindingForm.value.output_state_ids.map((stateNodeId) => ({
      stateNodeId,
      role: batchBindingRoles.value.output,
    })),
  ]
  const payloads = []
  let skipped = 0
  for (const candidate of candidates) {
    if (bindingAlreadyExistsOrQueued(activity, candidate.role, candidate.stateNodeId)) {
      skipped += 1
      continue
    }
    const payload = buildBindingPayload(activity, candidate.role, {
      stateNodeId: candidate.stateNodeId,
      opRuleId: batchBindingForm.value.op_rule_id,
    })
    if (!payload) return
    payloads.push({ ...candidate, payload })
  }
  if (!payloads.length) {
    ElMessage.info(skipped ? '所选状态已存在相同绑定或已在草稿中' : '请选择要绑定的状态')
    return
  }
  for (const item of payloads) {
    queueDraftChange({
      entityType: 'activity_state_binding',
      operation: 'create',
      payload: item.payload,
      label: `批量绑定：${item.role} / ${nodeLabel(stateById.value.get(item.stateNodeId))}`,
    })
  }
  const last = payloads[payloads.length - 1]
  bindingForm.value = defaultBindingForm({
    binding_role: last.role,
    state_node_id: last.stateNodeId,
    activity_graph_id: activity.id,
    op_rule_id: last.payload.op_rule_id || null,
  })
  batchBindingDialogVisible.value = false
  ElMessage.success(`批量绑定已加入草稿：${payloads.length} 条${skipped ? `，跳过 ${skipped} 条重复` : ''}`)
}

function buildBindingPayload(activity, role, { stateNodeId, opRuleId = null, quick = false, coveredLeafStateIds = null } = {}) {
  if (!stateNodeId || !activity || !supportsGraphActivityBinding(activity)) {
    ElMessage.warning('请先选择可绑定的状态和活动')
    return null
  }
  if (!bindingRoleAllowedForActivity(activity, role)) {
    ElMessage.warning(activity.atomic_activity_id
      ? '原子活动只支持输入或产出绑定'
      : '虚拟活动只支持上下文输入或声明输出绑定')
    return null
  }
  const payload = {
    machine_type_id: machineTypeId.value,
    state_node_id: stateNodeId,
    binding_role: role,
  }
  if (Array.isArray(coveredLeafStateIds)) {
    payload.covered_leaf_state_ids = coveredLeafStateIds
  }
  if (activity.atomic_activity_id) {
    const rules = activeOpRulesForAtomicActivity(activity.atomic_activity_id)
    if (opRuleId) {
      if (!rules.some((item) => item.id === opRuleId)) {
        ElMessage.warning('所选规则不是该原子活动的启用规则，请在右侧重新选择')
        return null
      }
      payload.op_rule_id = opRuleId
    } else if (rules.length === 1) {
      payload.op_rule_id = rules[0].id
    } else {
      ElMessage.warning(atomicRuleSelectionWarning(activity, quick))
      return null
    }
    payload.atomic_activity_id = activity.atomic_activity_id
  } else {
    payload.activity_node_id = activity.activity_node_id
  }
  return payload
}

async function createBindingForActivity(activity, role, {
  stateNodeId,
  opRuleId = null,
  quick = false,
  coveredLeafStateIds = null,
} = {}) {
  if (!requireEditMode('创建绑定')) return
  if (bindingAlreadyExistsOrQueued(activity, role, stateNodeId)) {
    ElMessage.info('已存在相同绑定或已在草稿中')
    clearPendingBindingPreview(activity, role, stateNodeId)
    return
  }
  const payload = buildBindingPayload(activity, role, { stateNodeId, opRuleId, quick, coveredLeafStateIds })
  if (!payload) return
  try {
    queueDraftChange({
      entityType: 'activity_state_binding',
      operation: 'create',
      payload,
      label: `创建绑定：${role} / ${nodeLabel(stateById.value.get(stateNodeId))}`,
    })
    bindingForm.value = defaultBindingForm({
      binding_role: role,
      state_node_id: stateNodeId,
      activity_graph_id: activity.id,
      op_rule_id: payload.op_rule_id || null,
    })
    setBindingCoverageSelectionForState(stateNodeId, payload.covered_leaf_state_ids || null)
    clearPendingBindingPreview(activity, role, stateNodeId)
    ElMessage.success('绑定创建已加入草稿')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function updateSelectedBindingFromForm() {
  if (!requireEditMode('更新绑定')) return
  if (!selectedBinding.value) return
  const activity = selectedBindingActivity.value
  const payload = buildBindingPayload(activity, bindingForm.value.binding_role, {
    stateNodeId: bindingForm.value.state_node_id,
    opRuleId: bindingForm.value.op_rule_id,
    coveredLeafStateIds: bindingFormCoveredLeafStateIds.value,
  })
  if (!payload) return
  try {
    queueDraftChange({
      entityType: 'activity_state_binding',
      operation: 'update',
      entityId: selectedBinding.value.id,
      payload,
      label: `更新绑定 #${selectedBinding.value.id}`,
    })
    ElMessage.success('绑定更新已加入草稿')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function removeBinding() {
  if (!requireEditMode('删除绑定')) return
  if (!selectedBinding.value) return
  try {
  await ElMessageBox.confirm('删除该状态-活动绑定？', '确认删除', { type: 'warning' })
  queueDraftChange({
    entityType: 'activity_state_binding',
    operation: 'delete',
    entityId: selectedBinding.value.id,
    label: `删除绑定 #${selectedBinding.value.id}`,
  })
  selectedBinding.value = null
  ElMessage.success('绑定删除已加入草稿')
  } catch (error) {
    if (!isUserCancel(error)) notifyOperationError('删除绑定失败', error)
  }
}

async function createReference() {
  if (!requireEditMode('添加状态包成员')) return
  try {
    const candidate = stateById.value.get(referenceForm.value.state_node_id)
    const parentId = referenceForm.value.parent_state_node_id
    if (statePackageChangeNeedsDecision(parentId)) {
      openPackageChangeDialog({
        mode: 'reuse',
        origin: 'reference_form',
        sourceStateNodeId: parentId,
        payload: {
          parent_id: parentId,
          sort_order: 0,
          name: candidate?.name || '',
        },
        candidate,
      })
      return
    }
    queueStateReuseReference(candidate, {
      parent_id: parentId,
      sort_order: 0,
      name: candidate?.name || '',
    })
    referenceForm.value = { state_node_id: null, parent_state_node_id: null }
  } catch (error) {
    notifyOperationError('创建状态引用失败', error)
  }
}

async function removeReference(row) {
  if (!requireEditMode('移除状态包成员')) return
  try {
    if (statePackageChangeNeedsDecision(row.parent_state_node_id)) {
      openPackageChangeDialog({
        mode: 'remove_reference',
        sourceStateNodeId: row.parent_state_node_id,
        row,
      })
      return
    }
    await ElMessageBox.confirm(
      `确认把「${row.state_node_code || row.state_node_id}」从状态包「${row.parent_state_node_code || row.parent_state_node_id}」中移除？真实状态不会被删除。`,
      '移除状态包成员',
      {
        type: 'warning',
        confirmButtonText: '移除引用',
        cancelButtonText: '取消',
      },
    )
    queueStateReferenceRemoval(row)
  } catch (error) {
    if (!isUserCancel(error)) notifyOperationError('移除状态引用失败', error)
  }
}

onMounted(async () => {
  try {
    machineTypes.value = await getMachineTypes()
  } catch (error) {
    notifyOperationError('加载设备类型失败', error)
  }
})

onUnmounted(() => {
  clearImpactDebounce()
  impactRequestSequence += 1
  window.removeEventListener('pointermove', onLayoutPointerMove)
  window.removeEventListener('pointerup', endLayoutDrag)
  window.removeEventListener('pointermove', onContainerMoveMove)
  window.removeEventListener('pointerup', endContainerMove)
  window.removeEventListener('pointermove', onContainerResizeMove)
  window.removeEventListener('pointerup', endContainerResize)
})
</script>

<style scoped>
:global(.network-submit-review .el-message-box__message) {
  white-space: pre-line;
  line-height: 1.55;
}

.network-editor {
  min-width: 0;
}
.workspace-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}
.workspace-toolbar h2 {
  margin: 0 0 6px;
}
.workspace-toolbar p {
  margin: 0;
  color: #606266;
}
.toolbar-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.focus-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.focus-context-strip {
  display: grid;
  grid-template-columns: minmax(220px, 1.1fr) minmax(220px, 2fr) auto;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 10px;
  border: 1px solid #c6e2ff;
  border-radius: 6px;
  background: #f5f9ff;
}
.focus-context-main,
.focus-boundaries,
.focus-context-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.focus-context-main,
.focus-boundaries {
  flex-wrap: wrap;
}
.focus-context-actions {
  justify-content: flex-end;
}
.focus-breadcrumb-item {
  min-width: 0;
  max-width: 180px;
  overflow: hidden;
  color: #303133;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.focus-breadcrumb-item:not(:last-child)::after {
  margin-left: 6px;
  color: #909399;
  content: "/";
}
.focus-boundaries > span {
  color: #606266;
  font-size: 12px;
  font-weight: 600;
}
.depth-control {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  font-size: 12px;
}
.depth-control :deep(.el-input-number) {
  width: 104px;
}
.summary-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(108px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.metric {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
}
.metric span {
  display: block;
  color: #606266;
  font-size: 12px;
}
.metric strong {
  display: block;
  margin-top: 4px;
  font-size: 20px;
  line-height: 1;
}
.metric.warning strong {
  color: #b88230;
}
.metric.danger strong {
  color: #c45656;
}
.solver-readiness-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #fff;
}
.solver-readiness-strip strong {
  display: block;
  font-size: 14px;
  line-height: 1.3;
}
.solver-readiness-strip span {
  display: block;
  margin-top: 3px;
  color: #606266;
  font-size: 12px;
  line-height: 1.4;
}
.solver-readiness-strip.is-success {
  border-color: #b3e19d;
  background: #f0f9eb;
}
.solver-readiness-strip.is-warning {
  border-color: #f3d19e;
  background: #fdf6ec;
}
.solver-readiness-strip.is-danger {
  border-color: #fab6b6;
  background: #fef0f0;
}
.solver-readiness-strip.is-info {
  border-color: #c8d3e0;
  background: #f4f7fb;
}
.workspace-body {
  display: grid;
  grid-template-rows: minmax(0, 1fr) minmax(176px, 30%);
  gap: 12px;
  height: max(520px, calc(100vh - 260px));
  min-height: 0;
}
.editor-grid {
  display: grid;
  grid-template-columns: 300px minmax(460px, 1fr) 360px;
  gap: 12px;
  min-height: 0;
}
.resource-pane,
.canvas-pane,
.properties-pane,
.validation-pane {
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  min-width: 0;
}
.resource-pane,
.properties-pane {
  padding: 12px;
  overflow: auto;
  scrollbar-gutter: stable;
}
.canvas-pane {
  display: flex;
  min-height: 0;
  flex-direction: column;
  padding: 12px;
  overflow: hidden;
}
.canvas-action-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 8px;
}
.canvas-view-controls {
  flex: 0 0 auto;
}
.drag-hint {
  margin-right: auto;
  color: #606266;
  font-size: 12px;
}
.solver-view-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 7px 9px;
  border: 1px solid #d9ecff;
  border-radius: 6px;
  background: #f5f9ff;
  color: #606266;
  font-size: 12px;
  line-height: 1.35;
}
.solver-view-note strong {
  flex: 0 0 auto;
  color: #337ecc;
}
.solver-view-note span {
  min-width: 0;
}
.pane-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  margin-bottom: 10px;
  font-weight: 600;
}
.search-input {
  margin-bottom: 10px;
}
.quick-create {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 12px;
}
.draft-change-list {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
  padding: 8px 0;
  border-top: 1px solid #ebeef5;
  border-bottom: 1px solid #ebeef5;
}
.draft-change-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #606266;
}
.draft-change-row span:last-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resource-section,
.detail-block {
  margin-bottom: 14px;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}
.tree-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.tree-row-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}
.tree-row-actions :deep(.el-button) {
  width: 22px;
  height: 22px;
}
.unplaced-list {
  display: grid;
  gap: 6px;
  max-height: 220px;
  overflow-y: auto;
  padding-right: 2px;
}
.unplaced-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 5px 8px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.unplaced-row:hover {
  border-color: #f3d19e;
  background: #fffaf2;
}
.unplaced-row span {
  color: #909399;
  font-size: 11px;
}
.unplaced-row strong {
  overflow: hidden;
  color: #303133;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reference-form {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  margin-bottom: 8px;
}
.duplicate-state-dialog p {
  margin: 0 0 12px;
  color: #606266;
  line-height: 1.5;
}
.duplicate-state-list {
  display: grid;
  gap: 8px;
}
.duplicate-state-list :deep(.el-radio) {
  width: 100%;
  height: auto;
  margin-right: 0;
  padding: 8px 10px;
}
.duplicate-state-list :deep(.el-radio__label) {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.duplicate-state-list strong,
.duplicate-state-list span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.duplicate-state-list span {
  color: #909399;
  font-size: 12px;
}
.package-change-dialog p {
  margin: 0 0 10px;
  color: #606266;
  line-height: 1.5;
}
.package-reference-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.package-change-options {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}
.package-change-options :deep(.el-radio) {
  width: 100%;
  height: auto;
  margin-right: 0;
  padding: 8px 10px;
}
.package-change-options :deep(.el-radio__label) {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.package-change-options strong,
.package-change-options span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.package-change-options span {
  color: #909399;
  font-size: 12px;
}
.package-fork-form {
  padding-top: 4px;
}
.package-impact-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 0 12px;
}
.package-impact-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.package-impact-grid div {
  min-width: 0;
  padding: 8px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}
.package-impact-grid span,
.package-impact-list > span {
  display: block;
  color: #909399;
  font-size: 12px;
}
.package-impact-grid strong {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #303133;
}
.package-impact-list {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}
.package-impact-list > div {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.canvas {
  position: relative;
  flex: 1 1 auto;
  min-height: 360px;
  overflow: auto;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: linear-gradient(90deg, #f8fafc 0 49%, #fff 49% 51%, #f8fafc 51% 100%);
}
.canvas-surface {
  position: relative;
}
.canvas-content {
  position: relative;
  transform-origin: 0 0;
}
.edge-layer {
  position: absolute;
  inset: 0;
  width: 100%;
  min-height: 100%;
  pointer-events: none;
}
.edge-layer * {
  pointer-events: none;
}
.edge-line {
  fill: none;
  stroke-width: 2;
  opacity: 0.62;
}
.edge-line.highlighted {
  stroke-width: 4;
  opacity: 0.96;
}
.edge-line.aggregate {
  stroke-dasharray: 6 5;
  opacity: 0.76;
}
.edge-hit-target {
  fill: none;
  stroke: transparent;
  stroke-width: 18;
  cursor: pointer;
  pointer-events: stroke;
}
.input-edge {
  stroke: #409eff;
}
.output-edge {
  stroke: #67c23a;
}
.edge-label {
  fill: #4b5563;
  paint-order: stroke;
  stroke: #fff;
  stroke-width: 4px;
  stroke-linejoin: round;
  font-size: 11px;
  font-weight: 700;
  text-anchor: middle;
}
.canvas-column {
  position: static;
  width: auto;
}
.state-column {
  display: contents;
}
.activity-column {
  display: contents;
}
.virtual-container,
.state-package-container {
  position: absolute;
  pointer-events: auto;
  border: 1px dashed #a8abb2;
  border-radius: 6px;
  padding: 6px 8px;
  color: #606266;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.virtual-container {
  background: rgba(64, 158, 255, 0.06);
  box-shadow: inset 3px 0 0 rgba(64, 158, 255, 0.28);
}
.state-package-container {
  background: rgba(103, 194, 58, 0.07);
  box-shadow: inset 3px 0 0 rgba(103, 194, 58, 0.26);
}
.virtual-container.selected {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.1);
}
.state-package-container.selected {
  border-color: #67c23a;
  background: rgba(103, 194, 58, 0.11);
}
.virtual-container .container-title,
.state-package-container .container-title {
  max-width: 132px;
  margin-left: 16px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
}
.virtual-container .container-meta {
  min-width: 56px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.virtual-container small,
.state-package-container small {
  color: #909399;
  font-size: 11px;
  white-space: nowrap;
}
.virtual-container small.warning {
  color: #e6a23c;
  font-weight: 600;
}
.virtual-container small.success {
  color: #67c23a;
  font-weight: 600;
}
.container-move-handle {
  position: absolute;
  left: 5px;
  top: 5px;
  width: 16px;
  height: 16px;
  border: 1px solid #909399;
  border-radius: 4px;
  background:
    linear-gradient(#909399, #909399) center 4px / 8px 1px no-repeat,
    linear-gradient(#909399, #909399) center 7px / 8px 1px no-repeat,
    linear-gradient(#909399, #909399) center 10px / 8px 1px no-repeat,
    rgba(255, 255, 255, 0.92);
  cursor: move;
  opacity: 0.8;
  pointer-events: auto;
  z-index: 5;
}
.container-move-handle:hover {
  opacity: 1;
  border-color: #606266;
}
.container-resize-handle {
  position: absolute;
  right: 5px;
  bottom: 5px;
  width: 12px;
  height: 12px;
  border-right: 2px solid #909399;
  border-bottom: 2px solid #909399;
  cursor: nwse-resize;
  opacity: 0.72;
  pointer-events: auto;
  z-index: 5;
}
.container-resize-handle:hover {
  opacity: 1;
}
.graph-node {
  position: absolute;
  z-index: 2;
  width: 220px;
  min-height: 56px;
  border: 1px solid #cfd8e3;
  border-radius: 6px;
  background: #fff;
  text-align: left;
  padding: 8px 10px 8px 24px;
  cursor: pointer;
  display: grid;
  gap: 2px;
  box-shadow: 0 1px 2px rgba(31, 41, 55, 0.06);
}
.layout-handle {
  position: absolute;
  left: 6px;
  top: 8px;
  width: 10px;
  height: 38px;
  border-radius: 5px;
  background:
    radial-gradient(circle, #909399 1px, transparent 1.8px) 0 0 / 5px 5px;
  cursor: move;
  opacity: 0.72;
}
.layout-handle:hover {
  opacity: 1;
}
.semantic-port {
  position: absolute;
  top: 50%;
  z-index: 4;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 20px;
  border: 1px solid #c6e2ff;
  border-radius: 999px;
  color: #337ecc;
  background: #ecf5ff;
  font-size: 11px;
  line-height: 1;
  cursor: copy;
  transform: translateY(-50%);
  user-select: none;
}
.semantic-port.port-left {
  left: -18px;
}
.semantic-port.port-right {
  right: -18px;
}
.semantic-port:hover,
.semantic-port:focus-visible {
  border-color: #409eff;
  outline: none;
  background: #d9ecff;
}
.graph-node:active {
  cursor: pointer;
}
.graph-node.selected {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.18);
}
.graph-node.multi-selected {
  border-color: #e6a23c;
  box-shadow: 0 0 0 2px rgba(230, 162, 60, 0.18);
}
.graph-node.staged-input {
  border-left-color: #409eff;
  background: #ecf5ff;
}
.graph-node.staged-output {
  border-left-color: #67c23a;
  background: #f0f9eb;
}
.graph-node.impact-highlight:not(.selected) {
  border-color: #67c23a;
  box-shadow: 0 0 0 2px rgba(103, 194, 58, 0.18);
}
.graph-node.dragging {
  opacity: 0.56;
}
.graph-node.drop-target {
  border-color: #67c23a;
  box-shadow: 0 0 0 3px rgba(103, 194, 58, 0.2);
}
.state-node {
  border-left: 4px solid #409eff;
}
.state-node.coverage-gap {
  border-color: #f3d19e;
  border-left-color: #e6a23c;
  background: #fffaf2;
}
.activity-node {
  border-left: 4px solid #909399;
}
.activity-node.executable {
  border-left-color: #67c23a;
}
.activity-node.focus-root {
  border-color: #409eff;
  background: #f5f9ff;
}
.node-code {
  font-size: 12px;
  color: #606266;
}
.node-name {
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.node-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
  font-size: 12px;
  color: #909399;
}
.node-reference-badge {
  border: 1px solid #f3d19e;
  border-radius: 999px;
  padding: 0 6px;
  color: #b88230;
  background: #fdf6ec;
  line-height: 17px;
}
.node-coverage-badge,
.node-binding-badge,
.node-kind-badge,
.node-metric-badge {
  border-radius: 999px;
  padding: 0 6px;
  line-height: 17px;
  white-space: nowrap;
}
.node-coverage-badge.coverage-complete {
  color: #529b2e;
  background: #f0f9eb;
  border: 1px solid #b3e19d;
}
.node-coverage-badge.coverage-partial {
  color: #b88230;
  background: #fdf6ec;
  border: 1px solid #f3d19e;
}
.node-coverage-badge.coverage-stale {
  color: #c45656;
  background: #fef0f0;
  border: 1px solid #fab6b6;
}
.node-binding-badge {
  color: #606266;
  background: #f4f4f5;
  border: 1px solid #dcdfe6;
}
.node-kind-badge,
.node-metric-badge {
  color: #606266;
  background: #f4f4f5;
  border: 1px solid #dcdfe6;
}
.node-metric-badge.inherited {
  color: #b88230;
  background: #fdf6ec;
  border-color: #f3d19e;
}
.node-metric-badge.complete {
  color: #529b2e;
  background: #f0f9eb;
  border-color: #b3e19d;
}
.node-metric-badge.warning {
  color: #c45656;
  background: #fef0f0;
  border-color: #fab6b6;
}
.node-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 2px;
}
.node-action {
  border: 1px solid #c6e2ff;
  border-radius: 999px;
  padding: 0 7px;
  color: #337ecc;
  background: #ecf5ff;
  font-size: 11px;
  line-height: 18px;
  cursor: pointer;
}
.node-action:hover,
.node-action:focus-visible {
  border-color: #409eff;
  outline: none;
  background: #d9ecff;
}
.node-context-menu {
  position: absolute;
  z-index: 8;
  min-width: 148px;
  max-width: 180px;
  padding: 6px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 8px 22px rgba(31, 41, 55, 0.16);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.context-menu-title {
  padding: 3px 6px 5px;
  color: #606266;
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 2px;
}
.node-context-menu button {
  border: 0;
  border-radius: 4px;
  padding: 6px 8px;
  background: transparent;
  color: #303133;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.node-context-menu button:hover,
.node-context-menu button:focus-visible {
  outline: none;
  background: #f5f7fa;
}
.node-context-menu button:disabled {
  color: #c0c4cc;
  cursor: not-allowed;
  background: transparent;
}
.multi-select-toolbar {
  position: absolute;
  z-index: 7;
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 430px;
  padding: 6px 8px;
  border: 1px solid #f3d19e;
  border-radius: 6px;
  background: #fdf6ec;
  box-shadow: 0 6px 18px rgba(31, 41, 55, 0.12);
}
.multi-select-toolbar strong {
  color: #7d5b24;
  font-size: 12px;
  white-space: nowrap;
}
.multi-select-toolbar button {
  border: 1px solid #eebe77;
  border-radius: 4px;
  padding: 4px 7px;
  background: #fff;
  color: #7d5b24;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.multi-select-toolbar button:hover,
.multi-select-toolbar button:focus-visible {
  outline: none;
  border-color: #e6a23c;
  background: #faecd8;
}
.multi-select-toolbar button:disabled {
  color: #c0c4cc;
  border-color: #e4e7ed;
  cursor: not-allowed;
  background: #fff;
}
.reference-parent-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.binding-coverage-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.atomic-output-coverage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 8px;
}
.atomic-output-coverage-row {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}
.coverage-row-title {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #303133;
  font-size: 12px;
}
.coverage-row-title small {
  flex-shrink: 0;
  color: #909399;
}
.form-hint {
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
.binding-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.impact-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}
.impact-grid div {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  background: #f8fafc;
}
.impact-grid span {
  display: block;
  color: #606266;
  font-size: 12px;
}
.impact-grid strong {
  display: block;
  margin-top: 2px;
  color: #303133;
  font-size: 18px;
  line-height: 1;
}
.impact-coverage {
  margin-top: 8px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  background: #fafcff;
}
.impact-coverage .impact-grid {
  margin-bottom: 0;
}
.impact-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.impact-section {
  margin-top: 10px;
}
.impact-section > span {
  display: block;
  color: #667085;
  font-size: 12px;
}
.coverage-panel {
  margin-top: 10px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px;
  background: #fafcff;
}
.coverage-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}
.coverage-summary div {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 7px;
  background: #fff;
  min-width: 0;
}
.coverage-summary span,
.coverage-list > span {
  display: block;
  color: #606266;
  font-size: 12px;
}
.coverage-summary strong {
  display: block;
  overflow: hidden;
  margin-top: 2px;
  color: #303133;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.coverage-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.coverage-list > span {
  flex: 0 0 100%;
}
.coverage-list.compact {
  max-height: 86px;
  overflow: auto;
}
.validation-pane {
  display: grid;
  grid-template-columns: 1fr 1fr 0.9fr;
  gap: 12px;
  min-height: 0;
  padding: 12px;
  overflow: auto;
  scrollbar-gutter: stable;
}
.issue-column,
.solver-precheck-column {
  min-width: 0;
}
.validation-pane :deep(.el-table__row) {
  cursor: pointer;
}
.issue-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.solver-precheck-blocked-alert {
  margin-bottom: 8px;
}
.solver-precheck-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 8px;
}
.solver-precheck-summary-grid div,
.solve-template-summary {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  padding: 8px;
}
.solver-precheck-summary-grid span,
.template-row span {
  display: block;
  color: #606266;
  font-size: 12px;
}
.solver-precheck-summary-grid strong,
.template-row strong {
  display: block;
  overflow: hidden;
  color: #303133;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.solve-template-summary {
  margin-bottom: 8px;
}
.template-tags {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
}
.template-row {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}
.solver-precheck-blockers {
  margin-top: 10px;
}
@media (max-width: 1180px) {
  .editor-grid {
    grid-template-columns: 1fr;
  }
  .validation-pane {
    grid-template-columns: 1fr;
  }
}
</style>
