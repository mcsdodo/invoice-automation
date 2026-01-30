---
name: plan-review-skill
description: Use for iterative plan/design review with two-phase approval workflow
---

# Plan Review Skill

## When to Use

- Before starting implementation (review plan)
- When examining design documents
- Validating task specifications
- Assessing feasibility of proposed solutions

## Key Differentiator: Iterative Approach

Unlike single-pass reviews, this skill uses:
1. **Multiple iterations** (max 4)
2. **Quality gate**: No new findings = comprehensive review
3. **Documentation**: Creates `_plan-review.md` tracking findings
4. **Two-phase**: Review -> User Approval -> Revise Plan

## Configuration

- **Max Iterations**: 4
- **Reviewer Role**: Plan Auditor
- **Quality Gate**: No new findings in one iteration

## Project-Specific Context

### Plan Locations
Plans live in `_tasks/{NN}-{name}/`:
- `01-task.md` - Requirements, user story
- `02-plan.md` - Implementation plan
- `02-design.md` - Architecture decisions (alternative)

### Plan Quality Standards
Per `_tasks/CLAUDE.md`:
- Include specific file paths
- Verification criteria for each step
- Link to tech debt if applicable
- Commit planning docs BEFORE implementation

## Phase 1: Review & Documentation

### Step 1: Read Target Plan
Read the plan/design document completely.

### Step 2: Create Review Document
Create `_plan-review.md` in the plan folder:

```markdown
# Plan Review: [Feature Name]

**Date:** YYYY-MM-DD
**Auditor:** Claude Code
**Status:** In Progress
**Plan Location:** _tasks/{NN}-{name}/02-plan.md

## Iterations

### Iteration 1
| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Critical | | | [ ] |
| Important | | | [ ] |
| Minor | | | [ ] |
```

### Step 3: Iterative Review Loop

For each iteration (max 4):

**Check these aspects:**

1. **Completeness**
   - All requirements have corresponding tasks?
   - Edge cases considered?
   - Error scenarios addressed?

2. **Feasibility**
   - Tasks achievable with current codebase?
   - Dependencies identified?
   - Blockers acknowledged?

3. **Clarity**
   - Specific file paths included?
   - Steps unambiguous?
   - Verification criteria defined?

4. **YAGNI/DRY**
   - Unnecessary scope creep?
   - Duplication with existing code?
   - Over-engineering?

5. **Project Alignment**
   - Follows documentation locality principle?
   - Uses existing patterns (workflow states, Telegram callbacks)?
   - Updates correct documentation files?

**Categorize findings:**
- **Critical**: Missing requirements, infeasible tasks, architectural issues
- **Important**: Unclear steps, missing file paths, no verification
- **Minor**: Minor wording, formatting, optional improvements

**Exit condition**: No new findings in one iteration.

### Step 4: Present Summary
```markdown
## Summary

### Critical (Must Address)
1. [Missing error handling for X scenario]

### Important (Should Address)
1. [Step 3 lacks specific file path]

### Minor (Nice to Have)
1. [Consider adding diagram]

**Recommendation**: [Revise before implementation / Proceed with notes]
```

### Step 5: Await User Approval
Present findings and ask which to address.

## Phase 2: Plan Revision

### Step 1: Apply Changes
Revise the plan document with approved changes.
Mark items as checked in `_plan-review.md`.

### Step 2: Commit Updated Plan
```bash
git add _tasks/{NN}-{name}/
git commit -m "docs: revise plan based on review

- [List of revisions]"
```

### Step 3: Update Review Document
```markdown
**Status:** Complete
**Revisions Applied:** [List]
**Plan Ready for Implementation:** Yes
```

## Plan Quality Checklist

Final plan should have:
- [ ] All requirements mapped to tasks
- [ ] Specific file paths for each change
- [ ] Verification steps for each task
- [ ] Dependencies ordered correctly
- [ ] Scope bounded (no creep)
- [ ] Complexity appropriate for task

## Related

- `code-review-skill` - For reviewing implementation
- `test-review-skill` - For reviewing test coverage
