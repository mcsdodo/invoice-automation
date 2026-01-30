# Task Planning Conventions

This folder contains planning documents for complex features. All plans, designs, and task tracking go here - NOT in `.claude/plans/`, `docs/`, or other directories.

## Folder Structure

```
_tasks/
├── {NN}-{descriptive-name}/          # Numbered folders (check existing for next NN)
│   ├── 01-task.md                    # Task description, requirements
│   ├── 02-plan.md                    # Implementation plan
│   ├── 02-design.md                  # Or design doc (alternative to plan)
│   └── 03-*.md                       # Additional docs as needed
├── _done/                            # Completed tasks (moved here, keep numbers)
├── _TECH_DEBT/                       # Tech debt tracking (see _TECH_DEBT/CLAUDE.md)
│   ├── {NN}-{issue-name}.md          # Individual tech debt items
│   └── CLAUDE.md                     # Tech debt guidelines
└── CLAUDE.md                         # This file
```

## File Naming

- **Folders**: `{NN}-{descriptive-name}` - Check existing folders for next number
- **Files**: `{NN}-{name}.md` format (e.g., `01-task.md`, `02-plan.md`)

**CRITICAL - Finding next folder number:**

```
# Check BOTH locations (items move to _done when completed)
Search(pattern: "[0-9][0-9]-*", path: "_tasks")
Search(pattern: "[0-9][0-9]-*", path: "_tasks/_done")
```

Extract highest folder number from BOTH results, add 1, zero-pad to 2 digits.

**Do NOT:**
- Use `ls _tasks/` or `Glob _tasks/*` (misses subdirectories)
- Guess folder numbers without checking
- Forget to check `_tasks/_done/` (completed tasks retain their numbers)

| File | Purpose |
|------|---------|
| `01-task.md` | Task description, user story, requirements |
| `02-plan.md` | Step-by-step implementation plan |
| `02-design.md` | Architecture decisions, diagrams |
| `03+` | Additional docs (status, notes, etc.) |

## File Content

Always include metadata at top:

```markdown
**Date:** 2026-01-30
**Subject:** Feature description
**Status:** Planning | In Progress | Complete
```

## When to Create Task Folders

**Create for:**
- Multi-file implementations
- Multi-session work
- Complex features requiring design
- Architectural changes

**Skip for:**
- Simple bug fixes
- Single-file changes
- Quick enhancements

## Task Lifecycle

1. **Planning**: Create `{NN}-{name}/01-task.md` with requirements
2. **Design**: Add `02-plan.md` or `02-design.md`
3. **Implementation**: Reference plan during coding
4. **Completion**: Move to `_done/` for historical reference

## Tech Debt Integration

Tasks often originate from tech debt items. When implementing such tasks:

1. **Link to tech debt**: In `01-task.md`, reference the source tech debt file
   ```markdown
   **Source:** `_TECH_DEBT/03-schema-divergence.md`
   ```

2. **Update tech debt on completion**: After implementing, update the tech debt file:
   - Change **Status** to "Fixed"
   - Add entry to **Decision Log** with commit reference

3. **Cross-reference**: Link from tech debt to the task folder in the **Related** section

See [`_TECH_DEBT/CLAUDE.md`](_TECH_DEBT/CLAUDE.md) for tech debt documentation guidelines.

## Task Files vs Code Documentation

- **Task files** (plans, status, designs) → Stay in `_tasks/`
- **Code documentation** (READMEs, API docs) → Stay with code (locality principle)
- **Never mix** task planning with permanent code docs

## Before Starting Implementation

**IMPORTANT:** When using superpowers skills (brainstorming, writing-plans, etc.), commit task/design/plan files BEFORE implementation begins:

1. **Complete planning phase**: Finish brainstorming, get user approval on design
2. **Write plan**: Create implementation plan, get user review
3. **Ask about branching**: "Should I create a feature branch for this work?"
4. **Commit planning docs**:
   ```bash
   git add _tasks/{NN}-{name}/
   git commit -m "docs: add task and plan for {feature-name}"
   ```
5. **Then start implementation**: Use subagent-driven-development or executing-plans

This preserves design rationale in version control before code changes begin.
