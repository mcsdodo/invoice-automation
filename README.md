## Telegram Bot Setup

1. Create a bot via @BotFather
2. Send a message to the bot (or add to a group)
3. Get chat ID: `https://api.telegram.org/<YOUR_BOT_TOKEN>/getUpdates`

**For group chats**: Disable privacy mode via BotFather:
- `/setprivacy` → Select your bot → Disable

This allows the bot to receive all messages (needed for the "Edit Hours" flow).

## Google Gmail API Setup

1. Create a project in Google Cloud Console
2. Enable Gmail API for that project
3. Create OAuth 2.0 credentials (Desktop app type)
4. OAuth consent screen → Test users → Add your Gmail account
5. Download credentials.json to `config/` folder
