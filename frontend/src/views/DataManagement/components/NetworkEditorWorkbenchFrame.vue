<template>
  <div
    class="network-editor-workbench-frame"
    data-testid="network-editor-workbench-frame"
  >
    <div class="workspace-body" :data-testid="workspaceTestId">
      <div
        class="editor-grid"
        :class="{
          'resource-collapsed': resourcePaneCollapsed,
          'properties-collapsed': propertiesPaneCollapsed,
        }"
        :style="editorGridStyle"
      >
        <slot name="resource" />
        <slot name="canvas" />
        <slot name="properties" />
      </div>

      <slot name="validation-status" />
      <slot name="validation-details" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  resourcePaneCollapsed: { type: Boolean, default: false },
  propertiesPaneCollapsed: { type: Boolean, default: false },
  resourcePaneWidth: { type: Number, default: 260 },
  propertiesPaneWidth: { type: Number, default: 320 },
  workspaceTestId: { type: String, default: '' },
})

const editorGridStyle = computed(() => ({
  '--resource-pane-width': `${props.resourcePaneWidth}px`,
  '--properties-pane-width': `${props.propertiesPaneWidth}px`,
}))
</script>

<style>
.network-editor {
  min-width: 0;
}

.network-editor .toolbar-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
}

.network-editor .filter-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.network-editor .filter-strip > .el-select {
  min-width: 220px;
}

.network-editor .filter-strip > .toolbar-controls {
  margin-left: auto;
}

.network-editor .depth-control {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  font-size: 12px;
}

.network-editor .depth-control .el-input-number {
  width: 110px;
}

.network-editor .summary-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.network-editor .metric {
  display: inline-grid;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid #dcdfe6;
  border-radius: 999px;
  background: #fff;
}

.network-editor .metric span {
  color: #606266;
  font-size: 12px;
}

.network-editor .metric strong {
  font-size: 14px;
  line-height: 1;
}

.network-editor .metric.warning strong {
  color: #b88230;
}

.network-editor .metric.danger strong {
  color: #c45656;
}

.network-editor-workbench-frame {
  width: 100%;
  min-width: 0;
}

.network-editor-workbench-frame .workspace-body {
  display: flex;
  width: 100%;
  min-width: 0;
  height: max(620px, calc(100vh - 196px));
  min-height: 0;
  flex-direction: column;
  gap: 8px;
}

.network-editor-workbench-frame .editor-grid {
  position: relative;
  display: grid;
  width: 100%;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  grid-template-columns:
    var(--resource-pane-width, 260px)
    minmax(720px, 1fr)
    var(--properties-pane-width, 320px);
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
}

.network-editor-workbench-frame .editor-grid.resource-collapsed {
  grid-template-columns: minmax(720px, 1fr) var(--properties-pane-width, 320px);
}

.network-editor-workbench-frame .editor-grid.properties-collapsed {
  grid-template-columns: var(--resource-pane-width, 260px) minmax(720px, 1fr);
}

.network-editor-workbench-frame
  .editor-grid.resource-collapsed.properties-collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.network-editor-workbench-frame .resource-pane,
.network-editor-workbench-frame .canvas-pane,
.network-editor-workbench-frame .properties-pane,
.network-editor-workbench-frame .validation-pane {
  min-width: 0;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
}

.network-editor-workbench-frame .resource-pane,
.network-editor-workbench-frame .properties-pane {
  position: relative;
  padding: 10px;
  overflow: auto;
  scrollbar-gutter: stable;
}

.network-editor-workbench-frame .resource-pane.collapsed,
.network-editor-workbench-frame .properties-pane.collapsed {
  position: absolute;
  top: 8px;
  bottom: 8px;
  z-index: 7;
  display: flex;
  width: 36px;
  align-items: stretch;
  flex-direction: column;
  padding: 6px 4px;
  overflow: hidden;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
}

.network-editor-workbench-frame .resource-pane.collapsed {
  left: 8px;
}

.network-editor-workbench-frame .properties-pane.collapsed {
  right: 8px;
}

.network-editor-workbench-frame .resource-pane.collapsed .pane-header,
.network-editor-workbench-frame .properties-pane.collapsed .pane-header {
  justify-content: center;
  margin-bottom: 6px;
}

.network-editor-workbench-frame .resource-pane.collapsed .pane-header > span,
.network-editor-workbench-frame .properties-pane.collapsed .pane-header > span {
  display: none;
}

.network-editor-workbench-frame .resource-pane.collapsed .pane-header-actions,
.network-editor-workbench-frame .properties-pane.collapsed .pane-header-actions {
  justify-content: center;
}

.network-editor-workbench-frame .pane-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 9;
  width: 10px;
  cursor: col-resize;
  touch-action: none;
}

.network-editor-workbench-frame .pane-resize-handle::after {
  position: absolute;
  top: 12px;
  bottom: 12px;
  left: 4px;
  width: 2px;
  border-radius: 999px;
  background: transparent;
  content: "";
  transition: background 0.14s ease;
}

.network-editor-workbench-frame .pane-resize-handle:hover::after,
.network-editor-workbench-frame .pane-resize-handle:focus-visible::after,
.network-editor-pane-resizing
  .network-editor-workbench-frame
  .pane-resize-handle::after {
  background: #409eff;
}

.network-editor-workbench-frame .resource-resize-handle {
  right: -5px;
}

.network-editor-workbench-frame .properties-resize-handle {
  left: -5px;
}

.network-editor-pane-resizing {
  cursor: col-resize;
  user-select: none;
}

.network-editor-workbench-frame .canvas-pane {
  display: flex;
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  padding: 8px;
  overflow: hidden;
}

.network-editor-workbench-frame .x6-canvas-wrapper {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex: 1 1 auto;
  overflow: auto;
  background: #f8fafc;
}

.network-editor-workbench-frame .canvas-action-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin-bottom: 6px;
}

.network-editor-workbench-frame .canvas-view-controls {
  flex: 0 0 auto;
}

.network-editor-workbench-frame .drag-hint {
  margin-right: auto;
  color: #606266;
  font-size: 12px;
}

.network-editor-workbench-frame .pane-header {
  display: flex;
  min-height: 26px;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 8px;
  font-weight: 600;
}

.network-editor-workbench-frame .pane-header-actions {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.network-editor-workbench-frame .pane-rail {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 auto;
  color: #606266;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  writing-mode: vertical-rl;
}

.network-editor-workbench-frame .validation-pane {
  padding: 10px;
  overflow: auto;
  scrollbar-gutter: stable;
}

.network-editor-workbench-frame .validation-status-strip {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
}

.network-editor-workbench-frame .validation-status-strip.is-success {
  border-color: #b3e19d;
  background: #f0f9eb;
}

.network-editor-workbench-frame .validation-status-strip.is-warning {
  border-color: #f3d19e;
  background: #fdf6ec;
}

.network-editor-workbench-frame .validation-status-strip.is-danger {
  border-color: #fab6b6;
  background: #fef0f0;
}

.network-editor-workbench-frame .validation-status-strip.is-info {
  border-color: #c8d3e0;
  background: #f4f7fb;
}

.network-editor-workbench-frame .validation-status-main {
  min-width: 0;
}

.network-editor-workbench-frame .validation-status-main strong {
  display: block;
  font-size: 13px;
  line-height: 1.2;
}

.network-editor-workbench-frame .validation-status-main span {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #606266;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.network-editor-workbench-frame .validation-status-chips,
.network-editor-workbench-frame .validation-status-actions {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

@media (max-width: 1180px) {
  .network-editor-workbench-frame .validation-status-strip {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .network-editor-workbench-frame .validation-status-chips,
  .network-editor-workbench-frame .validation-status-actions {
    justify-content: flex-start;
  }
}
</style>
