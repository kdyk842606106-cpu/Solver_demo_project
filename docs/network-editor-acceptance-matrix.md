# 网络编辑器需求验收矩阵

> 适用版本：V0.3 Beta 网络编辑器
> 来源：`docs/状态活动网络图编辑器_需求设计文档.md` 第 17 节 MVP 范围及第 12/13/14/16/19 节关键规则
> 更新日期：2026-07-16

> 2026-07-16 状态更新：X6 单白板画布、容器投影、嵌套自动布局、状态转移 relay/proxy 投影和统一提交均已落地。2026-06-25 关于“后续重构”的描述已完成，不再作为待办。

> 2026-06-30 决策更新：TICKET-057 将普通业务入口从“活动层级 + 全量状态活动边”调整为默认 `状态转移` 视图。该视图是前端投影层 MVP，仍复用后端 `view_mode: "implementation"`、现有绑定语义和统一提交协议；旧全图通过测试/调试开关保留。

## 1. MVP 范围验收

| 需求项 | 当前状态 | 主要证据 |
| --- | --- | --- |
| 状态树 | 已实现 | `NetworkEditorWorkspace.vue` 左侧状态树；`getStateNodes`；`buildHierarchyTree`。 |
| 活动树 | 已实现 | `NetworkEditorWorkspace.vue` 左侧活动树；`getActivityNodes` / `getAtomicActivities` / `getActivityPackageAtomicRefs`；`buildActivityResourceTree` 会把二级包下原子活动引用显示为原子条目。 |
| X6 单白板画布 | 已实现 | `NetworkEditorX6Canvas.vue` 使用单个 X6 graph 实例承载状态、引用实例、状态包/活动包容器、原子活动、relay 和语义边；普通业务入口默认显示状态转移投影，全图保留为调试入口。 |
| 自由白板节点位置、容器尺寸与容器内部自由布局 | 已实现 | 节点、引用实例和容器布局统一进入草稿；状态包/活动包可展开为嵌套容器，容器整体移动会带动内部节点，内部节点可独立移动，取消编辑恢复已提交布局。 |
| 自动布局与节点防重叠 | 已实现 | `networkEditorAutoLayout.js` 提供容器感知的自底向上 ELK 布局、深层边代理、宽容器压缩、relay 布局和失败回退；结果只进入布局草稿并通过统一提交持久化。 |
| 预览模式 / 编辑模式切换 | 已实现 | 前端默认显示 `预览模式`；没有点击 `进入编辑` 时，页面只读取和预览已提交数据，不是半编辑态或自动保存态；只有点击 `进入编辑` 后才打开临时编辑会话，并启用新增、编辑、删除、连线、刷新覆盖、布局调整、容器尺寸调整和状态包成员维护；预览模式下这些入口禁用或隐藏并由函数入口二次拦截，状态包节点保留 `展开/折叠` 但不显示 `添加状态` 写入口，`queueDraftChange` 中心草稿入口也会拒绝非编辑态写入；提交成功、取消编辑、刷新或切换设备后结束编辑会话并回到预览模式；`frontend/e2e/tests/network-editor.spec.ts` 覆盖预览态只读、预览态展开/折叠、预览态隐藏状态包写入口、进入编辑后写入口启用、无草稿时统一提交禁用、取消编辑恢复预览和抽屉保存仅入草稿。 |
| 编辑草稿、取消编辑、统一提交 | 已实现 | 前端 `draftChanges` 记录草稿并在左侧 `编辑草稿` 列表显示；用户进入编辑模式后才能编辑画板，单步保存、拖动、连线、刷新覆盖、自动整理和同步/分叉只进入草稿，不直接写库；`统一提交` 是编辑会话唯一写库动作，会先以 `allow_warnings=false` 调用 `network-editor/commit` 做提交预检，状态/活动层级环、引用环等结构性建模 error 会回滚并保留草稿；求解准备 error 和 warning 会弹出 `提交前复核`，列出最多 5 条中文问题摘要和建议，用户确认后再以 `allow_warnings=true` 正式保存；成功后清空草稿并回到预览模式；取消编辑和编辑态刷新都会用 `丢弃草稿 / 返回编辑` 确认，清空布局草稿并重新加载已提交图；`network-editor.spec.ts` 已收集取消编辑路径和“状态抽屉保存不触发 commit、点击统一提交才调用 `network-editor/commit`”用例。 |
| 编辑会话基线与并发冲突 | 已实现 | `network-editor/graph` 返回内容 revision；前端进入编辑时记录 `base_revision`，统一提交时随草稿传给后端；后端提交前重新计算当前 revision，不一致则返回 409，草稿不应用，前端保留草稿并提示用户刷新或取消后重来。 |
| 节点右键 / 更多菜单 | 已实现 | 画布状态和活动节点支持右键菜单；状态菜单提供设为状态焦点、编辑状态、向状态包添加状态；活动菜单提供设为活动焦点、虚拟活动专注、编辑活动和添加内部活动/原子活动；写操作仍受编辑模式和 `canMutate` 控制。 |
| 生产构建与本地预览入口 | 已实现 | 后端 `/` 优先服务 `frontend/dist/index.html` 和 `/assets/*`，没有生产构建时回退到 Vite 源码入口；`frontend/package.json` 提供 `npm run preview:api`，服务 `frontend/dist` 并把 `/api/*` 代理到后端，`--backend` / `--port` 可覆盖备用端口。 |
| 浏览器可测性与隐藏 DOM 控制 | 已实现 | `NetworkEditorWorkspace.vue` 为顶部工具栏、资源区、画布、属性区、校验区、问题表、抽屉/弹窗、关键按钮、状态/活动节点和容器补 `data-testid`；建模校验、求解器准备和求解预检阻塞项的定位/刷新按钮携带 `data-issue-code`；5 个 `el-segmented` 控件补 `aria-label`；状态、虚拟活动、原子活动抽屉，以及重复状态、共享状态包修改、批量绑定弹窗启用 `destroy-on-close`，避免隐藏表单 DOM 污染浏览器文本抽取；`network-editor.spec.ts` 以 mock API 打开真实页面并验证关键状态机、SVG 线标签、状态包/虚拟活动容器隔离、容器整体移动和虚拟活动专注画布预览态。 |
| 工作区布局、求解视图说明与设备选择器 | 已实现 | 网络编辑器工作区新增内部滚动容器，左侧资源区、右侧属性区和底部校验 / 求解预检区各自滚动，画布在中间区域内伸缩以改善 720px 高度下的可见性；画布动作条提供缩小、百分比重置和放大控件，`Ctrl/Alt + 滚轮` 也可缩放，缩放仅影响查看比例，画布滚动承担平移查看，不进入编辑草稿；`solver_ready` 视图画布顶部显示求解投影说明，避免用户误判虚拟活动消失；设备类型选择器继续支持搜索，并按最近使用、业务设备类型、测试 / 样例设备类型分组，切换设备类型时记录最近 5 个使用项。 |
| 默认状态转移视图 | 已实现 | 顶部 `implementation` 视图的可见标签改为 `状态转移`，后端请求值保持 `implementation`；默认画布以状态卡为骨架，卡片显示达成活动、前置状态计数和缺达成/多达成/多产出/状态包目标等关系提示；活动节点和边默认隐藏，只在选中目标状态或相关达成活动时展开诊断路径。旧全量状态/活动图仅通过 `?networkEditorFullGraph=1` 或 localStorage `network-editor-full-graph=1` 保留给回归和调试。 |
| 状态转移右侧建模 | 已实现 | 选中状态后右侧显示 `状态转移` 详情，按目标状态、达成活动、前置状态组织；编辑模式下可选择已有原子活动作为达成活动，或创建新的达成活动，并把 `activity_state_binding` 草稿写为 `output`；可追加前置状态并写为 `input` 草稿，状态包前置默认覆盖当前启用原子状态；可移除前置状态，已提交绑定排入 `delete` 草稿，新建未提交绑定则直接撤销草稿，状态转移投影会立即隐藏该前置。 |
| 前端请求去重与影响分析防抖 | 已实现 | `frontend/src/api/masterData.js` 中 `getMachineTypes` 增加共享缓存和 in-flight 请求合并，多个数据管理子页面并发请求时复用同一请求；`createMachineType` / `updateMachineType` / `deleteMachineType` 成功后清缓存。`NetworkEditorWorkspace.vue` 中影响分析自动刷新增加短防抖和请求序号保护，快速切换节点、焦点或图投影时旧响应不会覆盖新选择；顶部 `影响分析` 手动按钮保持即时刷新。 |
| 缺规则问题跳转活动能力 | 已实现 | 建模校验、求解器准备和求解预检阻塞项中的规则类问题行会显示 `规则` 动作；点击后先定位相关状态/活动/绑定对象，再通过 `open-workspace` 事件把数据管理页签切到 `活动能力`，方便为相关原子活动创建、启用或明确选择规则。 |
| 核心操作中文化 | 已实现 | 状态/虚拟活动/原子活动抽屉、顶部和资源区新建入口、画布节点摘要、容器摘要、绑定角色、覆盖状态、校验/预检状态、影响分析、求解预检摘要、阻塞项定位/刷新、端口拖线提示、状态包/跨层级语义线短标签、常见校验提示和统一提交复核提示均使用中文文案；右侧状态详情空归属显示 `未加入状态包`，网络编辑器加载失败、草稿入队失败等异常兜底提示为中文；建模校验、求解器准备、求解预检阻塞项表格和提交前 warning 复核以中文级别、中文问题类型、用户可读说明和建议展示，未知 issue code 使用中文通用建议，不直接透出后端英文 `suggested_action`；保留 `feature_key`、`/solve/layered`、问题 code 等必要技术字段用于接口协议和排查。 |
| 状态多选浮动工具条创建活动 | 已实现 | 编辑模式下 `Ctrl` / `Shift` / `Cmd` 点击状态节点进入多选，画布显示 `已选 / 前置 / 产出` 浮动工具条；用户可把当前多选批次标记为前置或产出，节点以不同底色提示角色；点击 `创建虚拟活动` 只打开虚拟活动管理包抽屉，不预填或生成状态绑定；点击 `创建原子活动` 会打开原子活动抽屉并预填 `input/output`，保存后仍进入 `draftChanges`，由 `统一提交` 一次性落库。 |
| 状态节点创建、编辑、删除 | 已实现 | 前端 `新建状态`、`编辑选中`、`删除状态本体` 在编辑模式下写入草稿；编辑模式下状态节点自身提供 `编辑` 快捷入口，状态包节点提供 `添加状态` 快捷入口并给新成员默认布局落点；状态抽屉可维护 `编码`，留空自动生成，编辑时支持改码；成员引用关系在状态包成员表中使用 `移除引用`，不会被误写成删除真实状态；统一提交时通过后端 state-node CRUD 校验。 |
| 活动节点创建、编辑、删除 | 已实现 | 前端 `新建虚拟活动` / `新建原子活动`、`编辑选中`、`删除虚拟活动` / `删除原子活动` 在编辑模式下写入草稿；虚拟/原子活动抽屉可维护 `编码` 和 `说明`，编码留空自动生成，编辑时支持改码；说明字段落到 `activity_node.description` / `atomic_activity.description`，新建原子活动时同批默认规则也沿用该说明；统一提交时通过后端 activity-node / atomic-activity CRUD 校验。 |
| 资源树中新建状态包成员/子活动后画布同步可编辑 | 已实现 | 左侧状态包、一级活动、二级活动包行内加号分别预填所在状态包或活动包；保存抽屉后进入草稿，统一提交成功后复用 `loadAll` 刷新资源树和图投影。 |
| 状态包成员基线维护 | 已实现 | 底层兼容字段 `state_node.parent_id` 作为默认所在状态包，前端表单显示为 `所在状态包`，不向用户表达层级所有权；后端 `_validate_state_parent`、state-node CRUD 继续拒绝危险重挂；若编辑已有状态时改动会把状态加入或移出已被复用的状态包，前端阻止在抽屉中直接保存，并提示改用 `状态包成员` 表的添加/移除引用入口走同步/分叉确认。 |
| 同一状态多状态包出现显示 | 已实现 | `state_node_reference`、引用 CRUD、画布 `引用` 标记、影响分析中的其他出现位置；`network-editor/graph` 会为引用实例输出带 `reference_id` 的独立图节点，引用实例布局保存到 `state_node_reference.metadata_json`，不会污染真实状态本体布局；聚焦状态包时，指向该真实状态的语义边会重定向到当前状态包内的引用实例端点，并保留 `canonical_source_id` / `canonical_target_id` 供语义校验继续按真实状态运行；成员引用参与局部展开、状态包覆盖、分层目标展开和 health check。 |
| 新建状态重复识别与复用 | 已实现 | 前端保存新状态前按编码、名称和相似名称识别候选；复用身份主要由同名决定，编码完全相同也视为明确复用信号；`feature_key/operator/target_value` 只表达状态维度、二元取值和分类，不作为自动复用依据。只有一个编码或名称强匹配候选时自动复用并提示 `已发现相同状态，将复用`；仅名称相似时弹出候选对话框，可选择 `复用选中状态` 或 `仍然新建`；复用时通过 `state_node_reference` 草稿把已有状态加入当前状态包。 |
| 被复用状态包同步 / 分叉 | 已实现 | 修改已被其他状态包复用的状态包成员时弹出 `共享状态包修改确认`，并在确认前展示本次新增/移除成员、受影响状态包、保持不变的状态包、相关绑定数量和当前覆盖缺口；选择同步则直接修改共享状态包成员；选择分叉则提交 `state_package_fork`，分叉必须带分支名称和说明，后端统一提交会拒绝缺少名称或说明的请求；后端复制原状态包直接成员、创建分支，新增成员时加入新增/复用状态，移除成员时跳过被移除成员，并可替换当前使用方。 |
| 折叠状态包节点摘要 | 已实现 | 画布状态包节点显示 `成员`、`深度`、`活动`、`覆盖 已覆盖/当前原子状态` 和绑定数量，覆盖成员数、深度、覆盖和关联活动摘要。 |
| 虚拟活动与原子活动区分 | 已实现 | level 1/2 `activity_node` 为虚拟活动管理包，不允许直接绑定状态；`atomic_activity` 为原子活动，仅允许 `input` / `output` 绑定；前端绑定表单和后端 API 均按该角色矩阵拦截；solver-ready 视图隐藏虚拟活动。 |
| 虚拟活动展开为容器 | 已实现 | 虚拟活动折叠为 X6 节点，展开后投影为活动容器；容器内部仅显示子虚拟活动和原子活动，不接纳状态。历史 `context_input/declared_output` 仅兼容展示。 |
| 虚拟活动专注画布入口 | 已实现 | 虚拟活动节点显示 `专注` 入口并支持双击进入；预览模式下也可进入专注画布查看层级上下文，但不打开编辑会话、不产生草稿；进入后设置 `activity_scope_node_ids` 和完整活动展开深度，顶部专注条显示活动面包屑；虚拟活动容器在专注画布中仍只显示活动节点，不接纳输入或输出状态；一级/二级虚拟活动在编辑模式下分别提供内部 `子活动` / `原子` 创建入口。 |
| 状态包绑定 | 已实现 | `activity_state_binding.binding_type = state_package`；聚合状态绑定投影为状态包。 |
| 状态包覆盖快照 | 已实现 | `covered_leaf_state_ids`、`coverage_policy=snapshot`、`coverage_status`。 |
| 新增状态包成员后的覆盖缺口提示 | 已实现 | 绑定返回前按 active leaves 重算 `complete/partial/stale`；校验返回覆盖缺口；右侧覆盖面板和状态包节点高亮。 |
| 局部展开/折叠 | 已实现 | 默认显示为 `状态深度 = 1`、`活动深度 = 2`；接口仍使用 `state_depth`、`activity_depth`；顶部提供 `聚焦选中`、`折叠选中`、`展开一层`、`展开全部`、`清除焦点`；状态包和虚拟活动节点右上角提供 `展开 / 折叠`，预览模式也可使用，只改变图焦点和深度，不打开编辑会话、不写入草稿；`network-editor.spec.ts` 覆盖预览态状态包与虚拟活动展开后仍停留预览模式，并验证展开后状态包/虚拟活动容器不互相混入节点类型。 |
| 纲要/不完整模型暂不可求解标记 | 已实现 | 前端求解就绪状态条按 `validation_summary.blocking_count`、求解器问题和建模提示显示 `暂不可求解` / `提交/求解前需复核` / `求解输入就绪`。 |
| 基础校验 | 已实现 | 孤立节点、缺输入/输出、重复状态名、跨层级绑定、多状态包出现提示、多 provider、结构环等。 |
| 虚拟活动管理包校验 | 已实现 | 虚拟活动仅作为管理包和分组元数据，不直接绑定状态，不再生成 `VIRTUAL_OUTPUT_NOT_IMPLEMENTED`；`VIRTUAL_ACTIVITY_NOT_DECOMPOSED` 仍用于提示空包或未分解包。 |
| 求解器准备校验 | 已实现 | `network-editor/validate` 合并图预检、`layered-expansion` 和 `layered-health-check`；求解准备 error 会阻止求解预检 ready 和求解读取，但允许用户在提交前复核后保存建模中的图；结构性建模 error 仍阻止统一提交；前端问题表将 issue code/message/suggested_action 映射为中文问题、说明和建议，并显示相关状态/活动/绑定对象。 |
| 求解预检 | 已实现 | 正式接口 `network-editor/solver-precheck` 输出 executable activities、自身输入/输出、聚合规则、虚拟 group 元数据、`/solve/layered` 请求模板摘要；旧 `network-editor/export-preview` 仅作为兼容别名保留；请求模板携带 `model_status`、`solver_handoff_ready` 和阻塞项数量，`blocked` 时页面标记为“仅预检摘要”，不可误当成可直接求解输入；前端显示为 `求解预检`，不再提供独立 JSON 或求解模板下载。 |
| `/solve/layered` 请求模板可补齐 | 已实现 | 未选择目标状态时，模板将 `target_state_node_ids` 放入 `required_runtime_fields`；未选择活动范围时，模板推断有可执行后代的顶层活动 scope，避免空候选活动请求。 |

## 2. 关键规则验收

| 规则 | 当前状态 | 主要证据 |
| --- | --- | --- |
| 保持 canonical 求解底座 | 已实现 | 图编辑语义层经 `统一提交` 写入 `state_node`、`activity_node`、`atomic_activity`、`op_rule`；绑定更新不允许跨 `machine_type_id` 移动；Planner/Scheduler 主链路未替换。 |
| 状态-活动-状态二部结构 | 已实现 | 绑定角色投影为 `STATE_TO_ACTIVITY` 或 `ACTIVITY_TO_STATE`，活动不直接依赖活动。 |
| 语义端口连线 | 已实现 | 编辑模式下状态和原子活动节点显示左右语义端口；右侧端口发起拖线，左侧端口接收拖放；画布动作条按预览模式、无选择、只选状态、只选活动、状态+活动双选和拖拽中状态显示不同下一步提示；松手后预填右侧绑定表单并弹出端点、角色、规则、覆盖范围确认，确认后才创建草稿；状态包绑定确认框支持 `全部当前成员` 或 `选择部分成员`，部分成员在右侧覆盖控件勾选原子状态后再创建；原子活动只使用启用规则，没有启用规则时提示前往活动能力或规则维护创建并启用 `op_rule`，多条启用规则时要求先选规则；状态右端口到原子活动左端口创建 `input`，原子活动右端口到状态左端口创建 `output`；虚拟活动仅作为管理包，不能直接绑定状态；历史 `context_input/declared_output` 夹具只作为兼容数据渲染，并在标签中标注历史口径。 |
| 复杂连线降噪 | 已实现 | 前端渲染层保留真实 `visibleEdges` 不变，新增 `renderedEdges` 只控制画法；活动输入或输出超过 5 条时默认渲染为 `N 个输入` / `N 个输出` 汇总曲线；点击汇总线会选中对应活动并展开具体边，选中相关活动、相关状态或影响分析路径时也会展开具体边；具体边使用端口 lane offset 上下错开，避免同端点多线完全重叠。 |
| 状态转移一对一达成关系 | MVP 已实现 | 前端按 `ACTIVITY_TO_STATE` 且 `binding_role=output` 推导目标状态的达成活动，并按同一原子活动的 `STATE_TO_ACTIVITY` / `input` 绑定汇总前置状态；一个目标状态通常对应一个达成活动、一个达成活动通常只输出一个目标状态。当前 MVP 对缺失、多达成、多产出和状态包目标只给出提示，不做后端强校验，也不改变 solver 读取规则。 |
| 已选原子活动批量连线 | 已实现 | 右侧 `批量绑定` 对话框可对当前选中的原子活动一次选择多个输入状态和多个产出状态，批量生成 `activity_state_binding` 创建草稿并沿用启用规则选择；重复的已有绑定或草稿绑定会跳过；批量状态包绑定默认使用全部当前启用原子状态，partial 覆盖由单条绑定表单处理。虚拟活动不提供批量状态绑定入口。 |
| 新建虚拟活动管理包 | 已实现 | 新建虚拟活动抽屉只创建 `activity_node(level 1/2)` 管理包草稿，不选择输入/产出状态，不追加 `activity_state_binding` 草稿；从多选状态工具条创建虚拟活动时，已选状态不会被直接绑定。 |
| 新建原子活动自动生成规则与连线 | 已实现 | 新建原子活动抽屉要求至少选择一个 `输入状态` 和一个 `产出状态`，否则不允许保存到草稿；产出状态能转换为 effect fact 时，前端同批排入 `atomic_activity`、`op_rule`、`activity_state_binding` 草稿，并用 `_draft_ref` 串联；产出状态暂时不能转换为 effect fact 时，前端按“待补规则”创建原子活动和 `input/output` 绑定草稿但不创建 `op_rule`，后端允许零启用规则的原子活动绑定 `op_rule_id=null`，统一提交确认后可保存模型，求解预检以 `EXECUTABLE_MISSING_RULE` 阻塞；产出包含多个原子状态的状态包时抽屉要求选择 `全部当前成员` 或 `选择部分成员`，partial 模式必须勾选原子状态。 |
| 状态包成员 DAG | 已实现 | `state_node.parent_id` 作为兼容的默认成员关系，`state_node_reference` 表达额外出现位置；成员引用环被拒绝并可预检；显示 DAG 用于网络编辑器投影、状态包原子状态展开、覆盖快照和分层目标展开。 |
| 状态包 = AND(直接成员状态) | 已实现 | 求解预检 `state_aggregation_rules` 固定 `aggregation_rule=AND`。 |
| 状态包绑定解释为成员覆盖 | 已实现 | 聚合状态绑定默认 `binding_type=state_package`，solver-ready 视图展开为覆盖原子状态；成员引用下的原子状态也纳入该状态包覆盖。 |
| 新增状态包成员不自动扩展旧覆盖 | 已实现 | 旧绑定保持 `covered_leaf_state_ids`，新增启用原子状态后覆盖状态变为 `stale/partial`。 |
| 虚拟活动不参与求解 | 已实现 | solver-ready 图只保留 executable activity；求解预检把虚拟活动作为 group/WBS metadata 保留。 |
| 原子活动参与求解器执行 | 已实现 | 原子活动绑定 `op_rule` 后同步 precondition/effect；求解交接只把原子活动作为执行单元。 |
| 手写规则事实保护 | 已实现 | 绑定层用 `metadata_json._network_editor_managed_rule_facts` 记录接管的 facts；删除 binding 不会清理原本手写在 `op_rule` 上的同名 precondition/effect。 |
| 虚拟活动不直接绑定状态 | 已实现 | 后端拒绝对 `activity_node(level 1/2)` 创建新的状态绑定；solver-ready 投影和求解预检不再把虚拟活动 `context_input/declared_output` 解释为原子活动输入/输出或继承前置。 |
| 跨层级绑定允许但标记 | 已实现 | `CROSS_LEVEL_BINDING_NOTICE` 和 `CROSS_LEVEL_BINDING_MANY`；前端活动节点显示 `跨层级 N` 节点级跨层级绑定数量；跨层级线在画布上显示 `输入 / 跨层级`、`状态包输入 / 跨层级` 等中文短标签，状态包绑定显示 `状态包输入` 或 `状态包产出`；历史 `context_input/declared_output` 标签带历史前缀。 |
| 反向/返工活动显式建模，不自动回滚 | 已实现 | 编辑器允许普通 input/output 绑定；无自动状态失效推导。 |
| GraphEdge 不持久化 | 已实现 | Graph edge 为响应投影对象；核心持久表仍为绑定层。 |

## 3. 校验覆盖

| 校验项 | 建模校验 | 求解器准备校验 |
| --- | --- | --- |
| 孤立状态 / 活动 | `ORPHAN_STATE` / `ORPHAN_ACTIVITY` | 非阻断摘要。 |
| 活动缺少前置 / 产出 | `ACTIVITY_MISSING_INPUT` / `ACTIVITY_MISSING_OUTPUT` | 原子活动对应 `EXECUTABLE_MISSING_INPUT` / `EXECUTABLE_MISSING_OUTPUT` 阻断。 |
| 原子活动规则不可用 | - | `EXECUTABLE_MISSING_RULE` / `EXECUTABLE_RULE_NOT_EXPLICIT` / `EXECUTABLE_RULE_AMBIGUOUS` / `EXECUTABLE_RULE_BINDING_INVALID` error；默认 solver-ready 图和求解预检只使用启用 `op_rule`，只有停用规则或待补规则的原子活动不会被自动填入 `op_rule_id`；待补规则模型可保存，但求解预检保持 blocked。 |
| 停用状态事实进入覆盖快照 | - | 默认 solver-ready 图和求解预检只交接启用原子状态事实；覆盖快照残留停用原子状态时，`own_preconditions` / `own_effects` / `inherited_preconditions` 会过滤停用状态，`include_inactive=true` 时可审计。 |
| 状态聚合环 | `STATE_AGGREGATION_CYCLE` | 同码 error 阻断。 |
| 活动容器环 | `ACTIVITY_CONTAINER_CYCLE` | 同码 error 阻断。 |
| 状态包成员引用环 | `STATE_REFERENCE_CYCLE` | 同码 error 阻断。 |
| 状态-活动依赖环 | - | `GRAPH_DEPENDENCY_CYCLE` error。 |
| 状态包覆盖缺口 | `BINDING_COVERAGE_NOT_COMPLETE` warning | 同码 error。 |
| 虚拟活动未分解 | `VIRTUAL_ACTIVITY_NOT_DECOMPOSED` warning | 仅提示管理包下没有可执行原子活动，不再与声明输出实现完整性绑定。 |
| 虚拟活动输出实现完整性 | 历史口径 | `VIRTUAL_OUTPUT_NOT_IMPLEMENTED` 已废止，虚拟活动不再声明输出；输入/产出应绑定到原子活动。 |
| 重复状态名称 | `DUPLICATE_STATE_NAME` warning | 非阻断质量提示。 |
| 跨层级绑定提示 | `CROSS_LEVEL_BINDING_NOTICE` info | `CROSS_LEVEL_BINDING_MANY` warning。 |
| 不可达前置 / 未产出必要状态 | - | 复用 `layered-health-check` 的 `BROKEN_CHAIN` / `NO_PROVIDER`；诊断会映射回真实状态或 `atomic_activity:*` 图节点，底部问题表可定位，不可见节点会自动展开后选中；目标停用、目标无原子状态、活动范围无原子活动等 `layered-expansion` 诊断也会带上 `node_id/node_type`；前端在缺少 `related_*` 时会用 `details.node_type/node_id`、`activity_node_id`、`state_node_id` 或 `op_rule_id` 兜底定位。 |
| 多个活动产出同一状态 | - | `MULTIPLE_OUTPUT_PROVIDERS` warning。 |
| 产出状态没有下游使用 | - | `OUTPUT_STATE_UNUSED` warning，目标状态豁免。 |
| 状态包覆盖范围过大 | - | `STATE_PACKAGE_COVERAGE_LARGE` warning。 |
| 活动参与求解标记错误 | - | `ACTIVITY_SOLVER_PARTICIPATION_MISMATCH` error。 |

## 4. 影响分析与统计

| 需求项 | 当前状态 | 主要证据 |
| --- | --- | --- |
| 选择状态显示上游/下游/所在状态包/其他出现位置 | 已实现 | `network-editor/impact` state 分支；右侧影响分析面板显示所在状态包路径和其他出现位置。 |
| 选择状态显示成员覆盖和包绑定使用 | 已实现 | `child_coverage`、`package_bindings`。 |
| 选择状态显示影响的虚拟/原子活动 | 已实现 | `affected_virtual_activities`、`affected_executable_activities`。 |
| 选择活动显示直接前置/产出 | 已实现 | `direct_precondition_states`、`output_states`；`inherited_precondition_states` 保留兼容字段，新口径不再由虚拟活动上下文继承生成。 |
| 选择活动显示所属虚拟活动、受影响状态包、下游活动、求解参与 | 已实现 | `owner_virtual_activities`、`affected_parent_states`、`downstream_activities`、`participates_in_solver`。 |
| 停用活动包引用的所属虚拟活动过滤 | 已实现 | 默认影响分析的 `owner_virtual_activities` 只按 active `activity_package_atomic_ref` 计算；`include_inactive=true` 时可审计停用挂载。 |
| 顶部影响分析入口 | 已实现 | 选中状态或活动后可点击顶部 `影响分析` 手动重新拉取影响路径；选中节点仍会自动刷新右侧影响分析面板。 |
| 影响路径高亮 | 已实现 | 前端 `impactHighlights` / `isImpactEdge`。 |
| 网络分布与深度统计 | 已实现 | 图摘要包含状态/活动数量、虚拟/原子活动数量、最大状态/活动深度、最长依赖链、孤立节点、覆盖缺口、跨层级绑定；活动节点显示 `跨层级 N` 局部数量。 |

## 5. 明确不做

以下内容与需求文档第 17/18 节一致，仍不属于当前 MVP：

- 工期维护。
- 资源维护。
- 成本维护。
- 自动排程引擎或自动排程重做。
- 自动状态回滚或自动状态失效。
- OR / CUSTOM 聚合规则。
- 自动生成三级活动或原子活动。
- 自动优化网络结构。
- 替代现有高级规则维护入口。

## 6. 当前验证

- 2026-07-16 后端全量：`.venv\Scripts\python.exe -m pytest -q` — 365 passed。
- 2026-07-16 Chromium 全量：86 passed；其中网络编辑器两个 spec 共收集并通过 67 条用例。
- 网络编辑器覆盖状态转移 relay/proxy、状态包 coverage、嵌套容器、ELK 自动布局与回退、预览/编辑状态机、统一提交、引用复用、状态创建和完整全图建模流。
- `npm.cmd run build` — passed，仅保留既有 Vite chunk-size warning。
- `python scripts/check_terminology.py` 与 `git diff --check` — passed。

## 7. 证据索引

后续审计优先从以下锚点进入，避免只凭口头描述判断完成度。前端工作区文件体量较大，行号会随 UI 文案和模板微调漂移；前端证据以 `data-testid`、函数名、API 调用名和 e2e 用例名为稳定锚点。

| 证据主题 | 文件锚点 |
| --- | --- |
| 状态包成员、引用和绑定校验 | `app/api/v1/master_data.py` 的 `_validate_state_parent`、`_validate_state_reference`、`_resolve_binding_payload`。 |
| 草稿模型与统一提交 | `app/db/schemas.py` 的 `NetworkEditorDraftChange` / `NetworkEditorCommitRequest`；`app/api/v1/master_data.py` 的 `commit_network_editor_draft` 与 `_create_state_package_fork`。 |
| 图投影、深度过滤与 canonical 端点 | `app/services/network_editor.py` 的 `_filter_graph`、`_build_graph_from_context`、`_validate_projected_graph`。 |
| 影响分析与求解预检 | `app/services/network_editor.py` 的 `analyze_network_editor_impact`、`precheck_network_editor_solver`；`app/db/schemas.py` 的 `NetworkEditorSolverPrecheckResponse`。 |
| 前端预览/编辑与草稿队列 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `startEditSession`、`queueDraftChange`、`submitDraftChanges` 及稳定 `data-testid`。 |
| X6 单画布与容器投影 | `frontend/src/views/DataManagement/components/NetworkEditorX6Canvas.vue`；`NetworkEditorWorkspace.vue` 的 cell 投影和布局草稿桥接。 |
| 容器感知自动布局 | `frontend/src/views/DataManagement/networkEditorAutoLayout.js` 的嵌套布局、深层边代理、容器尺寸、relay 和失败回退。 |
| 网络编辑器后端集成回归 | `tests/integration/test_master_data_api.py` 中 8 条 `test_network_editor_*` 用例，覆盖加载、深度过滤、统一提交、draft ref、ID 归一化、revision 冲突、复核回滚和模板状态复用。 |
| 网络编辑器浏览器回归 | `frontend/e2e/tests/network-editor.spec.ts` 与 `network-editor-full-flow.spec.ts`；共 67 条并包含在 86 passed 的 Chromium 全量回归中。 |
| 当前需求与操作说明 | `docs/状态活动网络图编辑器_需求设计文档.md`、`docs/network-editor-user-guide.md`；历史设计冻结材料仅用于追溯。 |

## 8. 关键设计结论逐条覆盖审计

该表对齐需求文档第 19 节 40 条关键设计结论。审计结论基于当前代码、验收矩阵和已通过回归；预览/编辑状态机、预览态展开/折叠、虚拟活动专注画布、状态包/虚拟活动容器隔离、编辑态容器整体移动与语义线标签已有 `network-editor.spec.ts` 浏览器回归，其他显示/交互大改后仍建议继续补针对性浏览器复核。

| 编号 | 关键结论 | 覆盖证据 |
| --- | --- | --- |
| 1 | 编辑器服务于全流程集成场景 | 求解预检、状态包聚合、虚拟 group 元数据、数据库交接和 `/solve/layered` 模板摘要已覆盖。 |
| 2 | 编辑器不仅可视化，还能直接编辑模型 | 预览/编辑模式、草稿队列、统一提交 API、状态/活动/绑定 CRUD 草稿均已实现。 |
| 3 | 服务求解器输入维护，并通过既有数据库接口对接求解链路 | 不导出独立文件；统一提交写 canonical 表；求解预检标记数据库交接就绪。 |
| 4 | 状态本体全局唯一，不携带层级所有权关系 | 状态包成员通过 `state_node_reference` 表达额外出现；界面收口为“所在状态包/引用”。 |
| 5 | 状态包是命名状态集合，通过成员引用聚合状态 | 状态树、状态包成员表、引用 CRUD、显示 DAG、覆盖快照均基于成员引用。 |
| 6 | 状态包通过全部成员状态 AND 聚合达成 | 求解预检 `state_aggregation_rules` 固定 `aggregation_rule=AND`，同时返回直接成员和原子状态展开。 |
| 7 | 活动必须遵循状态-活动-状态结构 | 绑定投影只生成 `STATE_TO_ACTIVITY` / `ACTIVITY_TO_STATE` 边。 |
| 8 | 活动依赖状态，不直接依赖活动 | GraphEdge 只来自状态-活动绑定；虚拟活动归属通过容器和 group 元数据表达。 |
| 9 | 一个活动可以有多个前置状态和多个产出状态 | 批量绑定、新建虚拟/原子活动自动生成多条绑定草稿。 |
| 10 | 一个状态可以由多个活动产出 | `MULTIPLE_OUTPUT_PROVIDERS` 作为非阻断 warning，允许但提示复核。 |
| 11 | 活动采用节点形式，不作为普通边 | 前端画布分状态节点、虚拟活动节点、原子活动节点和语义边渲染。 |
| 12 | 交互层自由画布，语义层仍落到状态-活动-状态关系 | 布局 metadata 独立保存，业务事实仍写 `activity_state_binding`。 |
| 13 | 边只表达输入/输出，不允许无语义自由线 | 端口拖线和右侧绑定表单都必须选择合法角色；`context_input/declared_output` 只作为历史数据兼容。 |
| 14 | 状态包绑定表示状态包成员状态覆盖范围 | `binding_type=state_package`，覆盖快照记录 `covered_leaf_state_ids`。 |
| 15 | 新增状态包成员后，原有状态包绑定不自动覆盖新增成员 | 旧覆盖保持快照，新增成员后状态变为 `stale/partial`，需刷新覆盖。 |
| 16 | 状态包绑定需要记录覆盖快照 | 模型、API、前端覆盖面板和测试均覆盖 `coverage_status` / `covered_leaf_state_ids`。 |
| 17 | 默认折叠高层节点，支持任意层级展开/收起 | 默认 `状态深度=1`、`活动深度=2`，支持聚焦、折叠、展开一层、展开全部。 |
| 18 | 展开状态包时容器只包含状态引用实例 | X6 状态包折叠为节点、展开为容器，内部只投影状态节点和引用实例；嵌套展开、引用布局和折叠恢复已有浏览器回归。 |
| 19 | 展开虚拟活动时容器只包含子虚拟活动和原子活动 | X6 活动容器内部只投影子虚拟活动和原子活动；上下文和声明输出状态不进入容器。 |
| 20 | 支持状态和活动完全同步 | `loadAll` 同步加载状态、活动、原子活动、引用、绑定和规则，提交成功后重新投影。 |
| 21 | 支持全局自由布局、容器内部自由布局、局部坐标保存和自动整理 | 节点布局、容器尺寸、容器整体移动、引用实例布局和 `自动整理` 均进入草稿后统一提交；浏览器回归验证状态包/虚拟活动容器移动时内部节点跟随，也验证展开状态包内部状态和展开虚拟活动内部原子活动可单独拖动且不拖走容器根节点。 |
| 22 | 状态包成员关系和活动归属不通过业务连线表达 | 成员关系由 `state_node_reference` / 容器 / 资源树 / 属性区表达；业务线只表达状态-活动依赖。 |
| 23 | 状态包成员引用通过实例、角标、资源树、面包屑和属性面板表达 | 画布 `引用` 标记、资源树分组、右侧其他出现位置和活动专注条已覆盖；引用实例独立布局已回归。 |
| 24 | 允许跨层级绑定，但必须显示跨层级或状态包输入/输出提示 | 后端返回跨层级提示；活动节点显示 `跨层级 N`；状态包/跨层级线显示中文短标签。 |
| 25 | 通过选择前置状态和目标状态创建活动，系统生成活动节点和两端语义连接 | 多选状态工具条、新建虚拟活动和新建原子活动同批创建活动与绑定草稿。 |
| 26 | 高层活动作为虚拟活动用于自上而下建模 | level 1/2 `activity_node` 作为虚拟活动，支持内部子活动/原子活动创建。 |
| 27 | 虚拟活动不参与求解器计算 | solver-ready 视图只保留原子活动，虚拟活动仅作为 group/WBS 元数据。 |
| 28 | 虚拟活动可进入专注画布继续分解 | 虚拟活动节点 `专注` 入口和双击进入，专注条显示面包屑、边界状态和实现摘要；浏览器回归验证预览态进入专注画布不产生草稿。 |
| 29 | 专注画布不展示虚拟活动边界状态 | 专注条显示活动面包屑，虚拟活动容器内部仍只含活动；`network-editor.spec.ts` 已补断言：进入专注画布后不显示上下文、输出或实现摘要，也不产生草稿。 |
| 30 | 原子活动作为真正执行单元参与求解器 | `atomic_activity` 绑定 `op_rule` 后进入 solver-ready 图和求解预检。 |
| 31 | 虚拟活动作为管理包，不声明输出 | `VIRTUAL_OUTPUT_NOT_IMPLEMENTED` 已废止，前端不再展示虚拟活动实现覆盖摘要。 |
| 32 | 虚拟活动不提供继承前置 | `context_input` 只作为历史数据兼容，不再在 solver-ready 和求解预检中作为 inherited preconditions。 |
| 33 | 同一状态可在不同状态包下以引用实例形式出现 | `state_node_reference`、引用实例图节点、独立布局和引用端点投影已覆盖。 |
| 34 | 新建状态时自动识别重复状态，优先复用已有状态 | 编码/名称强匹配自动复用；状态维度和二元值只作分类，不触发自动复用；相似名称弹窗选择复用或仍然新建。 |
| 35 | 修改已被引用状态包成员时必须选择同步或分叉 | `共享状态包修改确认` 和后端 `state_package_fork` 约束覆盖。 |
| 36 | 同步影响所有引用方；分叉创建分支并保持其他引用方不变 | 分叉复制成员、替换当前使用方引用，其他引用方保持原包；回归覆盖新增/移除。 |
| 37 | 默认预览只读；进入编辑后所有变更进入草稿 | `canMutate`、`requireEditMode` 和 `queueDraftChange` 中心入口覆盖。 |
| 38 | 统一提交写库；取消编辑丢弃草稿 | `network-editor/commit` 批量提交；取消/刷新/切换设备回到预览并清草稿；当前网络编辑器 67 条浏览器用例覆盖布局取消恢复、抽屉保存只入草稿及统一提交唯一写库。 |
| 39 | 不导出独立数据文件，提交后由既有数据库接口读取 | 页面无下载 JSON/模板入口；旧 export-preview 仅兼容别名；求解预检只给摘要。 |
| 40 | 需要建模校验和求解器准备校验两套机制 | `network-editor/validate` 同时返回 `modeling_issues` 与 `solver_ready_issues`，提交前按结构性问题和求解准备问题分流。 |
| 41 | 新增用户可见术语必须先进入术语映射表 | 术语规范以 `docs/ANCHOR.md` 的 V0.3 术语分层和主需求文档“术语与技术名映射”为准；新增中文业务名、旧口径兼容名或技术名外显前，必须补充规范业务名、技术名、旧名/别名和适用边界；提交前运行 `python scripts/check_terminology.py`，确认旧口径未回流。 |
