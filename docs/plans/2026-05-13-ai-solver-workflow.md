# AI Solver Workflow Skill — Implementation Plan
> **For agent:** REQUIRED SUB-SKILL: Use Section 5 (Subagent-Driven Development) or Section 4 (Executing Plans) to implement this plan.

**Goal:** Create an OpenClaw Skill that enables natural language-driven machine planning workflow through the Solver Demo backend.

**Architecture:** A 5-step OpenClaw Skill (`skills/ai-solver-workflow/`) that parses user intent, validates input, calls the backend solve API, validates results, and generates human-readable reports.

**Tech Stack:** OpenClaw Skill framework, Markdown prompts, HTTP client (curl/python), SQLite/PostgreSQL queries for validation.

---

## Context

- Backend: FastAPI on `http://localhost:8000`
- Database: PostgreSQL (Docker), machine `MS010` exists with 27 OPS activities
- Solve endpoint: `POST /api/v1/solve`
- Current limitation: Single resource type per task (multi-space not supported yet)

---

## Task 1: Create Skill Directory Structure

**Files:**
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/SKILL.md`
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/_meta.json`
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/prompts/intent_parser.md`
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/prompts/report_generator.md`

**Step 1:** Create directory structure
```bash
mkdir -p ~/.openclaw/workspace/skills/ai-solver-workflow/prompts
```

**Step 2:** Verify directory exists
```bash
ls -la ~/.openclaw/workspace/skills/ai-solver-workflow/
```
Expected: `prompts/` subdirectory exists

---

## Task 2: Write _meta.json

**Files:**
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/_meta.json`

**Step 1:** Write metadata file
```json
{
  "name": "ai-solver-workflow",
  "description": "AI-driven machine planning workflow for Solver Demo. Parses natural language intent, validates input, calls solve API, validates results, and generates human-readable reports.",
  "version": "1.0.0",
  "author": "OpenClaw Agent",
  "tags": ["solver", "planning", "workflow", "ai"]
}
```

**Step 2:** Verify JSON is valid
```bash
cat ~/.openclaw/workspace/skills/ai-solver-workflow/_meta.json | python3 -m json.tool > /dev/null && echo "Valid JSON"
```
Expected: `Valid JSON`

---

## Task 3: Write Intent Parser Prompt

**Files:**
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/prompts/intent_parser.md`

**Step 1:** Write the prompt template

This prompt will be used by the AI to parse natural language into structured solve parameters.

Content:
```markdown
# Intent Parser Prompt

You are a manufacturing planning assistant. Parse the user's natural language request into structured parameters for a machine planning system.

## Input Format
User message: <natural language description>

## Output Format
Return ONLY a valid JSON object (no markdown code blocks, no extra text):

```json
{
  "machine_code": "string",
  "current_state_label": "string",
  "target_state_label": "string",
  "objective": "minimize_makespan | minimize_cost | minimize_resources | balance_load",
  "objectives": [{"type": "string", "weight": number}],
  "constraints": {
    "priority_hint": "string | null",
    "deadline_hours": "number | null",
    "resource_preferences": ["string"]
  },
  "blockage_constraints": {
    "strategy": "A | B | AB | null",
    "blocked_step_id": "number | null",
    "blocked_op_rule_id": "number | null",
    "strategy_a": {"not_before_offset": "number | null"},
    "strategy_b": {"blockage_reason": "string | null"}
  }
}
```

## Rules
1. `machine_code`: Extract machine identifier (e.g., "MS010"). Default to "MS010" if not specified.
2. `current_state_label`: Infer from context. Default: "初始状态-全部待完成"
3. `target_state_label`: Infer from context. Default: "目标状态-全部完成"
4. `objective`: Map natural language to valid objective:
   - "最快", "最短时间", "赶工" → "minimize_makespan"
   - "最省", "最少人力", "最少资源" → "minimize_resources"
   - "均衡", "平衡" → "balance_load"
   - "最便宜", "最低成本" → "minimize_cost"
   - Default: "minimize_makespan"
5. `constraints.priority_hint`: Extract any priority keywords
6. `constraints.deadline_hours`: Extract explicit deadlines (e.g., "3天内" → 72)
7. All fields must be present. Use null for unknown values.

## Examples

Input: "帮MS010排个整机集成计划，最短时间"
Output:
```json
{
  "machine_code": "MS010",
  "current_state_label": "初始状态-全部待完成",
  "target_state_label": "目标状态-全部完成",
  "objective": "minimize_makespan",
  "objectives": [{"type": "minimize_makespan", "weight": 1.0}],
  "constraints": {
    "priority_hint": "时间优先",
    "deadline_hours": null,
    "resource_preferences": []
  },
  "blockage_constraints": null
}
```

Input: "MS010从当前状态装到完成，3天内搞定"
Output:
```json
{
  "machine_code": "MS010",
  "current_state_label": "初始状态-全部待完成",
  "target_state_label": "目标状态-全部完成",
  "objective": "minimize_makespan",
  "objectives": [{"type": "minimize_makespan", "weight": 1.0}],
  "constraints": {
    "priority_hint": null,
    "deadline_hours": 72,
    "resource_preferences": []
  },
  "blockage_constraints": null
}
```
```

**Step 2:** Verify file exists and is readable
```bash
head -20 ~/.openclaw/workspace/skills/ai-solver-workflow/prompts/intent_parser.md
```
Expected: Shows the prompt header

---

## Task 4: Write Report Generator Prompt

**Files:**
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/prompts/report_generator.md`

**Step 1:** Write the prompt template

This prompt will be used by the AI to convert solver results into human-readable reports.

Content:
```markdown
# Report Generator Prompt

You are a manufacturing planning analyst. Convert solver output into a clear, actionable report for factory floor managers.

## Input Format
```json
{
  "solve_request_id": number,
  "status": "done | failed",
  "candidate_plan_id": number,
  "state_delta": [{"feature_key": "string", "from_value": "string", "to_value": "string"}],
  "critical_path": ["string"],
  "schedule": {
    "makespan": number,
    "tasks": [{
      "step_order": number,
      "op_rule_code": "string",
      "op_rule_name": "string",
      "start_min": number,
      "end_min": number,
      "duration_min": number,
      "resources": [{"resource_code": "string"}],
      "predecessors": [number],
      "step_role": "string"
    }],
    "parallel_groups": [[number]]
  }
}
```

## Output Format
Return a Markdown report in Chinese with the following sections:

### 1. 概览
- 总工期 (days, hours, minutes)
- 优化目标
- 关键路径工序数量
- 并行任务组数量

### 2. 关键路径
- List critical path activities in order
- Highlight longest activities (>24h)

### 3. 甘特图概览 (ASCII or text-based)
- Group by day or week
- Show which activities run in parallel

### 4. 资源占用统计
- Per resource type: total usage time, number of activities
- Identify bottlenecks (resources with highest utilization)

### 5. 风险提示
- Activities with duration > 24h
- Activities with many predecessors (high coordination risk)
- Resource conflicts if any

### 6. 原始数据
- Collapsible JSON block with full schedule data

## Rules
1. All time values: convert minutes to "X天 Y小时 Z分钟" format
2. Use professional but accessible language
3. Highlight critical information with emojis: 🔴 critical, ⚠️ warning, ✅ normal
4. Keep report concise (under 3000 characters for main sections)
5. Include raw data at the end for traceability
```

**Step 2:** Verify file exists
```bash
head -20 ~/.openclaw/workspace/skills/ai-solver-workflow/prompts/report_generator.md
```
Expected: Shows the prompt header

---

## Task 5: Write SKILL.md (Main Skill Definition)

**Files:**
- Create: `~/.openclaw/workspace/skills/ai-solver-workflow/SKILL.md`

**Step 1:** Write the main skill definition

This is the core file that defines the 5-step workflow, trigger conditions, and execution logic.

Content structure:
- Skill metadata (name, description, version)
- Trigger conditions (when to activate)
- Step 1: Intent Parser (调用 LLM 解析用户输入)
- Step 2: Input Validator (验证 machine_id, state_id, objective)
- Step 3: Backend Caller (HTTP POST /api/v1/solve)
- Step 4: Result Validator (检查 makespan, tasks count, resource conflicts)
- Step 5: Report Generator (调用 LLM 生成报告)
- Error handling (每步失败的降级策略)
- Configuration (backend URL, timeout settings)

**Step 2:** Verify file exists and contains all 5 steps
```bash
grep -c "Step [1-5]:" ~/.openclaw/workspace/skills/ai-solver-workflow/SKILL.md
```
Expected: `5`

---

## Task 6: Validate Complete Skill

**Files:**
- Read: `~/.openclaw/workspace/skills/ai-solver-workflow/SKILL.md`
- Read: `~/.openclaw/workspace/skills/ai-solver-workflow/_meta.json`

**Step 1:** Check all required files exist
```bash
ls -la ~/.openclaw/workspace/skills/ai-solver-workflow/
ls -la ~/.openclaw/workspace/skills/ai-solver-workflow/prompts/
```
Expected: SKILL.md, _meta.json, prompts/intent_parser.md, prompts/report_generator.md

**Step 2:** Validate _meta.json
```bash
cat ~/.openclaw/workspace/skills/ai-solver-workflow/_meta.json | python3 -m json.tool
```
Expected: Pretty-printed valid JSON

**Step 3:** Validate SKILL.md has required sections
```bash
grep -E "^## (Trigger|Step [1-5]|Error Handling|Configuration)" ~/.openclaw/workspace/skills/ai-solver-workflow/SKILL.md
```
Expected: Lists all 5 steps plus trigger, error handling, configuration

---

## Task 7: Test End-to-End Workflow

**Files:**
- None (uses existing backend)

**Step 1:** Verify backend is running
```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected: `{"status": "healthy", "version": "0.1.0"}`

**Step 2:** Test solve API with known parameters
```bash
curl -s -X POST http://localhost:8000/api/v1/solve \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": 9001,
    "current_state_id": 9001,
    "target_state_id": 9002,
    "objective": "minimize_makespan"
  }' | python3 -m json.tool | head -30
```
Expected: `{"status": "done", "solve_request_id": ..., "schedule": {...}}`

**Step 3:** Verify response structure
```bash
# Extract key fields
curl -s -X POST http://localhost:8000/api/v1/solve \
  -H "Content-Type: application/json" \
  -d '{
    "machine_id": 9001,
    "current_state_id": 9001,
    "target_state_id": 9002,
    "objective": "minimize_makespan"
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status')); print('makespan:', d.get('schedule',{}).get('makespan')); print('tasks:', len(d.get('schedule',{}).get('tasks',[])))"
```
Expected: `status: done`, `makespan: <number>`, `tasks: 27`

---

## Verification Checklist

- [ ] All 4 files created (SKILL.md, _meta.json, 2 prompts)
- [ ] _meta.json is valid JSON
- [ ] SKILL.md contains all 5 steps
- [ ] Intent parser prompt has examples and rules
- [ ] Report generator prompt has output format specification
- [ ] Backend health check passes
- [ ] Solve API returns successful result
- [ ] Result contains 27 tasks for MS010
- [ ] Error handling documented for each step

---

## Notes

### Future Enhancements (out of scope for MVP)
1. Multi-space support (when scheduler supports it)
2. Weak dependency handling
3. Interactive plan adjustment ("把 OPS011 提前到周二")
4. Historical plan comparison ("和上次计划有什么不同")
5. Resource bottleneck visualization

### Known Limitations
1. Single resource type per task (scheduler limitation)
2. Weak dependencies ignored (data not in DB)
3. Natural language parsing depends on LLM quality
4. No persistence of conversation context between sessions
