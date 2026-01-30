---
name: code-review-skill
description: Use for iterative code review with documentation and two-phase approval workflow
---

# Code Review Skill

## When to Use

- After completing a feature implementation
- Before creating a pull request
- When validating code quality

## Key Differentiator: Iterative Approach

Unlike single-pass reviews, this skill uses:
1. **Multiple iterations** (max 4)
2. **Quality gate**: No new findings = comprehensive review
3. **Documentation**: Creates `_code-review.md` tracking findings
4. **Two-phase**: Review -> User Approval -> Implement

## Configuration

- **Max Iterations**: 4
- **Reviewer Role**: Senior Code Reviewer
- **Quality Gate**: No new findings in one iteration

## Phase 1: Review & Documentation

### Step 1: Context Gathering
- Get code diff: `git diff HEAD~1` or `git diff main...HEAD`
- Or read specific target files

### Step 2: Baseline Testing
Execute tests without modifications:
```bash
python -m pytest tests/ -v
```
Document results.

### Step 3: Create Review Document
Create `_code-review.md` in working directory:

```markdown
# Code Review: [Feature Name]

**Date:** YYYY-MM-DD
**Reviewer:** Claude Code
**Status:** In Progress

## Baseline Test Results
- Tests: X passed, Y failed

## Iterations

### Iteration 1
| Severity | Finding | Location | Status |
|----------|---------|----------|--------|
| Critical | | | [ ] |
| Important | | | [ ] |
| Minor | | | [ ] |

### Iteration 2
...
```

### Step 4: Iterative Review Loop

For each iteration (max 4):

**Check these areas:**
1. **Correctness**: Does code do what it should?
2. **Error Handling**: Are errors caught and handled?
3. **Security**: Any vulnerabilities (injection, XSS, etc.)?
4. **Project Patterns**: Follows existing conventions?
5. **Tests**: Are there tests for new functionality?
6. **Documentation**: Updated READMEs if needed?

**Categorize findings:**
- **Critical**: Bugs, security issues, data corruption risks
- **Important**: Performance, maintainability, missing tests
- **Minor**: Style, naming, documentation gaps

**Exit condition**: No new findings in one iteration.

### Step 5: Present Summary
After iterations complete, present consolidated findings:

```markdown
## Summary

### Critical (Must Fix)
1. [Finding description]

### Important (Should Fix)
1. [Finding description]

### Minor (Nice to Have)
1. [Finding description]

**Recommendation**: [Fix critical/all/none before merge]
```

### Step 6: Await User Approval
Present findings and ask which to address.

## Phase 2: Implementation & Validation

### Step 1: Apply Fixes
Implement approved corrections. Mark items as checked in `_code-review.md`.

### Step 2: Re-run Tests
```bash
python -m pytest tests/ -v
```
Address any failures.

### Step 3: Commit
```bash
git add .
git commit -m "fix: address code review findings

- [List of fixes]"
```

### Step 4: Update Review Document
Mark review as complete:
```markdown
**Status:** Complete
**Fixes Applied:** [List]
**Final Test Results:** All passing
```

## Project-Specific Checks

### Python (src/)
- Type hints present
- Async/await used correctly
- Pydantic models for config and data classes
- Error handling with Telegram notifications
- Gmail API patterns followed
- State persistence correct

### Workflow (src/workflow.py)
- State transitions correct
- Persistence to JSON working
- Telegram callbacks handled properly

### PDF Processing (src/pdf/)
- pdfplumber extraction correct
- pypdf merge order correct
- Playwright HTML→PDF working

### Email (src/gmail/)
- OAuth flow handled
- Thread detection correct
- Attachment handling proper

## Related

- `test-review-skill` - For test coverage gaps
- `plan-review-skill` - For design review before coding
