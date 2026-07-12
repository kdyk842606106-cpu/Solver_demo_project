const PptxGenJS = require('pptxgenjs');

// 创建PPT
const ppt = new PptxGenJS();

// 设置元数据
ppt.title = 'Solver Demo Project · 预研成果与技术路线汇报';
ppt.author = 'Solver Team';

// 定义颜色
const colors = {
    primary: '1E3A8A',    // 深蓝
    secondary: '3B82F6',  // 蓝色
    accent: 'EF4444',      // 红色
    text: '374151',        // 深灰
    light: 'F3F4F6',       // 浅灰背景
    white: 'FFFFFF'
};

// ========== 第1页：封面 ==========
const slide1 = ppt.addSlide();
slide1.background = { color: colors.primary };

// 标题
slide1.addText('Solver Demo Project', {
    x: 0.5, y: 1.5, w: 9, h: 1,
    fontSize: 44, color: colors.white, bold: true,
    fontFace: 'Microsoft YaHei'
});

// 副标题
slide1.addText('预研成果与技术路线汇报', {
    x: 0.5, y: 2.5, w: 9, h: 0.8,
    fontSize: 28, color: 'BFDBFE',
    fontFace: 'Microsoft YaHei'
});

// 一句话定位
slide1.addText('不是"用AI生成计划"，而是"用规则推导计划"\n——确定性、可解释、可审计', {
    x: 0.5, y: 4, w: 9, h: 1.2,
    fontSize: 20, color: colors.white,
    fontFace: 'Microsoft YaHei'
});

// 版本信息
slide1.addText('V0.3 · 2026-04-27', {
    x: 0.5, y: 5.5, w: 3, h: 0.5,
    fontSize: 14, color: '9CA3AF',
    fontFace: 'Microsoft YaHei'
});

// ========== 第2页：集成问题定性 ==========
const slide2 = ppt.addSlide();

slide2.addText('集成问题定性', {
    x: 0.5, y: 0.5, w: 9, h: 0.8,
    fontSize: 32, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

slide2.addText([
    { text: '泵体装配有500+工序，状态可回退（安装→拆卸→再安装），数值触发（每N次清洁）。', options: { breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: '传统排程工具假设"状态只前进"，LLM能做但保证不了确定性。', options: { breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: '我们需要一个形式化规则推导引擎——给定当前状态和目标，自动推导出工序序列。', options: { breakLine: true } }
], {
    x: 0.5, y: 1.5, w: 9, h: 3.5,
    fontSize: 20, color: colors.text,
    fontFace: 'Microsoft YaHei',
    lineSpacing: 28
});

// ========== 第3页：CP-SAT vs LLM ==========
const slide3 = ppt.addSlide();

slide3.addText('为什么CP-SAT和LLM都不够用？', {
    x: 0.5, y: 0.5, w: 9, h: 0.8,
    fontSize: 32, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

// CP-SAT 对比
slide3.addText('传统数学方法（CP-SAT / 线性规划）', {
    x: 0.5, y: 1.5, w: 4, h: 0.5,
    fontSize: 18, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

slide3.addText('• 擅长：给定工序列表后优化时间安排\n• 死穴：状态不回退、无法推导工序\n• 结论：优秀的"生产经理"，做不了"总工程师"', {
    x: 0.5, y: 2, w: 4, h: 2,
    fontSize: 14, color: colors.text,
    fontFace: 'Microsoft YaHei',
    lineSpacing: 22
});

// LLM 对比
slide3.addText('LLM大模型（GPT-4 / Claude）', {
    x: 5, y: 1.5, w: 4, h: 0.5,
    fontSize: 18, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

slide3.addText('• 擅长：理解自然语言、生成看似合理的计划\n• 死穴：结果不可复现、可能幻觉\n• 结论：优秀的"顾问"，做不了"执行者"', {
    x: 5, y: 2, w: 4, h: 2,
    fontSize: 14, color: colors.text,
    fontFace: 'Microsoft YaHei',
    lineSpacing: 22
});

// 金句
slide3.addShape(ppt.ShapeType.rect, {
    x: 0.5, y: 4.5, w: 9, h: 1,
    fill: { color: colors.light }
});

slide3.addText('这不是"又一个排程工具"，是"从0到1推导工序序列"的新品类。', {
    x: 0.5, y: 4.7, w: 9, h: 0.6,
    fontSize: 16, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei',
    align: 'center'
});

// ========== 第4页：双层架构 ==========
const slide4 = ppt.addSlide();

slide4.addText('双层架构——Planner 定工序，Scheduler 排时间', {
    x: 0.5, y: 0.5, w: 9, h: 0.8,
    fontSize: 32, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

// 架构框
slide4.addShape(ppt.ShapeType.rect, {
    x: 1, y: 1.8, w: 8, h: 0.8,
    fill: { color: colors.secondary }
});
slide4.addText('输入：当前状态 + 目标 + 规则库', {
    x: 1, y: 2, w: 8, h: 0.5,
    fontSize: 16, color: colors.white,
    fontFace: 'Microsoft YaHei',
    align: 'center'
});

slide4.addShape(ppt.ShapeType.rect, {
    x: 1, y: 2.8, w: 8, h: 1.2,
    fill: { color: colors.primary }
});
slide4.addText('Planner（状态空间推导）\n做什么 | 按什么顺序 | 哪些可并行', {
    x: 1, y: 3, w: 8, h: 1,
    fontSize: 16, color: colors.white,
    fontFace: 'Microsoft YaHei',
    align: 'center'
});

slide4.addShape(ppt.ShapeType.rect, {
    x: 1, y: 4.2, w: 8, h: 1.2,
    fill: { color: '10B981' }
});
slide4.addText('Scheduler（CP-SAT资源排程）\n何时做 | 用多少资源 | 工期最短', {
    x: 1, y: 4.4, w: 8, h: 1,
    fontSize: 16, color: colors.white,
    fontFace: 'Microsoft YaHei',
    align: 'center'
});

// 金句
slide4.addText('Planner是"总工程师"定工序，Scheduler是"生产经理"排时间。\n各司其职，接口稳定。', {
    x: 0.5, y: 5.8, w: 9, h: 0.8,
    fontSize: 14, color: colors.text,
    fontFace: 'Microsoft YaHei',
    align: 'center'
});

// ========== 第5页：V0.3成果 ==========
const slide5 = ppt.addSlide();

slide5.addText('V0.3 当前能做到什么程度？', {
    x: 0.5, y: 0.5, w: 9, h: 0.8,
    fontSize: 32, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

slide5.addText('工程闭环已验证，核心场景可跑通', {
    x: 0.5, y: 1.2, w: 9, h: 0.5,
    fontSize: 18, color: colors.secondary,
    fontFace: 'Microsoft YaHei'
});

// 能力表格
const tableData = [
    ['能力', '状态'],
    ['常规排程：输入起点+目标，输出工序序列', '✅ 基础可用'],
    ['数值步进：水位0→80，步长20，自动4次注水', '✅ 可用'],
    ['重复实例化：同一规则多次执行，独立ID', '✅ 可用'],
    ['隐式子目标：前置不满足时自动补齐', '✅ 可用'],
    ['阻塞重排：卡住时自动重规划', '✅ 可用']
];

slide5.addTable(tableData, {
    x: 0.5, y: 1.8, w: 9, h: 2.5,
    fontSize: 14,
    fontFace: 'Microsoft YaHei',
    color: colors.text,
    border: { color: colors.light, pt: 1 },
    colW: [6, 3]
});

// 案例
slide5.addShape(ppt.ShapeType.rect, {
    x: 0.5, y: 4.5, w: 9, h: 1.5,
    fill: { color: colors.light }
});

slide5.addText('案例：模块A已安装→电源下电→缺口=2\n目标：所有模块调测+上电+真空\n输出：上电→A调测→下电→建真空→B调测→再上电...\n特征：上电/下电反复，由约束网络自然决定', {
    x: 0.5, y: 4.6, w: 9, h: 1.3,
    fontSize: 13, color: colors.text,
    fontFace: 'Microsoft YaHei',
    lineSpacing: 20
});

// ========== 第6页：演进路线 ==========
const slide6 = ppt.addSlide();

slide6.addText('从Demo到产品', {
    x: 0.5, y: 0.5, w: 9, h: 0.8,
    fontSize: 32, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

// 时间线
const timelineData = [
    ['阶段', '目标', '标志事件'],
    ['V0.3 当前', '工程闭环验证', 'Demo可用，数值Phase1落地'],
    ['V0.5-V0.6', '补齐核心差距', '生产环境试点'],
    ['V1.0', '标准计划求解平台', '单机台→多机台，离线→实时'],
    ['V1.5+', 'MES/ERP深度集成', '"人驱动"→"系统推荐+人工确认"']
];

slide6.addTable(timelineData, {
    x: 0.5, y: 1.5, w: 9, h: 2.5,
    fontSize: 14,
    fontFace: 'Microsoft YaHei',
    color: colors.text,
    border: { color: colors.light, pt: 1 }
});

// 远景
slide6.addText('远景：成为复杂装备集成领域的标准计划求解平台', {
    x: 0.5, y: 4.3, w: 9, h: 0.5,
    fontSize: 18, color: colors.primary, bold: true,
    fontFace: 'Microsoft YaHei'
});

slide6.addText('• 工艺知识不随人员流动而流失\n• 任何工程师都能获得一致、高质量的排程方案\n• 从"人驱动"到"系统推荐+人工确认"', {
    x: 0.5, y: 4.8, w: 9, h: 1.5,
    fontSize: 14, color: colors.text,
    fontFace: 'Microsoft YaHei',
    lineSpacing: 22
});

// 保存文件
const outputPath = '/mnt/e/Solver_demo_project/Solver_Demo_Presentation.pptx';
ppt.writeFile({ fileName: outputPath })
    .then(() => {
        console.log('PPT generated successfully at: ' + outputPath);
    })
    .catch((err) => {
        console.error('Error:', err);
    });
