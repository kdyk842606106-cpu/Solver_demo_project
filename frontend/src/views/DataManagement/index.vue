<template>
  <el-tabs tab-position="left" class="data-tabs">
    <el-tab-pane label="设备类型" name="machineType">
      <MachineTypePage />
    </el-tab-pane>
    <el-tab-pane label="设备实例" name="machine">
      <MachinePage />
    </el-tab-pane>
    <el-tab-pane label="特征定义" name="featureDef">
      <FeatureDefPage />
    </el-tab-pane>
    <el-tab-pane label="状态管理" name="state">
      <StatePage />
    </el-tab-pane>
    <el-tab-pane label="活动规则" name="rule">
      <RulePage />
    </el-tab-pane>
    <el-tab-pane label="资源管理" name="resource">
      <ResourcePage />
    </el-tab-pane>
  </el-tabs>
</template>

<script setup>
import MachineTypePage from './MachineTypePage.vue'
import MachinePage from './MachinePage.vue'
import FeatureDefPage from './FeatureDefPage.vue'
import StatePage from './StatePage.vue'
import RulePage from './RulePage.vue'
import ResourcePage from './ResourcePage.vue'
</script>

<style scoped>
.data-tabs { min-height: calc(100vh - 104px); }
:deep(.el-tabs__content) { padding: 0 16px; }
</style>
