---
name: session-end
description: Sync completed work back to the STATE document and prepare handoff
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: context-management
---

## What I do

Synchronize all progress from this session back to the project's context documents,
ensuring the next session (or a different AI) can seamlessly continue.

This skill is the project-level closing step. It syncs project documents first,
then records any global superpowers artifacts created or advanced during the
session so the next workflow can resume cleanly.

## When to use me

Use this at the **end of every conversation**, even if the task is incomplete.
Never close a session without running this skill.

## Execution steps

### Step 1: Read current STATE document

Read the current STATE file (glob `docs/STATE_V*.md`) to understand the
baseline before applying updates.

### Step 2: Read active TICKET

Read the current TICKET file (glob `docs/TICKET_*.md`, highest number)
to check which subtasks were in scope.

### Step 3: Generate completion report

Output this section for the user:

```
## 1. 完成情况

TICKET-XXX: [title]

  ✅ [subtask] — completed
  ⚠️ [subtask] — partially done: [reason]
  ❌ [subtask] — not done: [reason]
```

### Step 4: Update STATE document

**Actually edit** the `docs/STATE_V*.md` file with these changes:

1. **任务完成状态**: Change `□` to `✅` for completed subtasks
2. **当前已知问题**: Add any new hanging decisions discovered during development
3. If new files were created, add them to the appropriate section

Use the Edit tool to make precise changes. Do NOT rewrite the entire file.

### Step 5: Update TICKET

**Actually edit** the `docs/TICKET_*.md` file:
- Mark completed subtasks: `□` → `✅`
- If ALL subtasks are done, add a completion note at the top:
  `> 状态：已完成 — [date]`

### Step 5.5: Record superpowers workflow state

If this session used any global superpowers workflow, capture that state in the
handoff and project context:

- If a spec was created or updated, record its path under
  `docs/superpowers/specs/` in the STATE document's relevant section or notes
- If a plan was created or updated, record its path under
  `docs/superpowers/plans/` in the STATE document's relevant section or notes
- If execution stopped mid-plan, note exactly which task or step should resume
  next
- If the next session must use a specific global skill, state that explicitly
  in the final summary

### Step 6: ANCHOR violation check

Review all code produced this session against ANCHOR.md constraints.
Output one of:
- "无违规" — if all code complies
- List of specific violations with file:line references

### Step 7: Propose next TICKET

If the current TICKET is complete, propose the next one:

1. Check STATE document for the next pending STEP/subtask
2. Output a draft TICKET in the standard format
3. Ask the user: "是否创建此 TICKET？"
4. If confirmed, write it to `docs/TICKET_XXX.md` (next sequential number)

If the current TICKET is incomplete, output:

```
当前 TICKET 未完成，下次对话继续使用 TICKET-XXX。
剩余任务：
  □ [remaining subtask 1]
  □ [remaining subtask 2]
```

### Step 8: Final summary

Output a one-paragraph handoff summary that the next session's session-start
can use to quickly understand where things left off.

If superpowers artifacts exist, the summary must include:
- Which global skill was last used
- The latest approved spec path, if any
- The latest active plan path, if any
- Whether the next session should brainstorm, write a plan, execute a plan, or
  continue direct implementation

## Important rules

- **Always write changes to files** — do not just output text for the user to
  manually copy. Use Edit/Write tools to update STATE and TICKET documents.
- **Be precise with diffs** — only change lines that need changing in STATE.
- **Never mark a task as complete if tests fail** — mark as ⚠️ with the
  failure reason instead.
- **Record ALL decisions made during the session** — even small ones that
  might affect future work. Put them in STATE's "当前已知问题" section if
  they need future attention.
- **Do not let global workflow artifacts drift from project context** — if a
  spec or plan changes scope, reflect that in TICKET/STATE before ending.
- **Project context wins on conflict** — if a global workflow artifact conflicts
  with `ANCHOR.md` or the active TICKET, flag it instead of silently preserving
  the mismatch.

## File paths reference

```
docs/STATE_V*.md         — edit this to sync progress
docs/TICKET_*.md         — edit to mark subtask completion
docs/ANCHOR.md           — read-only reference for violation check
docs/superpowers/specs/   — brainstorming artifacts to reference
docs/superpowers/plans/   — plan artifacts to reference
```
