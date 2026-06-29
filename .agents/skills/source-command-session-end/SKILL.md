---
name: "source-command-session-end"
description: "Sync completed work back to the STATE document and prepare handoff"
---

# source-command-session-end

## Canonical Instructions

Use this skill when the user asks to run `session-end`, or at the end of a
development session that changed code, docs, specs, plans, or project state.
This section supersedes any legacy migrated command text below.

Purpose:

- summarize what happened
- update STATE precisely
- update the active TICKET precisely
- record superpowers spec/plan state when those workflows were used
- report verification and remaining work

Execution:

1. Read the current non-archived `docs/STATE_V*.md`.
2. Read the highest-numbered non-archived `docs/TICKET_*.md`.
3. Report completion status in Chinese.
4. Edit only necessary lines in STATE:
   - completed subtasks
   - new known issues or decisions
   - important new files, specs, plans, or tests
   - verification results
5. Edit only necessary lines in the active TICKET:
   - mark completed subtasks only after verification passes
   - note partial work and failure reasons when relevant
   - add a dated completion note if all scoped work is complete
6. If `brainstorming`, `writing-plans`, or `plan-execution` was used, record:
   - latest spec path under `docs/superpowers/specs/`
   - latest plan path under `docs/superpowers/plans/`
   - the last workflow used
   - the exact next workflow or task to resume
7. Check the session's changes against `docs/ANCHOR.md` and report either
   `无违反` or concise violations with file references.
8. Propose the next TICKET if the active TICKET is complete; otherwise list
   remaining scoped subtasks.
9. End with a one-paragraph Chinese handoff summary for the next session.

Rules:

- Always update files when the session produced durable state changes.
- Never mark work complete if verification failed.
- Keep edits precise and local.
- Project context wins over any global superpowers artifact.

Use this skill when the user asks to run the migrated source command `session-end`.

## Command Template

## What I do

Synchronize all progress from this session back to the project's context documents,
ensuring the next session (or a different AI) can seamlessly continue.

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

## Important rules

- **Always write changes to files** — do not just output text for the user to
  manually copy. Use Edit/Write tools to update STATE and TICKET documents.
- **Be precise with diffs** — only change lines that need changing in STATE.
- **Never mark a task as complete if tests fail** — mark as ⚠️ with the
  failure reason instead.
- **Record ALL decisions made during the session** — even small ones that
  might affect future work. Put them in STATE's "当前已知问题" section if
  they need future attention.

## File paths reference

```
docs/STATE_V*.md         — edit this to sync progress
docs/TICKET_*.md         — edit to mark subtask completion
docs/ANCHOR.md           — read-only reference for violation check
```
