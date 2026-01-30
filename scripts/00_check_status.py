#!/usr/bin/env python
"""Check current workflow status."""

import json
from pathlib import Path

state_file = Path("data/state.json")

print("=" * 60)
print("WORKFLOW STATUS")
print("=" * 60)
print()

if not state_file.exists():
    print("State: No state file (service not started yet)")
else:
    state = json.loads(state_file.read_text())
    print(f"State: {state['state']}")
    print()

    if state.get("timesheet_info"):
        info = state["timesheet_info"]
        print(f"Timesheet: {info['total_hours']}h ({info['month']}/{info['year']})")
    else:
        print("Timesheet: Not detected")

    print(f"Approval:  {'Received' if state.get('approval_received') else 'Waiting'}")
    print(f"Invoice:   {'Received' if state.get('invoice_received') else 'Waiting'}")

    if state.get("manager_thread_id"):
        print(f"\nManager thread:    {state['manager_thread_id']}")
    if state.get("accountant_thread_id"):
        print(f"Accountant thread: {state['accountant_thread_id']}")

print()
