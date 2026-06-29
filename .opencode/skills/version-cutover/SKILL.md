---
name: version-cutover
description: Archive current STATE document and bootstrap the next version
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: context-management
---

## What I do

- Verify all tasks in the current STATE document are complete
- Archive the current STATE and completed TICKETs
- Bootstrap the next version's STATE document
- Propose the first TICKET for the new version
- Preserve references to any relevant global superpowers specs and plans across
  the version boundary

## When to use me

Use this when ALL tasks in the current STATE document are marked complete
and you are ready to begin the next version. Do not use mid-version.

## Pre-cutover checklist

Before generating any output, I will verify by reading the current STATE file:

- [ ] All STEP tasks are marked ✅
- [ ] No hanging decisions marked as blocking
- [ ] No ANCHOR violations flagged but unresolved
- [ ] All acceptance criteria (验收标准) have been verified

If any item is unmet, I will list what remains and **refuse to proceed**.

## Execution steps

### Step 1: Verify readiness

Read `docs/STATE_V*.md` and check the pre-cutover checklist above.
If not ready, output what remains and stop.

### Step 2: Generate ARCHIVE

Create `docs/archive/ARCHIVE_VX.X.md` with:
- Version target (one sentence)
- Completed feature list
- Key architectural decisions made (with rationale)
- Known limitations carried forward
- Final data model state
- Format: concise, ≤ 200 lines

### Step 3: Archive completed TICKETs

Move all `docs/TICKET_*.md` files to `docs/archive/`:
- Rename to `docs/archive/TICKET_XXX.md`
- Use bash `mv` commands

### Step 4: Archive current STATE

Rename `docs/STATE_VX.X.md` to `docs/archive/STATE_VX.X.md`

### Step 5: Bootstrap new STATE

Create `docs/STATE_VX+1.md` with the standard structure:

1. **本版本目标**: From ANCHOR.md roadmap for the next version
2. **当前已完成**: Merge ALL prior versions' completed work
3. **已知技术债**: Carry forward from archive + any new ones
4. **本版本变更**: Populated from ANCHOR.md roadmap
5. **任务完成状态**: All items reset to `[ ] 未开始`
6. **当前已知问题**: Empty, ready for new entries
7. **深入参考**: Updated links

If there are still relevant approved specs or unfinished plans under
`docs/superpowers/`, carry forward references to them in the new STATE file's
reference or notes sections instead of losing that execution context.

### Step 6: Check ANCHOR.md

Ask the user: "ANCHOR.md 是否需要更新？（99% 情况下不需要）"

Only modify ANCHOR.md if the user confirms a fundamental change is needed.
If modified, add a dated change note at the top.

### Step 7: Create first TICKET

Propose and create `docs/TICKET_XXX.md` for the first task of the new version,
derived from the new STATE document's STEP 1 items.

If a valid approved spec or unfinished plan already exists for the new version,
prefer deriving the first TICKET from that artifact rather than inventing a new
scope from scratch.

### Step 8: Reconcile project context with global workflows

Before finishing cutover, verify these alignment rules:

- Archived version documents still point to the superpowers artifacts they used
  when those references matter for traceability
- The new STATE references any carried-forward spec or plan that remains active
- No outdated plan is presented as current if the version boundary invalidated
  it; mark it superseded instead
- The first TICKET for the new version clearly states whether the next session
  should start with `brainstorming`, `writing-plans`, or `plan-execution`

## Output summary

After all steps complete, output:

```
版本切换完成
  归档：STATE_VX.X.md → archive/
  归档：TICKET_XXX~YYY → archive/
  新建：STATE_VX+1.md
  新建：TICKET_ZZZ.md (首个任务)
  superpowers：已校准相关 spec/plan 引用

下一步：运行 /session-start 开始新版本开发
```

If no superpowers artifact needs carrying forward, state that explicitly in the
summary rather than omitting the check.

## File paths reference

```
docs/STATE_V*.md         — current state (to be archived)
docs/TICKET_*.md         — active tickets (to be archived)
docs/archive/            — destination for archives
docs/ANCHOR.md           — check if update needed (rare)
docs/superpowers/specs/   — specs that may remain relevant across versions
docs/superpowers/plans/   — plans that may need carry-forward or superseding
```
