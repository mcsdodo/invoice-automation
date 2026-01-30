#!/bin/bash
# Post-commit hook: changelog reminder + temp file cleanup

input=$(cat)
[ -z "$input" ] && exit 0

# Clean up tmpclaude-* temp files (always, on any bash command)
find . -name "tmpclaude-*" -delete 2>/dev/null

# Only show reminder for git commit commands
if ! echo "$input" | grep -q '"command"[^}]*git commit'; then
    exit 0
fi

# Skip if this is a changelog commit
if echo "$input" | grep -qi '"command"[^}]*changelog'; then
    exit 0
fi

# Exit code 2 with stderr = blocking message shown to Claude
echo "REMINDER: Run /changelog to update CHANGELOG.md" >&2
exit 2
