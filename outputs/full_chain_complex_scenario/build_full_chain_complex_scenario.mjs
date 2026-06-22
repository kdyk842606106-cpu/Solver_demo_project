import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outDir = "E:/Solver_demo_project/outputs/full_chain_complex_scenario";
const outPath = path.join(outDir, "full_chain_complex_scenario.xlsx");

const MT = "COMPLEX_ASSEMBLY_LINE";
const MACHINE = "CAL-001";

const headers = {
  meta: ["scenario_code", "scenario_name", "version", "mode"],
  feature_catalog: ["feature_key", "value_type", "allowed_values", "unit", "description"],
  machine_type: ["code", "name", "description"],
  machines: ["code", "machine_type_code", "name", "location"],
  state_feature_defs: ["machine_type_code", "feature_key", "feature_name", "value_type", "allowed_values"],
  resources: ["machine_code", "code", "name", "resource_type", "capacity", "is_available", "meta_json"],
  activity_nodes: [
    "machine_type_code",
    "code",
    "parent_code",
    "level",
    "name",
    "activity_category",
    "sort_order",
    "is_active",
    "metadata_json",
  ],
  state_nodes: [
    "machine_type_code",
    "code",
    "parent_code",
    "level",
    "name",
    "feature_key",
    "operator",
    "target_value",
    "state_kind",
    "sort_order",
    "is_active",
    "metadata_json",
  ],
  scope_guards: [
    "machine_type_code",
    "activity_node_code",
    "name",
    "description",
    "is_active",
    "preconditions",
    "metadata_json",
  ],
  rules: [
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
    "activity_node_code",
  ],
  states: ["machine_code", "state_code", "state_type", "label", "features"],
  solve_cases: [
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
  maintenance_intents: [
    "machine_type_code",
    "issue_type",
    "name",
    "scope_activity_node_code",
    "description",
    "target_state_node_codes",
    "candidate_activity_scope_codes",
    "observed_fact_templates",
    "desired_fact_templates",
    "is_active",
    "metadata_json",
  ],
  layered_health_checks: [
    "machine_type_code",
    "check_code",
    "name",
    "target_state_node_codes",
    "activity_scope_node_codes",
    "include_inactive",
    "description",
  ],
  instructions: ["section", "description"],
  notes: ["note"],
};

const features = [
  ["prep_done", "enum", "false,true", "", "Common preparation complete."],
  ["power_on", "enum", "false,true", "", "Line has been powered on."],
  ["structure_installed", "enum", "false,true", "", "Main structure installed."],
  ["alignment_done", "enum", "false,true", "", "Mechanical alignment complete."],
  ["wiring_done", "enum", "false,true", "", "Electrical wiring complete."],
  ["hydraulic_ready", "enum", "false,true", "", "Hydraulic subsystem ready."],
  ["sensor_calibrated", "enum", "false,true", "", "Sensors calibrated."],
  ["cleanliness", "number", "", "score", "Cleanliness score, target 80."],
  ["integration_ready", "enum", "false,true", "", "Integrated system ready for QA."],
  ["qa_passed", "enum", "false,true", "", "QA passed."],
  ["delivery_ready", "enum", "false,true", "", "Ready for delivery."],
  ["blockage_reason", "string", "", "", "Blockage reason for repair replans."],
];

const activityNodes = [
  [MT, "CAL_FLOW", "", 1, "Complex assembly flow", "normal", 0, "true", ""],
  [MT, "PREP_PACK", "CAL_FLOW", 2, "Preparation package", "normal", 10, "true", ""],
  [MT, "MECH_PACK", "CAL_FLOW", 2, "Mechanical package", "normal", 20, "true", ""],
  [MT, "ELECTRIC_PACK", "CAL_FLOW", 2, "Electrical package", "normal", 30, "true", ""],
  [MT, "HYDRAULIC_PACK", "CAL_FLOW", 2, "Hydraulic package", "normal", 40, "true", ""],
  [MT, "CLEAN_PACK", "CAL_FLOW", 2, "Cleanliness package", "normal", 50, "true", ""],
  [MT, "INTEGRATION_PACK", "CAL_FLOW", 2, "Integration package", "normal", 60, "true", ""],
  [MT, "QA_PACK", "CAL_FLOW", 2, "QA package", "normal", 70, "true", ""],
  [MT, "DELIVERY_PACK", "CAL_FLOW", 2, "Delivery package", "normal", 80, "true", ""],
  [MT, "REPAIR_PACK", "CAL_FLOW", 2, "Repair package", "repair", 90, "true", ""],
  [MT, "COMMON_PREP_STEP", "PREP_PACK", 3, "Common prep and power-on", "normal", 10, "true", ""],
  [MT, "STRUCTURE_STEP", "MECH_PACK", 3, "Install structure", "normal", 20, "true", ""],
  [MT, "ALIGNMENT_STEP", "MECH_PACK", 3, "Align structure", "normal", 30, "true", ""],
  [MT, "WIRING_STEP", "ELECTRIC_PACK", 3, "Connect wiring", "normal", 40, "true", ""],
  [MT, "SENSOR_CAL_STEP", "ELECTRIC_PACK", 3, "Calibrate sensors", "normal", 50, "true", ""],
  [MT, "HYD_READY_STEP", "HYDRAULIC_PACK", 3, "Prepare hydraulics", "normal", 60, "true", ""],
  [MT, "CLEAN_STEP", "CLEAN_PACK", 3, "Incremental clean", "normal", 70, "true", ""],
  [MT, "INTEGRATION_STEP", "INTEGRATION_PACK", 3, "Integrated checkout", "normal", 80, "true", ""],
  [MT, "QA_STEP", "QA_PACK", 3, "Quality inspection", "normal", 90, "true", ""],
  [MT, "DELIVERY_STEP", "DELIVERY_PACK", 3, "Delivery release", "normal", 100, "true", ""],
  [MT, "REPAIR_SENSOR_STEP", "REPAIR_PACK", 3, "Repair sensor blockage", "repair", 110, "true", ""],
];

const stateNodes = [
  [MT, "CAL_COMPLETE", "", 1, "Assembly complete", "", "", "", "aggregate", 0, "true", ""],
  [MT, "PREP_READY", "CAL_COMPLETE", 2, "Preparation ready", "", "", "", "aggregate", 10, "true", ""],
  [MT, "MECH_READY", "CAL_COMPLETE", 2, "Mechanical ready", "", "", "", "aggregate", 20, "true", ""],
  [MT, "ELECTRIC_READY", "CAL_COMPLETE", 2, "Electrical ready", "", "", "", "aggregate", 30, "true", ""],
  [MT, "FLUID_READY", "CAL_COMPLETE", 2, "Fluid ready", "", "", "", "aggregate", 40, "true", ""],
  [MT, "CLEAN_READY", "CAL_COMPLETE", 2, "Cleanliness ready", "", "", "", "aggregate", 50, "true", ""],
  [MT, "FINAL_READY", "CAL_COMPLETE", 2, "Final delivery ready", "", "", "", "aggregate", 60, "true", ""],
  [MT, "MAINT_READY", "CAL_COMPLETE", 2, "Maintenance clear", "", "", "", "aggregate", 70, "true", ""],
  [MT, "PREP_DONE", "PREP_READY", 3, "Preparation done", "prep_done", "eq", "true", "atomic", 10, "true", ""],
  [MT, "POWER_ON", "PREP_READY", 3, "Power on", "power_on", "eq", "true", "atomic", 20, "true", ""],
  [MT, "STRUCTURE_INSTALLED", "MECH_READY", 3, "Structure installed", "structure_installed", "eq", "true", "atomic", 30, "true", ""],
  [MT, "ALIGNMENT_DONE", "MECH_READY", 3, "Alignment done", "alignment_done", "eq", "true", "atomic", 40, "true", ""],
  [MT, "WIRING_DONE", "ELECTRIC_READY", 3, "Wiring done", "wiring_done", "eq", "true", "atomic", 50, "true", ""],
  [MT, "SENSOR_CALIBRATED", "ELECTRIC_READY", 3, "Sensor calibrated", "sensor_calibrated", "eq", "true", "atomic", 60, "true", ""],
  [MT, "HYDRAULIC_READY", "FLUID_READY", 3, "Hydraulic ready", "hydraulic_ready", "eq", "true", "atomic", 70, "true", ""],
  [MT, "CLEAN_80", "CLEAN_READY", 3, "Cleanliness reaches 80", "cleanliness", "eq", "80", "atomic", 80, "true", ""],
  [MT, "INTEGRATION_READY", "FINAL_READY", 3, "Integration ready", "integration_ready", "eq", "true", "atomic", 90, "true", ""],
  [MT, "QA_PASSED", "FINAL_READY", 3, "QA passed", "qa_passed", "eq", "true", "atomic", 100, "true", ""],
  [MT, "DELIVERY_READY", "FINAL_READY", 3, "Delivery ready", "delivery_ready", "eq", "true", "atomic", 110, "true", ""],
  [MT, "BLOCKAGE_CLEAR", "MAINT_READY", 3, "Blockage clear", "blockage_reason", "eq", "none", "atomic", 120, "true", ""],
];

const scopeGuards = [
  [MT, "MECH_PACK", "Preparation before mechanical work", "", "true", "PREP_DONE:completed", ""],
  [MT, "ELECTRIC_PACK", "Power before electrical work", "", "true", "POWER_ON:completed", ""],
  [MT, "HYDRAULIC_PACK", "Structure before hydraulic work", "", "true", "STRUCTURE_INSTALLED:completed", ""],
  [MT, "INTEGRATION_PACK", "All subsystems before integration", "", "true", "ALIGNMENT_DONE:completed;WIRING_DONE:completed;HYDRAULIC_READY:completed;SENSOR_CALIBRATED:completed", ""],
  [MT, "QA_PACK", "Integration before QA", "", "true", "INTEGRATION_READY:completed", ""],
  [MT, "DELIVERY_PACK", "QA before delivery", "", "true", "QA_PASSED:completed", ""],
];

const rules = [
  ["OP_CAL_COMMON_PREP", MT, "Common preparation and power-on", 12, "Shared provider for prep_done and power_on.", "true", "false", "", "prep_done:set:true;power_on:set:true", "technician:1:true", "COMMON_PREP_STEP"],
  ["OP_CAL_STRUCTURE", MT, "Install primary structure", 30, "Mechanical branch.", "true", "false", "prep_done:eq:true", "structure_installed:set:true", "technician:1:true;crane:1:true;fixture:1:true", "STRUCTURE_STEP"],
  ["OP_CAL_ALIGNMENT", MT, "Align structure", 22, "Mechanical follow-up.", "true", "false", "structure_installed:eq:true", "alignment_done:set:true", "technician:1:true;fixture:1:true", "ALIGNMENT_STEP"],
  ["OP_CAL_WIRING", MT, "Connect wiring", 24, "Electrical branch.", "true", "false", "power_on:eq:true", "wiring_done:set:true", "technician:1:true", "WIRING_STEP"],
  ["OP_CAL_SENSOR_CAL", MT, "Calibrate sensors", 18, "Calibration bench bottleneck.", "true", "false", "wiring_done:eq:true", "sensor_calibrated:set:true", "technician:1:true;calibration_bench:1:true", "SENSOR_CAL_STEP"],
  ["OP_CAL_HYDRAULIC", MT, "Prepare hydraulics", 20, "Hydraulic branch after structure.", "true", "false", "structure_installed:eq:true", "hydraulic_ready:set:true", "technician:1:true;fixture:1:true", "HYD_READY_STEP"],
  ["OP_CAL_CLEAN_INCREMENT", MT, "Incremental cleaning pass", 8, "Repeated numeric provider, +20 cleanliness per instance.", "true", "false", "prep_done:eq:true", "cleanliness:increment:20", "technician:1:true", "CLEAN_STEP"],
  ["OP_CAL_INTEGRATION", MT, "Integrated checkout", 28, "Consumes all branch results.", "true", "false", "alignment_done:eq:true;wiring_done:eq:true;hydraulic_ready:eq:true;sensor_calibrated:eq:true", "integration_ready:set:true", "technician:1:true;fixture:1:true;calibration_bench:1:true", "INTEGRATION_STEP"],
  ["OP_CAL_QA", MT, "Quality inspection", 16, "Final inspection.", "true", "false", "integration_ready:eq:true", "qa_passed:set:true", "inspector:1:true", "QA_STEP"],
  ["OP_CAL_DELIVERY", MT, "Delivery release", 10, "Release the line for delivery.", "true", "false", "qa_passed:eq:true", "delivery_ready:set:true", "inspector:1:true", "DELIVERY_STEP"],
  ["OP_CAL_REPAIR_SENSOR", MT, "Repair sensor blockage", 14, "Repair rule triggered by blockage_reason=sensor_fault.", "true", "true", "blockage_reason:eq:sensor_fault", "blockage_reason:set:none;sensor_calibrated:set:true", "technician:1:true;calibration_bench:1:true", "REPAIR_SENSOR_STEP"],
  ["OP_CAL_SPARE_FIXTURE_CHECK", MT, "Inactive fixture check", 9, "Inactive validation row kept out of solves.", "false", "false", "prep_done:eq:true", "alignment_done:set:false", "fixture:1:true", "ALIGNMENT_STEP"],
];

const startFeatures = [
  "prep_done:false",
  "power_on:false",
  "structure_installed:false",
  "alignment_done:false",
  "wiring_done:false",
  "hydraulic_ready:false",
  "sensor_calibrated:false",
  "cleanliness:0",
  "integration_ready:false",
  "qa_passed:false",
  "delivery_ready:false",
  "blockage_reason:none",
].join(";");

const targetFeatures = [
  "prep_done:true",
  "power_on:true",
  "structure_installed:true",
  "alignment_done:true",
  "wiring_done:true",
  "hydraulic_ready:true",
  "sensor_calibrated:true",
  "cleanliness:80",
  "integration_ready:true",
  "qa_passed:true",
  "delivery_ready:true",
  "blockage_reason:none",
].join(";");

const sheets = {
  meta: [["FULL_CHAIN_COMPLEX_001", "Full-chain complex solver scenario", "v1", "scenario_upsert"]],
  feature_catalog: features,
  machine_type: [[MT, "Complex Assembly Line", "Full-chain integration planning scenario with layered state, maintenance and numeric repeats."]],
  machines: [[MACHINE, MT, "Complex Assembly Line 001", "Integration Lab A"]],
  state_feature_defs: features.map(([featureKey, valueType, allowedValues, , description]) => [MT, featureKey, description || featureKey, valueType, allowedValues]),
  resources: [
    [MACHINE, "TECH-CAL-01", "Technician A", "technician", 1, "true", "{\"team\":\"A\"}"],
    [MACHINE, "TECH-CAL-02", "Technician B", "technician", 1, "true", "{\"team\":\"B\"}"],
    [MACHINE, "FIX-CAL-01", "Assembly fixture", "fixture", 1, "true", ""],
    [MACHINE, "QA-CAL-01", "Inspector", "inspector", 1, "true", ""],
    [MACHINE, "BENCH-CAL-01", "Calibration bench", "calibration_bench", 1, "true", ""],
    [MACHINE, "CRANE-CAL-01", "Overhead crane", "crane", 1, "true", ""],
  ],
  activity_nodes: activityNodes,
  state_nodes: stateNodes,
  scope_guards: scopeGuards,
  rules,
  states: [
    [MACHINE, "START", "current", "All work pending", startFeatures],
    [MACHINE, "TARGET", "target", "Delivery ready", targetFeatures],
  ],
  solve_cases: [
    [
      "FULL_CHAIN_LAYERED",
      MACHINE,
      "START",
      "TARGET",
      "minimize_makespan",
      "[{\"type\":\"minimize_makespan\",\"weight\":1},{\"type\":\"minimize_activity_group_span\",\"weight\":1},{\"type\":\"minimize_activity_group_gaps\",\"weight\":1}]",
      "",
      13,
      180,
    ],
  ],
  maintenance_intents: [
    [
      MT,
      "SENSOR_FAULT",
      "Repair sensor fault before delivery",
      "REPAIR_PACK",
      "Observed sensor fault should trigger repair and allow the electrical/integration chain to continue.",
      "BLOCKAGE_CLEAR;SENSOR_CALIBRATED",
      "PREP_PACK;ELECTRIC_PACK;REPAIR_PACK;INTEGRATION_PACK",
      "blockage_reason:eq:sensor_fault",
      "blockage_reason:eq:none",
      "true",
      "{\"severity\":\"high\"}",
    ],
  ],
  layered_health_checks: [
    [
      MT,
      "FULL_CHAIN_DELIVERY_HEALTH",
      "Full-chain delivery health",
      "DELIVERY_READY",
      "PREP_PACK;MECH_PACK;ELECTRIC_PACK;HYDRAULIC_PACK;INTEGRATION_PACK;QA_PACK;DELIVERY_PACK",
      "false",
      "Validate imported providers, guards, maintenance repair and final delivery reachability.",
    ],
  ],
  instructions: [
    ["purpose", "Import this workbook through POST /api/v1/imports/scenario or the Data Management import dialog."],
    ["coverage", "Covers layered activity/state trees, Scope Guards, maintenance intents, health checks, multi-resource scheduling and repeated numeric cleaning."],
    ["numeric repeat", "OP_CAL_CLEAN_INCREMENT increments cleanliness by 20; START=0 and TARGET=80 should produce four rule instances."],
    ["blockage", "Use OP_CAL_CLEAN_INCREMENT or OP_CAL_SENSOR_CAL task step_id for Strategy A/AB replan checks; Strategy B uses blockage_reason=sensor_fault."],
  ],
  notes: [
    ["This workbook is intentionally compact enough for integration tests while still exercising the V0.3 full-chain behavior."],
    ["The inactive spare fixture rule validates importer inactive handling and should not appear in normal solves."],
  ],
};

const workbook = Workbook.create();
for (const [sheetName, header] of Object.entries(headers)) {
  const sheet = workbook.worksheets.add(sheetName);
  const rows = [header, ...(sheets[sheetName] || [])];
  const colCount = Math.max(...rows.map((row) => row.length));
  const normalized = rows.map((row) => {
    const next = [...row];
    while (next.length < colCount) next.push("");
    return next;
  });
  sheet.getRangeByIndexes(0, 0, normalized.length, colCount).values = normalized;
  sheet.getRangeByIndexes(0, 0, 1, colCount).format = {
    fill: "#1F4E79",
    font: { bold: true, color: "#FFFFFF" },
  };
  sheet.freezePanes.freezeRows(1);
  const used = sheet.getUsedRange();
  used.format.wrapText = true;
  used.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  used.format.autofitColumns();
}

const summary = workbook.worksheets.add("scenario_summary");
summary.getRange("A1:D8").values = [
  ["Area", "Count", "Signal", "Notes"],
  ["Rules", rules.length, "planner/scheduler", "Includes one inactive rule and one repair rule."],
  ["Activity nodes", activityNodes.length, "layered activity tree", "1 root, 9 packages, 11 leaf activities."],
  ["State nodes", stateNodes.length, "layered state tree", "Atomic leaves are targetable by layered and maintenance solves."],
  ["Scope guards", scopeGuards.length, "effective preconditions", "Guards force package-level prerequisite expansion."],
  ["Resources", sheets.resources.length, "multi-resource schedule", "Technician, fixture, inspector, calibration bench and crane."],
  ["Numeric repeats", 4, "repeated op instances", "Cleanliness 0 to 80 through +20 passes."],
  ["Maintenance intents", sheets.maintenance_intents.length, "joint maintenance solve", "Sensor fault clears blockage_reason."],
];
summary.getRange("A1:D1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
summary.getUsedRange().format.wrapText = true;
summary.getUsedRange().format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
summary.getUsedRange().format.autofitColumns();
summary.freezePanes.freezeRows(1);

await fs.mkdir(outDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outPath);
await fs.rm(`${outPath}.inspect.ndjson`, { force: true });
console.log(outPath);
