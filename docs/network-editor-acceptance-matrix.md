# 网络编辑器需求验收矩阵

> 适用版本：V0.3 网络编辑器 MVP
> 来源：`docs/状态活动网络图编辑器_需求设计文档.md` 第 17 节 MVP 范围及第 12/13/14/16/19 节关键规则
> 更新日期：2026-06-25

> 2026-06-25 决策更新：网络编辑器画板目标已切换为 X6 单白板画布。当前手写 DOM/SVG 状态-活动二部图壳子和“普通节点 + 容器外框”的展示方式仅作为历史过渡实现保留，后续需按主需求和主设计 spec 重构为 X6 单画布后重新验收前端画板项。

## 1. MVP 范围验收

| 需求项 | 当前状态 | 主要证据 |
| --- | --- | --- |
| 状态树 | 已实现 | `NetworkEditorWorkspace.vue` 左侧状态树；`getStateNodes`；`buildHierarchyTree`。 |
| 活动树 | 已实现 | `NetworkEditorWorkspace.vue` 左侧活动树；`getActivityNodes` / `getAtomicActivities` / `getActivityPackageAtomicRefs`；`buildActivityResourceTree` 会把二级包下原子活动引用显示为原子叶子。 |
| X6 单白板画布 | 待重构 | 目标画布为一个 X6 graph 实例，状态、状态引用、状态包容器、虚拟活动容器、原子活动和语义线共用同一坐标系；不再拆成左右两个图，也不再使用“高层普通节点 + 装饰容器外框”的旧展示。主需求文档和主设计 spec 已记录 X6 单画布目标；当前前端旧实现仍待替换。 |
| 自由白板节点位置、容器尺寸与容器内部自由布局 | 部分实现，待 X6 重构 | 现有手写画板已通过布局手柄、容器移动、容器尺寸和 `network-editor/commit` 草稿提交验证了核心数据路径；最终验收需在 X6 单画布上重新证明：高层对象折叠时是节点、展开时同一对象切换为容器，状态包容器只收状态/引用实例，虚拟活动容器只收虚拟/原子活动，容器内部节点可自由拖动，拖动容器带动内部节点，拖动内部节点不拖动容器根对象。 |
| 自动布局与节点防重叠 | 待迁移 | 旧自动整理按状态/活动分组排布；X6 重构后需改为单画布自动整理，按容器层级、已有坐标和关联关系给出建议布局，整理结果仍只进入布局草稿并通过统一提交持久化。 |
| 预览模式 / 编辑模式切换 | 已实现 | 前端默认显示 `预览模式`；没有点击 `进入编辑` 时，页面只读取和预览已提交数据，不是半编辑态或自动保存态；只有点击 `进入编辑` 后才打开临时编辑会话，并启用新增、编辑、删除、连线、刷新覆盖、布局调整、容器尺寸调整和状态包成员维护；预览模式下这些入口禁用或隐藏并由函数入口二次拦截，状态包节点保留 `展开/折叠` 但不显示 `添加状态` 写入口，`queueDraftChange` 中心草稿入口也会拒绝非编辑态写入；提交成功、取消编辑、刷新或切换设备后结束编辑会话并回到预览模式；`frontend/e2e/tests/network-editor.spec.ts` 覆盖预览态只读、预览态展开/折叠、预览态隐藏状态包写入口、进入编辑后写入口启用、无草稿时统一提交禁用、取消编辑恢复预览和抽屉保存仅入草稿。 |
| 编辑草稿、取消编辑、统一提交 | 已实现 | 前端 `draftChanges` 记录草稿并在左侧 `编辑草稿` 列表显示；用户进入编辑模式后才能编辑画板，单步保存、拖动、连线、刷新覆盖、自动整理和同步/分叉只进入草稿，不直接写库；`统一提交` 是编辑会话唯一写库动作，会先以 `allow_warnings=false` 调用 `network-editor/commit` 做提交预检，状态/活动层级环、引用环等结构性建模 error 会回滚并保留草稿；求解准备 error 和 warning 会弹出 `提交前复核`，列出最多 5 条中文问题摘要和建议，用户确认后再以 `allow_warnings=true` 正式保存；成功后清空草稿并回到预览模式；取消编辑和编辑态刷新都会用 `丢弃草稿 / 返回编辑` 确认，清空布局草稿并重新加载已提交图；`network-editor.spec.ts` 已收集取消编辑路径和“状态抽屉保存不触发 commit、点击统一提交才调用 `network-editor/commit`”用例。 |
| 编辑会话基线与并发冲突 | 已实现 | `network-editor/graph` 返回内容 revision；前端进入编辑时记录 `base_revision`，统一提交时随草稿传给后端；后端提交前重新计算当前 revision，不一致则返回 409，草稿不应用，前端保留草稿并提示用户刷新或取消后重来。 |
| 节点右键 / 更多菜单 | 已实现 | 画布状态和活动节点支持右键菜单；状态菜单提供设为状态焦点、编辑状态、向状态包添加状态；活动菜单提供设为活动焦点、虚拟活动专注、编辑活动和添加内部活动/原子活动；写操作仍受编辑模式和 `canMutate` 控制。 |
| 生产构建与本地预览入口 | 已实现 | 后端 `/` 优先服务 `frontend/dist/index.html` 和 `/assets/*`，没有生产构建时回退到 Vite 源码入口；`frontend/package.json` 提供 `npm run preview:api`，服务 `frontend/dist` 并把 `/api/*` 代理到后端，`--backend` / `--port` 可覆盖备用端口。 |
| 浏览器可测性与隐藏 DOM 控制 | 已实现 | `NetworkEditorWorkspace.vue` 为顶部工具栏、资源区、画布、属性区、校验区、问题表、抽屉/弹窗、关键按钮、状态/活动节点和容器补 `data-testid`；建模校验、求解器准备和求解预检阻塞项的定位/刷新按钮携带 `data-issue-code`；5 个 `el-segmented` 控件补 `aria-label`；状态、虚拟活动、原子活动抽屉，以及重复状态、共享状态包修改、批量绑定弹窗启用 `destroy-on-close`，避免隐藏表单 DOM 污染浏览器文本抽取；`network-editor.spec.ts` 以 mock API 打开真实页面并验证关键状态机、SVG 线标签、状态包/虚拟活动容器隔离、容器整体移动和虚拟活动专注画布预览态。 |
| 工作区布局、求解视图说明与设备选择器 | 已实现 | 网络编辑器工作区新增内部滚动容器，左侧资源区、右侧属性区和底部校验 / 求解预检区各自滚动，画布在中间区域内伸缩以改善 720px 高度下的可见性；画布动作条提供缩小、百分比重置和放大控件，`Ctrl/Alt + 滚轮` 也可缩放，缩放仅影响查看比例，画布滚动承担平移查看，不进入编辑草稿；`solver_ready` 视图画布顶部显示求解投影说明，避免用户误判虚拟活动消失；设备类型选择器继续支持搜索，并按最近使用、业务设备类型、测试 / 样例设备类型分组，切换设备类型时记录最近 5 个使用项。 |
| 前端请求去重与影响分析防抖 | 已实现 | `frontend/src/api/masterData.js` 中 `getMachineTypes` 增加共享缓存和 in-flight 请求合并，多个数据管理子页面并发请求时复用同一请求；`createMachineType` / `updateMachineType` / `deleteMachineType` 成功后清缓存。`NetworkEditorWorkspace.vue` 中影响分析自动刷新增加短防抖和请求序号保护，快速切换节点、焦点或图投影时旧响应不会覆盖新选择；顶部 `影响分析` 手动按钮保持即时刷新。 |
| 缺规则问题跳转活动能力 | 已实现 | 建模校验、求解器准备和求解预检阻塞项中的规则类问题行会显示 `规则` 动作；点击后先定位相关状态/活动/绑定对象，再通过 `open-workspace` 事件把数据管理页签切到 `活动能力`，方便为相关原子活动创建、启用或明确选择规则。 |
| 核心操作中文化 | 已实现 | 状态/虚拟活动/原子活动抽屉、顶部和资源区新建入口、画布节点摘要、容器摘要、绑定角色、覆盖状态、校验/预检状态、影响分析、求解预检摘要、阻塞项定位/刷新、端口拖线提示、状态包/跨层级语义线短标签、常见校验提示和统一提交复核提示均使用中文文案；右侧状态详情空归属显示 `未加入状态包`，网络编辑器加载失败、草稿入队失败等异常兜底提示为中文；建模校验、求解器准备、求解预检阻塞项表格和提交前 warning 复核以中文级别、中文问题类型、用户可读说明和建议展示，未知 issue code 使用中文通用建议，不直接透出后端英文 `suggested_action`；保留 `feature_key`、`/solve/layered`、问题 code 等必要技术字段用于接口协议和排查。 |
| 状态多选浮动工具条创建活动 | 已实现 | 编辑模式下 `Ctrl` / `Shift` / `Cmd` 点击状态节点进入多选，画布显示 `已选 / 前置 / 产出` 浮动工具条；用户可把当前多选批次标记为前置或产出，节点以不同底色提示角色；点击 `创建虚拟活动` 会打开虚拟活动抽屉并预填 `context_input/declared_output`，点击 `创建原子活动` 会打开原子活动抽屉并预填 `input/output`，保存后仍进入 `draftChanges`，由 `统一提交` 一次性落库。 |
| 状态节点创建、编辑、删除 | 已实现 | 前端 `新建状态`、`编辑选中`、`删除状态本体` 在编辑模式下写入草稿；编辑模式下状态节点自身提供 `编辑` 快捷入口，状态包节点提供 `添加状态` 快捷入口并给新成员默认布局落点；状态抽屉可维护 `编码`，留空自动生成，编辑时支持改码；成员引用关系在状态包成员表中使用 `移除引用`，不会被误写成删除真实状态；统一提交时通过后端 state-node CRUD 校验。 |
| 活动节点创建、编辑、删除 | 已实现 | 前端 `新建虚拟活动` / `新建原子活动`、`编辑选中`、`删除虚拟活动` / `删除原子活动` 在编辑模式下写入草稿；虚拟/原子活动抽屉可维护 `编码` 和 `说明`，编码留空自动生成，编辑时支持改码；说明字段落到 `activity_node.description` / `atomic_activity.description`，新建原子活动时同批默认规则也沿用该说明；统一提交时通过后端 activity-node / atomic-activity CRUD 校验。 |
| 资源树中新建状态包成员/子活动后画布同步可编辑 | 已实现 | 左侧状态包、一级活动、二级活动包行内加号分别预填所在状态包或活动包；保存抽屉后进入草稿，统一提交成功后复用 `loadAll` 刷新资源树和图投影。 |
| 状态包成员基线维护 | 已实现 | 底层兼容字段 `state_node.parent_id` 作为默认所在状态包，前端表单显示为 `所在状态包`，不向用户表达层级所有权；后端 `_validate_state_parent`、state-node CRUD 继续拒绝危险重挂；若编辑已有状态时改动会把状态加入或移出已被复用的状态包，前端阻止在抽屉中直接保存，并提示改用 `状态包成员` 表的添加/移除引用入口走同步/分叉确认。 |
| 同一状态多状态包出现显示 | 已实现 | `state_node_reference`、引用 CRUD、画布 `引用` 标记、影响分析中的其他出现位置；`network-editor/graph` 会为引用实例输出带 `reference_id` 的独立图节点，引用实例布局保存到 `state_node_reference.metadata_json`，不会污染真实状态本体布局；聚焦状态包时，指向该真实状态的语义边会重定向到当前状态包内的引用实例端点，并保留 `canonical_source_id` / `canonical_target_id` 供语义校验继续按真实状态运行；成员引用参与局部展开、状态包覆盖、分层目标展开和 health check。 |
| 新建状态重复识别与复用 | 已实现 | 前端保存新状态前按编码、名称、原子状态 `feature_key/operator/target_value` 和相似名称识别候选；只有一个编码/名称/事实强匹配候选时自动复用并提示 `已发现相同状态，将复用`；多个候选或仅相似名称时弹出候选对话框，可选择 `复用选中状态` 或 `仍然新建`；复用时通过 `state_node_reference` 草稿把已有状态加入当前状态包。 |
| 被复用状态包同步 / 分叉 | 已实现 | 修改已被其他状态包复用的状态包成员时弹出 `共享状态包修改确认`，并在确认前展示本次新增/移除成员、受影响状态包、保持不变的状态包、相关绑定数量和当前覆盖缺口；选择同步则直接修改共享状态包成员；选择分叉则提交 `state_package_fork`，分叉必须带分支名称和说明，后端统一提交会拒绝缺少名称或说明的请求；后端复制原状态包直接成员、创建分支，新增成员时加入新增/复用状态，移除成员时跳过被移除成员，并可替换当前使用方。 |
| 折叠状态包节点摘要 | 已实现 | 画布状态包节点显示 `成员`、`深度`、`活动`、`覆盖 已覆盖/当前叶子` 和绑定数量，覆盖成员数、深度、覆盖和关联活动摘要。 |
| 虚拟活动与可执行活动区分 | 已实现 | level 1/2 `activity_node` 为虚拟活动，仅允许 `context_input` / `declared_output` 绑定；`atomic_activity` 为可执行活动，仅允许 `input` / `output` 绑定；前端绑定表单和后端 API 均按该角色矩阵拦截；solver-ready 视图隐藏虚拟活动。 |
| 虚拟活动展开为容器 | 待 X6 重构 | 目标交互为虚拟活动折叠时显示为节点，展开时同一对象切换为 X6 容器；容器内部只显示子虚拟活动和原子活动，不接纳上下文或输出状态。当前 `virtualActivityContainers` 属于历史过渡实现。 |
| 虚拟活动专注画布入口 | 已实现 | 虚拟活动节点显示 `专注` 入口并支持双击进入；预览模式下也可进入专注画布查看层级上下文，但不打开编辑会话、不产生草稿；进入后设置 `activity_scope_node_ids` 和完整活动展开深度，顶部专注条显示活动面包屑、`上下文` 边界状态、`输出` 声明输出和 `实现` 覆盖；虚拟活动容器在专注画布中仍只显示活动节点，不接纳上下文或输出边界状态；一级/二级虚拟活动在编辑模式下分别提供内部 `子活动` / `原子` 创建入口。 |
| 状态包绑定 | 已实现 | `activity_state_binding.binding_type = state_package`；聚合状态绑定投影为状态包。 |
| 状态包覆盖快照 | 已实现 | `covered_leaf_state_ids`、`coverage_policy=snapshot`、`coverage_status`。 |
| 新增状态包成员后的覆盖缺口提示 | 已实现 | 绑定返回前按 active leaves 重算 `complete/partial/stale`；校验返回覆盖缺口；右侧覆盖面板和状态包节点高亮。 |
| 局部展开/折叠 | 已实现 | 默认显示为 `状态深度 = 1`、`活动深度 = 2`；接口仍使用 `state_depth`、`activity_depth`；顶部提供 `聚焦选中`、`折叠选中`、`展开一层`、`展开全部`、`清除焦点`；状态包和虚拟活动节点右上角提供 `展开 / 折叠`，预览模式也可使用，只改变图焦点和深度，不打开编辑会话、不写入草稿；`network-editor.spec.ts` 覆盖预览态状态包与虚拟活动展开后仍停留预览模式，并验证展开后状态包/虚拟活动容器不互相混入节点类型。 |
| 纲要/不完整模型暂不可求解标记 | 已实现 | 前端求解就绪状态条按 `validation_summary.blocking_count`、求解器问题和建模提示显示 `暂不可求解` / `提交/求解前需复核` / `求解输入就绪`。 |
| 基础校验 | 已实现 | 孤立节点、缺输入/输出、重复状态名、跨层级绑定、多状态包出现提示、多 provider、结构环等。 |
| 虚拟活动实现完整性校验 | 已实现 | `VIRTUAL_ACTIVITY_NOT_DECOMPOSED`、`VIRTUAL_OUTPUT_NOT_IMPLEMENTED`；前端虚拟活动节点显示 `实现 已实现/声明`，虚拟活动容器显示 `输出 已实现/声明` 输出覆盖摘要。 |
| 求解器准备校验 | 已实现 | `network-editor/validate` 合并图预检、`layered-expansion` 和 `layered-health-check`；求解准备 error 会阻止求解预检 ready 和求解读取，但允许用户在提交前复核后保存建模中的图；结构性建模 error 仍阻止统一提交；前端问题表将 issue code/message/suggested_action 映射为中文问题、说明和建议，并显示相关状态/活动/绑定对象。 |
| 求解预检 | 已实现 | 正式接口 `network-editor/solver-precheck` 输出 executable activities、继承前置、自身输入/输出、聚合规则、虚拟 group 元数据、`/solve/layered` 请求模板摘要；旧 `network-editor/export-preview` 仅作为兼容别名保留；请求模板携带 `model_status`、`solver_handoff_ready` 和阻塞项数量，`blocked` 时页面标记为“仅预检摘要”，不可误当成可直接求解输入；前端显示为 `求解预检`，不再提供独立 JSON 或求解模板下载。 |
| `/solve/layered` 请求模板可补齐 | 已实现 | 未选择目标状态时，模板将 `target_state_node_ids` 放入 `required_runtime_fields`；未选择活动范围时，模板推断有可执行后代的顶层活动 scope，避免空候选活动请求。 |

## 2. 关键规则验收

| 规则 | 当前状态 | 主要证据 |
| --- | --- | --- |
| 保持 canonical 求解底座 | 已实现 | 图编辑语义层经 `统一提交` 写入 `state_node`、`activity_node`、`atomic_activity`、`op_rule`；绑定更新不允许跨 `machine_type_id` 移动；Planner/Scheduler 主链路未替换。 |
| 状态-活动-状态二部结构 | 已实现 | 绑定角色投影为 `STATE_TO_ACTIVITY` 或 `ACTIVITY_TO_STATE`，活动不直接依赖活动。 |
| 语义端口连线 | 已实现 | 编辑模式下状态和活动节点显示左右语义端口；右侧端口发起拖线，左侧端口接收拖放；画布动作条按预览模式、无选择、只选状态、只选活动、状态+活动双选和拖拽中状态显示不同下一步提示；松手后预填右侧绑定表单并弹出端点、角色、规则、覆盖范围确认，确认后才创建草稿；状态包绑定确认框支持 `全部当前成员` 或 `选择部分成员`，部分成员在右侧覆盖控件勾选叶子后再创建；原子活动只使用启用规则，没有启用规则时提示前往活动能力或规则维护创建并启用 `op_rule`，多条启用规则时要求先选规则；状态右端口到虚拟/原子活动左端口分别创建 `context_input` / `input`，虚拟/原子活动右端口到状态左端口分别创建 `declared_output` / `output`；SVG 线端点与端口方向一致，状态包绑定和跨层级绑定显示短中文标签，普通线 hover 标题也使用中文角色；`network-editor.spec.ts` 使用合法虚拟活动 `context_input` 夹具，直接断言 `状态包上下文 / 跨层级` 与 `产出 / 跨层级` 渲染。 |
| 复杂连线降噪 | 已实现 | 前端渲染层保留真实 `visibleEdges` 不变，新增 `renderedEdges` 只控制画法；活动输入或输出超过 5 条时默认渲染为 `N 个输入` / `N 个输出` 汇总曲线；点击汇总线会选中对应活动并展开具体边，选中相关活动、相关状态或影响分析路径时也会展开具体边；具体边使用端口 lane offset 上下错开，避免同端点多线完全重叠。 |
| 已选活动批量连线 | 已实现 | 右侧 `批量绑定` 对话框可对当前选中的虚拟/原子活动一次选择多个输入状态和输出状态，批量生成 `activity_state_binding` 创建草稿；虚拟活动自动使用 `context_input/declared_output`，原子活动自动使用 `input/output` 并沿用启用规则选择；重复的已有绑定或草稿绑定会跳过；批量状态包绑定默认使用全部当前启用叶子，partial 覆盖由单条绑定表单处理。 |
| 新建虚拟活动自动生成边界连线 | 已实现 | 新建虚拟活动抽屉可选择多个 `上下文输入` 和 `声明输出` 状态；前端排入活动创建草稿后追加指向该草稿 `client_id` 的绑定草稿，后端 `network-editor/commit` 解析 `_draft_ref` 为真实 `activity_node_id`，同一次统一提交生成虚拟活动和两侧语义连线。 |
| 新建原子活动自动生成规则与连线 | 已实现 | 新建原子活动抽屉要求至少选择一个 `输入状态` 和一个 `产出状态`，否则不允许保存到草稿；产出状态能转换为 effect fact 时，前端同批排入 `atomic_activity`、`op_rule`、`activity_state_binding` 草稿，并用 `_draft_ref` 串联；产出状态暂时不能转换为 effect fact 时，前端按“待补规则”创建原子活动和 `input/output` 绑定草稿但不创建 `op_rule`，后端允许零启用规则的原子活动绑定 `op_rule_id=null`，统一提交确认后可保存模型，求解预检以 `EXECUTABLE_MISSING_RULE` 阻塞；产出多叶子状态包时抽屉要求选择 `全部当前成员` 或 `选择部分成员`，partial 模式必须勾选叶子状态。 |
| 状态包成员 DAG | 已实现 | `state_node.parent_id` 作为兼容的默认成员关系，`state_node_reference` 表达额外出现位置；成员引用环被拒绝并可预检；显示 DAG 用于网络编辑器投影、状态包叶子展开、覆盖快照和分层目标展开。 |
| 状态包 = AND(直接成员状态) | 已实现 | 求解预检 `state_aggregation_rules` 固定 `aggregation_rule=AND`。 |
| 状态包绑定解释为成员覆盖 | 已实现 | 聚合状态绑定默认 `binding_type=state_package`，solver-ready 视图展开为覆盖叶子；成员引用下的叶子也纳入该状态包覆盖。 |
| 新增状态包成员不自动扩展旧覆盖 | 已实现 | 旧绑定保持 `covered_leaf_state_ids`，新增启用叶子状态后覆盖状态变为 `stale/partial`。 |
| 虚拟活动不参与求解 | 已实现 | solver-ready 图只保留 executable activity；求解预检把虚拟活动作为 group/WBS metadata 保留。 |
| 可执行活动参与求解 | 已实现 | 原子活动绑定 `op_rule` 后同步 precondition/effect；求解交接只把原子活动作为可执行活动。 |
| 手写规则事实保护 | 已实现 | 绑定层用 `metadata_json._network_editor_managed_rule_facts` 记录接管的 facts；删除 binding 不会清理原本手写在 `op_rule` 上的同名 precondition/effect。 |
| 虚拟活动上下文前置继承给内部活动 | 已实现 | 后端拒绝虚拟活动普通 `input/output` 绑定；`context_input` 绑定在 solver-ready 叶子边和求解预检中作为 inherited preconditions。 |
| 跨层级绑定允许但标记 | 已实现 | `CROSS_LEVEL_BINDING_NOTICE` 和 `CROSS_LEVEL_BINDING_MANY`；前端活动节点显示 `跨层级 N` 节点级跨层级绑定数量；跨层级线在画布上显示 `输入 / 跨层级`、`状态包输入 / 跨层级` 等中文短标签，状态包绑定也显示 `状态包输入`、`状态包产出`、`状态包上下文` 或 `状态包声明输出`。 |
| 反向/返工活动显式建模，不自动回滚 | 已实现 | 编辑器允许普通 input/output 绑定；无自动状态失效推导。 |
| GraphEdge 不持久化 | 已实现 | Graph edge 为响应投影对象；核心持久表仍为绑定层。 |

## 3. 校验覆盖

| 校验项 | 建模校验 | 求解器准备校验 |
| --- | --- | --- |
| 孤立状态 / 活动 | `ORPHAN_STATE` / `ORPHAN_ACTIVITY` | 非阻断摘要。 |
| 活动缺少前置 / 产出 | `ACTIVITY_MISSING_INPUT` / `ACTIVITY_MISSING_OUTPUT` | 可执行活动对应 `EXECUTABLE_MISSING_INPUT` / `EXECUTABLE_MISSING_OUTPUT` 阻断。 |
| 可执行活动规则不可用 | - | `EXECUTABLE_MISSING_RULE` / `EXECUTABLE_RULE_NOT_EXPLICIT` / `EXECUTABLE_RULE_AMBIGUOUS` / `EXECUTABLE_RULE_BINDING_INVALID` error；默认 solver-ready 图和求解预检只使用启用 `op_rule`，只有停用规则或待补规则的原子活动不会被自动填入 `op_rule_id`；待补规则模型可保存，但求解预检保持 blocked。 |
| 停用状态事实进入覆盖快照 | - | 默认 solver-ready 图和求解预检只交接启用叶子状态事实；覆盖快照残留停用叶子状态时，`own_preconditions` / `own_effects` / `inherited_preconditions` 会过滤停用状态，`include_inactive=true` 时可审计。 |
| 状态聚合环 | `STATE_AGGREGATION_CYCLE` | 同码 error 阻断。 |
| 活动容器环 | `ACTIVITY_CONTAINER_CYCLE` | 同码 error 阻断。 |
| 状态包成员引用环 | `STATE_REFERENCE_CYCLE` | 同码 error 阻断。 |
| 状态-活动依赖环 | - | `GRAPH_DEPENDENCY_CYCLE` error。 |
| 状态包覆盖缺口 | `BINDING_COVERAGE_NOT_COMPLETE` warning | 同码 error。 |
| 虚拟活动未分解 | `VIRTUAL_ACTIVITY_NOT_DECOMPOSED` warning | 由声明输出未实现决定是否阻断。 |
| 虚拟活动部分实现 | `VIRTUAL_OUTPUT_NOT_IMPLEMENTED` warning | 同码 error。 |
| 重复状态名称 | `DUPLICATE_STATE_NAME` warning | 非阻断质量提示。 |
| 跨层级绑定提示 | `CROSS_LEVEL_BINDING_NOTICE` info | `CROSS_LEVEL_BINDING_MANY` warning。 |
| 不可达前置 / 未产出必要状态 | - | 复用 `layered-health-check` 的 `BROKEN_CHAIN` / `NO_PROVIDER`；诊断会映射回真实状态或 `atomic_activity:*` 图节点，底部问题表可定位，不可见节点会自动展开后选中；目标停用、目标无叶子、活动范围无原子活动等 `layered-expansion` 诊断也会带上 `node_id/node_type`；前端在缺少 `related_*` 时会用 `details.node_type/node_id`、`activity_node_id`、`state_node_id` 或 `op_rule_id` 兜底定位。 |
| 多个活动产出同一状态 | - | `MULTIPLE_OUTPUT_PROVIDERS` warning。 |
| 产出状态没有下游使用 | - | `OUTPUT_STATE_UNUSED` warning，目标状态豁免。 |
| 状态包覆盖范围过大 | - | `STATE_PACKAGE_COVERAGE_LARGE` warning。 |
| 活动参与求解标记错误 | - | `ACTIVITY_SOLVER_PARTICIPATION_MISMATCH` error。 |

## 4. 影响分析与统计

| 需求项 | 当前状态 | 主要证据 |
| --- | --- | --- |
| 选择状态显示上游/下游/所在状态包/其他出现位置 | 已实现 | `network-editor/impact` state 分支；右侧影响分析面板显示所在状态包路径和其他出现位置。 |
| 选择状态显示成员覆盖和包绑定使用 | 已实现 | `child_coverage`、`package_bindings`。 |
| 选择状态显示影响的虚拟/可执行活动 | 已实现 | `affected_virtual_activities`、`affected_executable_activities`。 |
| 选择活动显示直接前置/继承前置/产出 | 已实现 | `direct_precondition_states`、`inherited_precondition_states`、`output_states`。 |
| 选择活动显示所属虚拟活动、受影响状态包、下游活动、求解参与 | 已实现 | `owner_virtual_activities`、`affected_parent_states`、`downstream_activities`、`participates_in_solver`。 |
| 停用活动包引用的所属虚拟活动过滤 | 已实现 | 默认影响分析的 `owner_virtual_activities` 只按 active `activity_package_atomic_ref` 计算；`include_inactive=true` 时可审计停用挂载。 |
| 顶部影响分析入口 | 已实现 | 选中状态或活动后可点击顶部 `影响分析` 手动重新拉取影响路径；选中节点仍会自动刷新右侧影响分析面板。 |
| 影响路径高亮 | 已实现 | 前端 `impactHighlights` / `isImpactEdge`。 |
| 网络分布与深度统计 | 已实现 | 图摘要包含状态/活动数量、虚拟/可执行数量、最大状态/活动深度、最长依赖链、孤立节点、覆盖缺口、部分实现虚拟活动、跨层级绑定；活动节点显示 `跨层级 N` 局部数量。 |

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

- `python -m pytest tests\integration\test_layered_activity_state_api.py::test_network_editor_unified_commit_batches_changes_and_rolls_back -q` — 1 passed，覆盖统一提交 rollback、布局 metadata 持久化、重复状态复用引用、引用实例独立布局、聚焦状态包时语义边重定向到引用实例端点、状态包分叉新增/移除成员、分叉名称/说明必填、新建虚拟活动自动连线、新建原子活动同批规则/连线和编辑基线冲突 409 不落库。
- `python -m pytest tests\integration\test_layered_activity_state_api.py -q` — 20 passed。
- `python -m pytest tests\integration\test_scenario_import_api.py -q` — 9 passed。
- `python -m py_compile app\services\network_editor.py app\api\v1\master_data.py app\db\schemas.py` — passed。
- `python -m py_compile app\main.py scripts\serve_frontend_dist_proxy.py` — passed。
- TestClient smoke — `/`、`/frontend/network-editor` 返回 `frontend/dist` 入口，`/assets/index-*.js` 返回 200。
- `npm run build` — passed，仅有既有 Vite chunk-size warning；一次性提交状态机复核、端口拖放确认、语义线中文标签、汇总线点击展开和 details-only 问题定位兜底补强后重新通过。
- `npm run test:e2e -- network-editor.spec.ts --project=chromium` — 8 passed，覆盖历史手写 DOM/SVG 画板的预览只读、预览态展开/折叠、虚拟活动专注预览、取消编辑、统一提交、容器移动、容器隔离、汇总线和中文语义线；该结果证明既有业务流和草稿/提交路径可用，但不等同于 X6 单画布最终验收。
- 本轮未重新执行全量 `python -m pytest -q`。

## 7. 证据索引

后续审计优先从以下锚点进入，避免只凭口头描述判断完成度。前端工作区文件体量较大，行号会随 UI 文案和模板微调漂移；前端证据以 `data-testid`、函数名、API 调用名和 e2e 用例名为稳定锚点。

| 证据主题 | 文件锚点 |
| --- | --- |
| 状态包成员 / 活动包校验 | `app/api/v1/master_data.py:515` `_validate_state_parent`; `app/api/v1/master_data.py:790` `_validate_state_reference`; `app/api/v1/master_data.py:836` `_resolve_binding_payload`。 |
| 状态包成员引用 API 与布局更新 | `app/db/schemas.py:520` `StateNodeReferenceUpdate`; `app/api/v1/master_data.py:2323` list; `app/api/v1/master_data.py:2346` create; `app/api/v1/master_data.py:2369` update; `app/api/v1/master_data.py:2977` draft apply。 |
| 活动-状态绑定 API | `app/api/v1/master_data.py:2394` list; `app/api/v1/master_data.py:2418` create; `app/api/v1/master_data.py:2449` update。 |
| 统一提交 API 与草稿模型 | `app/db/schemas.py:862` `NetworkEditorDraftChange`; `app/db/schemas.py:873` `NetworkEditorCommitRequest`; `app/api/v1/master_data.py:3151` `commit_network_editor_draft`。 |
| 状态包分叉统一提交 | `app/api/v1/master_data.py:2833` `_create_state_package_fork`; `app/api/v1/master_data.py:3090` draft dispatch。 |
| 图投影 / 深度过滤 / 引用实例端点投影 | `app/services/network_editor.py:212` `_state_node_id_from_graph_id`; `app/services/network_editor.py:896` `_filter_graph`; `app/services/network_editor.py:1149` 引用实例统计；`app/services/network_editor.py:1193` `_build_graph_from_context`。 |
| 图预检与 canonical 端点校验 | `app/services/network_editor.py:1561` `_validate_projected_graph`; `app/services/network_editor.py:1604` / `1610` 使用 `canonical_source_id` / `canonical_target_id` 回到真实状态语义。 |
| 影响分析 | `app/services/network_editor.py:2318` `analyze_network_editor_impact`; `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `selectedImpact` / `impactHighlights` / `isImpactEdge`; `frontend/src/api/masterData.js` `analyzeNetworkEditorImpact`。 |
| 求解预检、聚合规则、虚拟 group 元数据 | `app/services/network_editor.py:2876` `precheck_network_editor_solver`; `app/db/schemas.py:966` `NetworkEditorSolverPrecheckResponse`。 |
| 前端预览 / 编辑模式与草稿队列 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `data-testid="network-editor-enter-edit"` / `network-editor-submit-draft`; `queueDraftChange`; `startEditSession`; `submitDraftChanges`; `commitNetworkEditorDraft`。 |
| 主设计冻结文档一次性提交口径 | `docs/superpowers/specs/2026-06-23-state-activity-network-editor-design.md` 的 `Unified Edit Commit`、`Page state machine` 和设计冻结验收标准，明确默认预览、进入编辑后草稿化、取消丢弃、统一提交写库。 |
| X6 单画布重构目标 | `docs/状态活动网络图编辑器_需求设计文档.md` 的 `X6 单画布原则`；`docs/superpowers/specs/2026-06-23-state-activity-network-editor-design.md` 的 `X6 Canvas Refactor`。 |
| 历史前端状态包 / 虚拟活动容器实现 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `statePackageContainers`; `virtualActivityContainers`; `startContainerMove`; `queueNodeLayoutChange`; 容器尺寸 `containerResize` 流程；后续将被 X6 单画布实现替换。 |
| 历史前端自由白板布局与自动整理 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的画布空白双击入口、状态包容器空白双击入口、`queueNodeLayoutChange`、`autoArrangeCanvas`、`startContainerMove` 和容器缩放流程；后续需迁移为 X6 graph 事件和 draft bridge。 |
| 前端虚拟活动专注画布 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `focusedActivityCanvas`; `enterActivityFocus`; `enterActivityFocusById`; `frontend/e2e/tests/network-editor.spec.ts` 预览态专注画布回归。 |
| 前端重复状态复用与同步/分叉对话 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `data-testid="network-editor-duplicate-state-dialog"`; `openDuplicateStateDialog`; `findDuplicateStateCandidates`; `packageChangeDecision`; `state_package_fork` 草稿入队。 |
| 前端局部展开 / 折叠 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的状态包 `展开 / 折叠` 节点入口、虚拟活动 `展开 / 折叠` 节点入口和对应展开深度更新函数；`frontend/e2e/tests/network-editor.spec.ts` 预览态展开/折叠回归。 |
| 前端问题定位、规则跳转与覆盖刷新 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `inspectIssue`; `openRuleMaintenance`; `refreshIssueCoverage`; `refreshSelectedCoverage`; 问题表 `定位` / `规则` / `刷新` test id。 |
| 前端求解预检入口 | `frontend/src/views/DataManagement/NetworkEditorWorkspace.vue` 的 `data-testid="network-editor-solver-precheck"`; `solverPrecheckPayload`; `runSolverPrecheck`; `frontend/src/api/masterData.js` `precheckNetworkEditorSolver`。 |
| 前端预览/编辑与语义线浏览器回归 | `frontend/e2e/tests/network-editor.spec.ts`；当前完整浏览器执行 8 passed，覆盖预览只读、预览态展开/折叠、虚拟活动专注预览、details-only 问题定位、取消编辑丢弃草稿、抽屉保存仅入草稿且统一提交才调用 commit、容器内部节点自由拖动、容器整体移动、汇总线点击展开和语义线中文标签。 |
| 网络编辑器统一提交回归 | `tests/integration/test_layered_activity_state_api.py:2073` `test_network_editor_unified_commit_batches_changes_and_rolls_back`。 |
| 状态包成员引用约束回归 | `tests/integration/test_layered_activity_state_api.py:2905` `test_network_editor_state_references_validate_constraints`。 |
| 图投影 / 校验 / 求解预检回归 | `tests/integration/test_layered_activity_state_api.py:3613` `test_network_editor_graph_validation_and_solver_precheck`。 |
| 停用 legacy rule 默认排除回归 | `tests/integration/test_layered_activity_state_api.py:4509`。 |
| 停用叶子状态事实默认求解交接过滤回归 | `tests/integration/test_layered_activity_state_api.py:4616`。 |
| 停用活动包引用默认 owner 过滤回归 | `tests/integration/test_layered_activity_state_api.py:4765`。 |

## 8. 关键设计结论逐条覆盖审计

该表对齐需求文档第 19 节 40 条关键设计结论。审计结论基于当前代码、验收矩阵和已通过回归；预览/编辑状态机、预览态展开/折叠、虚拟活动专注画布、状态包/虚拟活动容器隔离、编辑态容器整体移动与语义线标签已有 `network-editor.spec.ts` 浏览器回归，其他显示/交互大改后仍建议继续补针对性浏览器复核。

| 编号 | 关键结论 | 覆盖证据 |
| --- | --- | --- |
| 1 | 编辑器服务于全流程集成场景 | 求解预检、状态包聚合、虚拟 group 元数据、数据库交接和 `/solve/layered` 模板摘要已覆盖。 |
| 2 | 编辑器不仅可视化，还能直接编辑模型 | 预览/编辑模式、草稿队列、统一提交 API、状态/活动/绑定 CRUD 草稿均已实现。 |
| 3 | 服务求解器输入维护，并通过既有数据库接口对接求解链路 | 不导出独立文件；统一提交写 canonical 表；求解预检标记数据库交接就绪。 |
| 4 | 状态本体全局唯一，不携带层级所有权关系 | 状态包成员通过 `state_node_reference` 表达额外出现；界面收口为“所在状态包/引用”。 |
| 5 | 状态包是命名状态集合，通过成员引用聚合状态 | 状态树、状态包成员表、引用 CRUD、显示 DAG、覆盖快照均基于成员引用。 |
| 6 | 状态包通过全部成员状态 AND 聚合达成 | 求解预检 `state_aggregation_rules` 固定 `aggregation_rule=AND`，同时返回直接成员和叶子展开。 |
| 7 | 活动必须遵循状态-活动-状态结构 | 绑定投影只生成 `STATE_TO_ACTIVITY` / `ACTIVITY_TO_STATE` 边。 |
| 8 | 活动依赖状态，不直接依赖活动 | GraphEdge 只来自状态-活动绑定；虚拟活动归属通过容器和 group 元数据表达。 |
| 9 | 一个活动可以有多个前置状态和多个产出状态 | 批量绑定、新建虚拟/原子活动自动生成多条绑定草稿。 |
| 10 | 一个状态可以由多个活动产出 | `MULTIPLE_OUTPUT_PROVIDERS` 作为非阻断 warning，允许但提示复核。 |
| 11 | 活动采用节点形式，不作为普通边 | 前端画布分状态节点、虚拟活动节点、原子活动节点和语义边渲染。 |
| 12 | 交互层自由画布，语义层仍落到状态-活动-状态关系 | 布局 metadata 独立保存，业务事实仍写 `activity_state_binding`。 |
| 13 | 边只表达输入/输出/上下文/声明输出，不允许无语义自由线 | 端口拖线和右侧绑定表单都必须选择合法角色。 |
| 14 | 状态包绑定表示状态包成员状态覆盖范围 | `binding_type=state_package`，覆盖快照记录 `covered_leaf_state_ids`。 |
| 15 | 新增状态包成员后，原有状态包绑定不自动覆盖新增成员 | 旧覆盖保持快照，新增成员后状态变为 `stale/partial`，需刷新覆盖。 |
| 16 | 状态包绑定需要记录覆盖快照 | 模型、API、前端覆盖面板和测试均覆盖 `coverage_status` / `covered_leaf_state_ids`。 |
| 17 | 默认折叠高层节点，支持任意层级展开/收起 | 默认 `状态深度=1`、`活动深度=2`，支持聚焦、折叠、展开一层、展开全部。 |
| 18 | 展开状态包时容器只包含状态引用实例 | 最终验收以 X6 容器为准：状态包折叠为节点，展开为同一对象的容器形态，内部只允许状态节点和状态引用实例；当前 `statePackageContainers` 只是历史过渡证据。 |
| 19 | 展开虚拟活动时容器只包含子虚拟活动和原子活动 | 最终验收以 X6 容器为准：虚拟活动折叠为节点，展开为同一对象的容器形态，内部只允许虚拟活动和原子活动；上下文和声明输出状态不得进入容器。 |
| 20 | 支持状态和活动完全同步 | `loadAll` 同步加载状态、活动、原子活动、引用、绑定和规则，提交成功后重新投影。 |
| 21 | 支持全局自由布局、容器内部自由布局、局部坐标保存和自动整理 | 节点布局、容器尺寸、容器整体移动、引用实例布局和 `自动整理` 均进入草稿后统一提交；浏览器回归验证状态包/虚拟活动容器移动时内部节点跟随，也验证展开状态包内部状态和展开虚拟活动内部原子活动可单独拖动且不拖走容器根节点。 |
| 22 | 状态包成员关系和活动归属不通过业务连线表达 | 成员关系由 `state_node_reference` / 容器 / 资源树 / 属性区表达；业务线只表达状态-活动依赖。 |
| 23 | 状态包成员引用通过实例、角标、资源树、面包屑和属性面板表达 | 画布 `引用` 标记、资源树分组、右侧其他出现位置和活动专注条已覆盖；引用实例独立布局已回归。 |
| 24 | 允许跨层级绑定，但必须显示跨层级或状态包输入/输出提示 | 后端返回跨层级提示；活动节点显示 `跨层级 N`；状态包/跨层级线显示中文短标签。 |
| 25 | 通过选择前置状态和目标状态创建活动，系统生成活动节点和两端语义连接 | 多选状态工具条、新建虚拟活动和新建原子活动同批创建活动与绑定草稿。 |
| 26 | 高层活动作为虚拟活动用于自上而下建模 | level 1/2 `activity_node` 作为虚拟活动，支持内部子活动/原子活动创建。 |
| 27 | 虚拟活动不参与求解器计算 | solver-ready 视图只保留原子活动，虚拟活动仅作为 group/WBS 元数据。 |
| 28 | 虚拟活动可进入专注画布继续分解 | 虚拟活动节点 `专注` 入口和双击进入，专注条显示面包屑、边界状态和实现摘要；浏览器回归验证预览态进入专注画布不产生草稿。 |
| 29 | 专注画布边界状态仍属于状态体系，不进入虚拟活动容器 | 专注条显示上下文和声明输出状态，虚拟活动容器内部仍只含活动；`network-editor.spec.ts` 已补断言：进入专注画布后虚拟活动容器显示活动名，但不显示上下文状态或声明输出状态名称；该断言已随当前 8 条浏览器用例完整执行通过。 |
| 30 | 原子活动作为真正可执行活动参与求解器 | `atomic_activity` 绑定 `op_rule` 后进入 solver-ready 图和求解预检。 |
| 31 | 虚拟活动需要通过内部可执行活动实现声明输出 | `VIRTUAL_OUTPUT_NOT_IMPLEMENTED` 和前端 `实现 已实现/声明` 摘要覆盖。 |
| 32 | 虚拟活动可提供上下文前置并继承给内部可执行活动 | `context_input` 在 solver-ready 和求解预检中作为 inherited preconditions。 |
| 33 | 同一状态可在不同状态包下以引用实例形式出现 | `state_node_reference`、引用实例图节点、独立布局和引用端点投影已覆盖。 |
| 34 | 新建状态时自动识别重复状态，优先复用已有状态 | 编码/名称/事实强匹配自动复用，多候选弹窗选择复用或仍然新建。 |
| 35 | 修改已被引用状态包成员时必须选择同步或分叉 | `共享状态包修改确认` 和后端 `state_package_fork` 约束覆盖。 |
| 36 | 同步影响所有引用方；分叉创建分支并保持其他引用方不变 | 分叉复制成员、替换当前使用方引用，其他引用方保持原包；回归覆盖新增/移除。 |
| 37 | 默认预览只读；进入编辑后所有变更进入草稿 | `canMutate`、`requireEditMode` 和 `queueDraftChange` 中心入口覆盖。 |
| 38 | 统一提交写库；取消编辑丢弃草稿 | `network-editor/commit` 批量提交；取消/刷新/切换设备回到预览并清草稿；浏览器用例覆盖布局草稿取消后恢复已提交位置，并断言状态抽屉 `保存` 只进入草稿、不触发 commit，点击顶部 `统一提交` 后才发送唯一一次 `network-editor/commit` 请求；这些路径已随当前 8 条 Playwright 用例完整执行通过。 |
| 39 | 不导出独立数据文件，提交后由既有数据库接口读取 | 页面无下载 JSON/模板入口；旧 export-preview 仅兼容别名；求解预检只给摘要。 |
| 40 | 需要建模校验和求解器准备校验两套机制 | `network-editor/validate` 同时返回 `modeling_issues` 与 `solver_ready_issues`，提交前按结构性问题和求解准备问题分流。 |
