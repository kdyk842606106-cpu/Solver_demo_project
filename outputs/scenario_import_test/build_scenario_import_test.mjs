import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outDir = "E:/Solver_demo_project/outputs/scenario_import_test";
const outPath = path.join(outDir, "scenario_import_test.xlsx");

const workbook = Workbook.create();

const sheets = {
  meta: [
    ["scenario_code", "scenario_name", "version", "mode"],
    ["QA_IMPORT_001", "场景导入验收测试", "v1", "scenario_upsert"],
  ],
  feature_catalog: [
    ["feature_key", "value_type", "allowed_values", "unit", "description"],
    ["prep_done", "enum", "false,true", "", "准备完成"],
    ["structure_installed", "enum", "false,true", "", "结构件安装完成"],
    ["wiring_done", "enum", "false,true", "", "线缆连接完成"],
    ["hydraulic_ready", "enum", "false,true", "", "液压系统就绪"],
    ["qa_passed", "enum", "false,true", "", "质量检查通过"],
    ["delivery_ready", "enum", "false,true", "", "交付就绪"],
  ],
  machine_type: [
    ["code", "name", "description"],
    ["QA_ASSEMBLY_LINE", "导入测试装配线", "用于验证场景 Excel 导入与求解链路"],
  ],
  machines: [
    ["code", "machine_type_code", "name", "location"],
    ["QA-LINE-001", "QA_ASSEMBLY_LINE", "导入测试线 001", "测试车间 A"],
  ],
  state_feature_defs: [
    ["machine_type_code", "feature_key", "feature_name", "value_type", "allowed_values"],
    ["QA_ASSEMBLY_LINE", "prep_done", "准备完成", "enum", "false,true"],
    ["QA_ASSEMBLY_LINE", "structure_installed", "结构件安装完成", "enum", "false,true"],
    ["QA_ASSEMBLY_LINE", "wiring_done", "线缆连接完成", "enum", "false,true"],
    ["QA_ASSEMBLY_LINE", "hydraulic_ready", "液压系统就绪", "enum", "false,true"],
    ["QA_ASSEMBLY_LINE", "qa_passed", "质量检查通过", "enum", "false,true"],
    ["QA_ASSEMBLY_LINE", "delivery_ready", "交付就绪", "enum", "false,true"],
  ],
  resources: [
    ["code", "name", "resource_type", "capacity", "is_available", "meta_json"],
    ["TECH-QA-01", "技术员 01", "technician", 1, "true", "{\"team\":\"A班组\",\"skill_level\":\"senior\"}"],
    ["FIXTURE-QA-01", "装配工装 01", "fixture", 1, "true", "{\"area\":\"A区\",\"asset_no\":\"FX-QA-01\"}"],
    ["QA-QA-01", "质检员 01", "inspector", 1, "true", "{\"certified_for\":[\"assembly\",\"delivery\"]}"],
  ],
  rules: [
    [
      "code",
      "machine_type_code",
      "name",
      "duration_min",
      "description",
      "is_active",
      "is_repair",
      "preconditions",
      "effects",
      "resource_reqs",
    ],
    [
      "OP_QA_PREP",
      "QA_ASSEMBLY_LINE",
      "准备工位",
      15,
      "清点工装和技术准备",
      "true",
      "false",
      "prep_done:eq:false",
      "prep_done:set:true",
      "technician:1:true",
    ],
    [
      "OP_QA_STRUCTURE",
      "QA_ASSEMBLY_LINE",
      "安装结构件",
      30,
      "安装主体结构件",
      "true",
      "false",
      "prep_done:eq:true;structure_installed:eq:false",
      "structure_installed:set:true",
      "technician:1:true;fixture:1:true",
    ],
    [
      "OP_QA_WIRING",
      "QA_ASSEMBLY_LINE",
      "连接线缆",
      25,
      "完成线缆连接",
      "true",
      "false",
      "structure_installed:eq:true;wiring_done:eq:false",
      "wiring_done:set:true",
      "technician:1:true",
    ],
    [
      "OP_QA_HYDRAULIC",
      "QA_ASSEMBLY_LINE",
      "液压准备",
      20,
      "完成液压系统准备",
      "true",
      "false",
      "structure_installed:eq:true;hydraulic_ready:eq:false",
      "hydraulic_ready:set:true",
      "technician:1:true;fixture:1:true",
    ],
    [
      "OP_QA_INSPECT",
      "QA_ASSEMBLY_LINE",
      "质量检查",
      18,
      "结构、线缆和液压状态检查",
      "true",
      "false",
      "wiring_done:eq:true;hydraulic_ready:eq:true;qa_passed:eq:false",
      "qa_passed:set:true",
      "inspector:1:true",
    ],
    [
      "OP_QA_DELIVER",
      "QA_ASSEMBLY_LINE",
      "交付确认",
      12,
      "确认交付状态",
      "true",
      "false",
      "qa_passed:eq:true;delivery_ready:eq:false",
      "delivery_ready:set:true",
      "inspector:1:true",
    ],
  ],
  states: [
    ["machine_code", "state_code", "state_type", "label", "features"],
    [
      "QA-LINE-001",
      "START",
      "current",
      "导入测试起点",
      "prep_done:false;structure_installed:false;wiring_done:false;hydraulic_ready:false;qa_passed:false;delivery_ready:false",
    ],
    [
      "QA-LINE-001",
      "TARGET",
      "target",
      "导入测试目标",
      "prep_done:true;structure_installed:true;wiring_done:true;hydraulic_ready:true;qa_passed:true;delivery_ready:true",
    ],
  ],
  solve_cases: [
    [
      "case_code",
      "machine_code",
      "current_state_code",
      "target_state_code",
      "objective",
      "objectives_json",
      "constraints_json",
      "expected_min_steps",
      "expected_max_makespan_min",
    ],
    ["FULL_IMPORT_FLOW", "QA-LINE-001", "START", "TARGET", "minimize_makespan", "", "", 6, 120],
  ],
  instructions: [
    ["section", "description"],
    ["用途", "这个文件可直接用于 数据管理 -> 导入场景，先预校验，再确认导入。"],
    ["rules.preconditions", "格式：feature_key:operator:value，多项用分号分隔。"],
    ["rules.effects", "格式：feature_key:effect_type:value，多项用分号分隔。"],
    ["rules.resource_reqs", "格式：resource_type:quantity:is_required，多项用分号分隔。"],
    ["states.features", "格式：feature_key:value，多项用分号分隔。"],
    ["solve_cases", "导入后响应会返回 machine_id/current_state_id/target_state_id，可直接调用 /api/v1/solve。"],
  ],
  rule_groups: [
    ["group_code", "group_name", "rule_codes", "description"],
    ["PREP", "准备阶段", "OP_QA_PREP", "准备类活动"],
    ["ASSEMBLY", "装配阶段", "OP_QA_STRUCTURE,OP_QA_WIRING,OP_QA_HYDRAULIC", "装配与连接活动"],
    ["QA_DELIVERY", "质检交付", "OP_QA_INSPECT,OP_QA_DELIVER", "质检与交付确认"],
  ],
  notes: [
    ["note"],
    ["rule_groups 是可选 sheet，当前导入不落库，不影响求解。"],
  ],
};

for (const [sheetName, rows] of Object.entries(sheets)) {
  const sheet = workbook.worksheets.add(sheetName);
  const colCount = Math.max(...rows.map((row) => row.length));
  const normalized = rows.map((row) => {
    const next = [...row];
    while (next.length < colCount) next.push("");
    return next;
  });
  sheet.getRangeByIndexes(0, 0, normalized.length, colCount).values = normalized;
  const header = sheet.getRangeByIndexes(0, 0, 1, colCount);
  header.format = {
    fill: "#1F4E79",
    font: { bold: true, color: "#FFFFFF" },
  };
  sheet.freezePanes.freezeRows(1);
  sheet.getUsedRange().format.wrapText = true;
  sheet.getUsedRange().format.autofitColumns();
}

await fs.mkdir(outDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outPath);

console.log(outPath);
