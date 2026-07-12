# TICKET-039: 数据管理网络编辑器 MVP

> Status: implemented
> Version: V0.3
> Completed: 2026-06-23
> Depends on: `docs/TICKET_037.md`, `docs/TICKET_038.md`

## Scope

本工单在 Data Management 中新增网络编辑器工作区，提供真实可操作的状态-活动-状态建模入口。

## Implemented

- [x] `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue`
- [x] Data Management 新增 `网络编辑器` tab
- [x] 前端 API 封装网络编辑器相关接口
- [x] 顶部工具栏：
  - 设备类型选择
  - 视图模式切换
  - include inactive
  - 新建状态、虚拟活动、原子活动
  - 刷新、校验、求解预检
  - 网络统计总览，包含部分实现虚拟活动和跨层级绑定数量
  - 求解就绪状态条，标记暂不可求解、提交/求解前需复核或求解输入就绪
- [x] 左侧资源区：
  - 状态树
  - 活动树（含二级包下原子活动叶子）
  - 状态包、一级活动和二级活动包行内新建子节点入口
  - 未布置状态/活动列表、搜索过滤与点击定位
  - 状态引用维护
- [x] 中间二部图画布：
  - 状态列
  - 活动列
  - 状态包容器范围
  - 虚拟活动容器范围、上下文前置和输出覆盖摘要
  - 折叠状态包成员数、深度、关联活动和覆盖摘要
  - 状态包节点覆盖摘要和缺口高亮
  - 活动节点子活动、最大后代层级、声明输出实现覆盖、输入、上下文、输出和跨层级数量摘要
  - 输入/输出边投影
  - 拖拽快速建绑定
  - 层级深度控制，默认折叠为 `State depth = 1`、`Activity depth = 2`
  - 选中对象局部折叠、逐层展开和展开完整子树
- [x] 右侧属性区：
  - 当前选中状态/活动
  - 所在状态包和其他出现位置
  - 影响分析
  - 选中活动的直接前置、继承前置、产出状态、所属虚拟活动、受影响状态包和下游活动列表
  - 选中状态的状态包成员覆盖摘要
  - 影响路径节点和边高亮
  - 创建绑定
  - 更新选中绑定
  - 绑定列表
  - 覆盖快照面板
  - 覆盖刷新和删除绑定
- [x] 底部校验与求解预检区：
  - 建模校验
  - 求解器准备校验
  - 校验问题建议操作展示
  - 求解预检
  - 阻塞项定位和覆盖刷新

## Verification

- `npm run build`
- Browser artifacts:
  - `output/network-editor-coverage-stale.png`
  - `output/network-editor-coverage-refreshed.png`
  - `output/network-editor-issue-navigation.png`
  - `output/network-editor-ready-flow.png`
  - `output/network-editor-state-reference.png`
  - `output/network-editor-solver-ready-mode.png`
  - `output/network-editor-impact-analysis.png`
  - `output/network-editor-depth-controls.png`
  - `output/network-editor-virtual-containers.png`
