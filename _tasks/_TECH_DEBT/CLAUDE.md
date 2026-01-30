# Tech Debt Documentation Guidelines

This folder tracks technical debt items discovered during development.

## File Structure

Each tech debt item gets its own numbered markdown file:

```
_TECH_DEBT/
├── CLAUDE.md                              # This file
└── {NN}-{descriptive-name}.md             # Individual tech debt items (numbered)
```

## File Naming

Use sequential numbering like `_tasks/`:
- `01-first-issue.md`
- `02-second-issue.md`
- `03-third-issue.md`

**CRITICAL - Finding next file number:**

```
# Check BOTH locations (items move to _done when completed)
Search(pattern: "[0-9][0-9]-*.md", path: "_tasks/_TECH_DEBT")
Search(pattern: "[0-9][0-9]-*.md", path: "_tasks/_TECH_DEBT/_done")
```

Extract highest file number from BOTH results, add 1, zero-pad to 2 digits.

**Do NOT:**
- Guess file numbers without checking
- Forget to check `_TECH_DEBT/_done/` (completed items retain their numbers)

## File Template

```markdown
# Tech Debt: {Title}

**Date:** YYYY-MM-DD
**Priority:** Critical | High | Medium | Low
**Effort:** Low (<2h) | Medium (2-8h) | High (1-3d) | Very High (>3d)
**Component:** `path/to/affected/file.py`
**Status:** Open | In Progress | Fixed | Wont Fix

## Problem

Clear description of the technical debt.

## Impact

- What breaks or degrades because of this?
- What's the maintenance burden?
- What's blocked by this?

## Root Cause

Why does this debt exist? (Historical, time pressure, scope creep, etc.)

## Recommended Solution

The proposed fix with:
- Implementation steps
- Code examples if helpful
- Files affected

## Alternative Options (if any)

Other approaches considered and why they're not recommended.

## Related

- Links to related files, PRs, or other tech debt items

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| YYYY-MM-DD | Initial analysis | Why the item was created |
```

## Priority Guidelines

| Priority | Definition |
|----------|------------|
| **Critical** | Blocks development or causes production issues |
| **High** | Significant maintenance burden or risk |
| **Medium** | Noticeable friction but manageable |
| **Low** | Nice to fix when convenient |

## Effort Guidelines

| Effort | Definition |
|--------|------------|
| **Low** | < 2 hours |
| **Medium** | 2-8 hours |
| **High** | 1-3 days |
| **Very High** | > 3 days |

## When to Create Tech Debt Items

- During code review when you spot issues outside PR scope
- After hotfixes that need proper cleanup
- When discovering architectural inconsistencies
- When implementing workarounds for deeper problems

## Lifecycle

1. **Discovery**: Create file with analysis
2. **Planning**: Create task in `_tasks/{NN}-{name}/` when ready to fix
3. **Resolution**: Update Status to "Fixed", link to commit
4. **Archive**: Move to `_done/` for historical reference

## Decision Log Guidelines

Every tech debt item should include a **Decision Log** table at the bottom to track the chronological history of decisions and changes.

### When to Add Entries

Add a new row to the Decision Log when:
- Creating the initial tech debt item
- Changing the recommended solution approach
- Updating priority or status
- Completing implementation
- Deciding to defer or close as "Won't Fix"

### Entry Format

| Column | Content |
|--------|---------|
| **Date** | YYYY-MM-DD format |
| **Decision** | Brief description (e.g., "Created analysis", "Changed to Option B", "Fixed in commit abc123") |
| **Rationale** | Why this decision was made |
