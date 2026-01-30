---
name: test-review-skill
description: Use for iterative test coverage analysis with two-phase approval workflow
---

# Test Review Skill

## When to Use

- After implementing a feature (verify test coverage)
- Before release (quality assurance)
- When extending test suites
- Routine test health assessments

## Key Differentiator: Iterative Approach

Unlike single-pass analysis, this skill uses:
1. **Multiple iterations** (max 4)
2. **Quality gate**: No new gaps = comprehensive analysis
3. **Documentation**: Creates `_test-review.md` tracking gaps
4. **Two-phase**: Analyze -> User Approval -> Implement

## Configuration

- **Max Iterations**: 4
- **Reviewer Role**: Test Coverage Analyst
- **Quality Gate**: No new gaps in one iteration

## Project-Specific Test Locations

| Module | Test Path | Framework |
|--------|-----------|-----------|
| All | `tests/` | pytest |
| Unit | `tests/unit/` | pytest |
| Integration | `tests/integration/` | pytest |

### Test Commands
```bash
# All tests
python -m pytest -v

# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests
python -m pytest tests/integration/ -v

# With coverage
python -m pytest --cov=src --cov-report=term-missing
```

## Phase 1: Analysis & Discovery

### Step 1: Locate Test Files
Find existing tests for target module:
```bash
ls tests/unit/test_*.py
ls tests/integration/test_*.py
```

### Step 2: Execute Baseline
Run tests to establish current state:
```bash
python -m pytest --cov=src --cov-report=term-missing
```
Document pass/fail counts and coverage percentage.

### Step 3: Create Review Document
Create `_test-review.md` in working directory:

```markdown
# Test Review: [Module/Feature Name]

**Date:** YYYY-MM-DD
**Analyst:** Claude Code
**Status:** In Progress

## Baseline Metrics
- Tests: X passed, Y failed
- Coverage: XX%
- Uncovered lines: [list]

## Iterations

### Iteration 1
| Severity | Gap | Location | Status |
|----------|-----|----------|--------|
| Critical | | | [ ] |
| Important | | | [ ] |
| Minor | | | [ ] |
```

### Step 4: Iterative Analysis Loop

For each iteration (max 4):

**Analyze these aspects:**
1. **Function Coverage**: Are all functions tested?
2. **Branch Coverage**: Are all if/else paths covered?
3. **Edge Cases**: Boundary conditions, empty inputs, nulls
4. **Error Paths**: Exception handling tested?
5. **Integration Points**: External service mocks correct?
6. **Business Logic**: Core calculations verified?

**Categorize gaps:**
- **Critical**: Core business logic untested, security paths
- **Important**: Error handling, edge cases
- **Minor**: Utility functions, logging paths

**Exit condition**: No new gaps in one iteration.

### Step 5: Present Summary
```markdown
## Summary

### Critical Gaps (Must Cover)
1. [Function X has no tests - core business logic]

### Important Gaps (Should Cover)
1. [Error path in Y not tested]

### Minor Gaps (Nice to Have)
1. [Logging branch uncovered]

**Current Coverage**: XX%
**Projected Coverage After Fixes**: YY%
```

### Step 6: Await User Approval
Present gaps and ask which to address.

## Phase 2: Implementation

### Step 1: Write Tests
For each approved gap, write tests following project patterns:

```python
# Example test pattern
import pytest
from unittest.mock import Mock, patch, AsyncMock

class TestFeatureName:
    """Tests for [feature description]."""

    @pytest.fixture
    def mock_gmail(self):
        return AsyncMock()

    @pytest.fixture
    def mock_telegram(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_happy_path(self, mock_gmail):
        """Test normal operation."""
        # Arrange
        # Act
        # Assert

    def test_edge_case(self):
        """Test boundary condition."""

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test exception path."""
```

### Step 2: Execute Full Suite
```bash
python -m pytest -v
python -m pytest --cov=src --cov-report=term-missing
```
Verify no regressions and coverage improved.

### Step 3: Commit
```bash
git add tests/
git commit -m "test: add coverage for [feature]

- [List of test additions]"
```

### Step 4: Update Review Document
```markdown
**Status:** Complete
**Tests Added:** [List]
**Final Coverage:** YY%
**All Tests Passing:** Yes
```

## Quality Criteria

Tests must demonstrate:
- [ ] Core business logic validation
- [ ] Boundary/edge case coverage
- [ ] Error condition testing
- [ ] Meaningful assertions (not just "no exception")
- [ ] Test isolation (no shared state)
- [ ] Proper mocking of external services (Gmail, Telegram, Gemini)

## Related

- `code-review-skill` - For code quality review
