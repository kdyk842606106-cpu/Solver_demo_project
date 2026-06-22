---
name: session-start
description: Load project context and prepare for a focused development session
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: context-management
---

## What I do

Automatically load the project's 3-layer context system, confirm understanding,
and prepare for focused development work.

This skill is the project-level entry point. It loads project context first,
then routes the session into the appropriate global superpowers workflow when
design, planning, or plan execution is needed.

## When to use me

Use this at the **start of every new conversation** before any development work.
Always use me first — do not skip context loading even for "small" tasks.

After context is loaded and confirmed, decide whether the task should remain in
the current session flow or hand off to a global superpowers skill.

## Execution steps

### Step 1: Read ANCHOR (system constitution)

Read the file `docs/ANCHOR.md` in full. This contains the permanent system
principles, architecture, constraints, and glossary that govern all development.

### Step 2: Read STATE (current version snapshot)

Find and read the current STATE file. Use glob pattern `docs/STATE_V*.md` to
locate it. There should be exactly one. Read it in full. This tells you:
- What has been built (V0.1 baseline)
- What this version aims to do
- Current task completion status
- Any hanging decisions from previous sessions

### Step 3: Find and read active TICKET

Search for TICKET files using glob pattern `docs/TICKET_*.md`.
- If one or more TICKET files exist, read the one with the highest number
  (this is the current active ticket).
- If no TICKET files exist, note this — you will need to propose creating one.

### Step 4: Check for hanging decisions

In the STATE document, look at the "当前已知问题 / 决策悬挂" section.
If there are unresolved items:
- List them prominently
- Ask the user whether to resolve them now or defer

### Step 5: Confirm understanding

Output EXACTLY in this format (in Chinese), then STOP and wait for user confirmation:

```
已就绪
- 当前版本：[VERSION from STATE doc]
- 本次任务：[TICKET title, or "未指定 — 需要创建 TICKET" if no ticket found]
- 悬挂问题：[list from STATE doc, or "无"]
- 本次不做：[out-of-scope items from TICKET, or "待确认" if no ticket]
```

### Step 6: Wait for confirmation

Do NOT begin any implementation until the user explicitly confirms.
If the user wants to change the task scope, update the TICKET file accordingly.

### Step 7: Route into the right workflow

Once the user confirms context and scope, decide the next workflow based on the
task type:

- **New feature / behavior change / workflow design / structural change**:
  invoke global `brainstorming` first. Do not skip design, even if the change
  looks small.
- **Approved spec already exists**: invoke global `writing-plans` to create the
  executable implementation plan.
- **Approved plan already exists**: invoke global `executing-plans` to execute
  the plan task-by-task.
- **Bug diagnosis / narrow fix / non-creative implementation**: continue in the
  current session, but still obey `ANCHOR.md`, `STATE`, and `TICKET`.

If the correct next step is a global superpowers skill, explicitly announce the
handoff so the user can see which workflow is being used.

### Step 8: Preserve project context during handoff

When invoking a global superpowers skill, keep these project-level constraints
active throughout the session:

- `ANCHOR.md` remains the source of truth for architecture and constraints
- `STATE_V*.md` remains the source of truth for current version status
- `TICKET_*.md` remains the source of truth for current scoped work
- Any spec or plan produced by global workflows must stay aligned with the
  current TICKET scope, or the TICKET must be updated before execution

## If no TICKET exists

After confirming ANCHOR + STATE are loaded, look at the STATE document's
task completion status. Identify the next pending STEP/task and propose
creating a TICKET for it:

```
未找到活跃的 TICKET 文件。

根据 STATE 文档，下一个待完成的任务是：
  [STEP X: task name]

是否为此任务创建 TICKET？
```

If the user confirms, create the TICKET file following the standard format
(see existing TICKET files for reference), then re-run the confirmation output.

## Rules I follow during this session

- I will not make architectural decisions that contradict ANCHOR.md
- If I encounter a conflict between ANCHOR.md and current code, I will flag it
  and wait for the user's decision before proceeding
- If a task exceeds what can be completed in one conversation, I will stop,
  summarize progress, and trigger session-end
- I will never hardcode values that ANCHOR.md requires to be dynamic
- Every file I create or modify must be consistent with STATE document's
  description of the current codebase
- I will mark TICKET subtasks as completed (□ → ✅) as I finish them
- I will not use a global superpowers workflow without first loading project
  context through this skill
- If a global workflow produces a spec or plan, I will treat that artifact as
  subordinate to project context until it is reflected in TICKET/STATE

## File paths reference

```
docs/ANCHOR.md           — Layer 1: permanent principles
docs/STATE_V*.md         — Layer 2: current version snapshot (glob to find)
docs/TICKET_*.md         — Layer 3: current task ticket (glob to find)
docs/v0.2-spec.md        — detailed V0.2 spec (read on demand)
docs/protocols/           — module implementation details (read on demand)
docs/superpowers/specs/   — global brainstorming output to track
docs/superpowers/plans/   — global writing-plans output to track
```
