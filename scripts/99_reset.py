#!/usr/bin/env python
"""Reset the workflow state for a fresh test run."""

import shutil
from pathlib import Path

print("=" * 60)
print("RESETTING WORKFLOW")
print("=" * 60)
print()

# Remove state file
state_file = Path("data/state.json")
if state_file.exists():
    state_file.unlink()
    print("Deleted: data/state.json")

# Clear incoming folder
incoming = Path("data/incoming")
if incoming.exists():
    for f in incoming.glob("*.pdf"):
        f.unlink()
        print(f"Deleted: {f}")

# Clear temp folder
temp = Path("data/temp")
if temp.exists():
    for f in temp.glob("*"):
        if f.is_file():
            f.unlink()
            print(f"Deleted: {f}")

print()
print("Workflow reset. Ready for fresh test run.")
print()
