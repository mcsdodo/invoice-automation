# Task: Telegram Persistent Debug Keyboard

## Summary

Add a persistent reply keyboard to the Telegram bot for remote debugging actions. Move functionality from the `scripts/` debug scripts into the bot so all debugging can be done remotely via Telegram buttons.

## Motivation

Currently, debugging/testing the workflow requires SSH access or running local scripts. A persistent Telegram keyboard would allow:
- Remote status checks without SSH
- Triggering test scenarios from mobile
- Faster iteration during development
- Production debugging without direct server access

## Requirements

1. **Persistent Reply Keyboard** with buttons:
   - `📊 Status` - Show current workflow state
   - `📄 Drop Test PDF` - Create and drop a test timesheet
   - `✅ Send Approval` - Send approval email to manager thread
   - `💰 Send Invoice` - Send invoice email with PDF attachment
   - `🔄 Reset` - Reset workflow to IDLE state

2. **Contextual Button Visibility** (optional enhancement):
   - Show only relevant buttons based on current state
   - Or always show all, with error messages for invalid actions

3. **Security**:
   - Only respond to configured `TELEGRAM_CHAT_ID`
   - Existing authorization model is sufficient

## Out of Scope

- Mini Apps / web dashboard
- Inline keyboard alternative (keep current inline for approvals)
- New config options

## Success Criteria

- [ ] All 5 debug actions work via Telegram buttons
- [ ] Keyboard persists across messages
- [ ] Works in Docker container
- [ ] No changes to existing approval workflow
