---
name: "source-command-version-cutover"
description: "Archive current STATE document and bootstrap the next version"
---

# source-command-version-cutover

Use this skill when the user asks to run the migrated source command `version-cutover`.

## Command Template

## What I do

- Verify all tasks in the current STATE document are complete
- Archive the current STATE and completed TICKETs
- Bootstrap the next version's STATE document
- Propose the first TICKET for the new version

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

### Step 6: Check ANCHOR.md

Ask the user: "ANCHOR.md 是否需要更新？（99% 情况下不需要）"

Only modify ANCHOR.md if the user confirms a fundamental change is needed.
If modified, add a dated change note at the top.

### Step 7: Create first TICKET

Propose and create `docs/TICKET_XXX.md` for the first task of the new version,
derived from the new STATE document's STEP 1 items.

## Output summary

After all steps complete, output:

```
版本切换完成
  归档：STATE_VX.X.md → archive/
  归档：TICKET_XXX~YYY → archive/
  新建：STATE_VX+1.md
  新建：TICKET_ZZZ.md (首个任务)

下一步：运行 /session-start 开始新版本开发
```

## File paths reference

```
docs/STATE_V*.md         — current state (to be archived)
docs/TICKET_*.md         — active tickets (to be archived)
docs/archive/            — destination for archives
docs/ANCHOR.md           — check if update needed (rare)
```
