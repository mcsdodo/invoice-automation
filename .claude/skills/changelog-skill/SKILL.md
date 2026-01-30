---
name: changelog-skill
description: Use when completing work to update CHANGELOG.md immediately
---

# Changelog Skill

## When to Use

Apply this skill IMMEDIATELY after completing:
- New features
- Bug fixes
- Behavior modifications
- Feature removals
- Security enhancements

**CRITICAL**: Update IMMEDIATELY when completing work, not batched later.

## Categories

| Category | Use For |
|----------|---------|
| Added | New features |
| Changed | Alterations to existing functionality |
| Fixed | Bug corrections |
| Removed | Deprecated or deleted features |

## Process

1. **Check today's section**: Look for `## [YYYY-MM-DD]` matching today's date
2. **Create if missing**: If today's section doesn't exist, add it at the top (after the header)
3. **Add entry**: Write under the appropriate category (Added/Changed/Fixed/Removed)
4. **Commit together**: Include changelog update in the same commit as code changes

## Format

Entries are grouped by date. No "Unreleased" section - just add to today's date:

```markdown
## [2026-01-09]

### Added
- New feature description

### Fixed
- Bug fix description
```

## Writing Standards

**DO:**
- Brief, single-line statements
- Focus on user-facing impact
- Start with action verbs (Add, Fix, Remove, Update)
- Be concise (1-2 sentences max)

**DON'T:**
- Include file paths or technical details
- Multi-line entries
- Internal refactoring details (unless user-visible impact)
- Duplicate entries

## Good Examples

```markdown
### Added
- Dark mode theme option in settings
- Export to CSV functionality for metrics

### Changed
- Loading speed improved for large datasets
- Dashboard layout reorganized for clarity

### Fixed
- PDF parsing correctly handles multi-page timesheets
- Gmail thread detection works with forwarded emails

### Removed
- Legacy API v1 endpoints
```

## Bad Examples

```markdown
### Added
- Added new file src/components/DarkMode.tsx with theme provider
  (Too technical, mentions file paths)

### Fixed
- Fixed the bug in line 42 of cosmos_service.py
  (Implementation detail, not user-facing)
```

## Commit Pattern

Include changelog in the same commit as the feature/fix:

```bash
git add src/feature.ts CHANGELOG.md
git commit -m "feat: add dark mode toggle"
```
