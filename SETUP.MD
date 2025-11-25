# !Clipit Setup Guide

This guide will walk you through setting up and configuring !Clipit for your Twitch channel.

---

## Prerequisites

Before you begin, ensure you have the following:

- Python 3.8 or higher
- A Twitch account
- Twitch Application credentials (Client ID and Client Secret)
- (Optional) Discord webhook URL

---

## Step 1: Create a Twitch Application

Visit the [Twitch Developers Console](https://dev.twitch.tv/console) to register your application.

1. Click **"Register Your Application"**
2. Fill in the application details:
   - **Name**: `Clipit` (or any name you prefer)
   - **OAuth Redirect URLs**: `http://localhost:3000`
   - **Category**: `Chat Bot`
3. Click **"Create"**
4. Copy your **Client ID**
5. Click **"New Secret"** to generate and copy your **Client Secret**

> **Note**: Keep these credentials secure. You'll need them in Step 3.

For more information, see the [Twitch Authentication Documentation](https://dev.twitch.tv/docs/authentication/register-app).

---

## Step 2: Install Dependencies

### Setup Instructions

> **Note**: For all platforms (Windows, Linux, Mac), you can create a virtual environment to isolate dependencies. This ensures that this project's Python packages do not interfere with other Python projects or system-wide installations. This is optional and not part of these setup instructions.

1. Clone this repo:
   ```bash
   git clone https://github.com/dimins/clipit.git
   ```
   
2. Install the required packages:
   ```bash
   cd clipit
   pip install -r requirements.txt
   ```

## Step 3: Configure the Bot

### 3.1 Create Configuration Files

1. Copy the example configuration file:

   **Windows:**
   ```bash
   copy config.yaml.example config.yaml
   ```

   **Linux/Mac:**
   ```bash
   cp config.yaml.example config.yaml
   ```

2. Create an `.env` file in the project directory with your Twitch credentials:

   ```env
   TWITCH_CLIENT_ID=your_client_id_here
   TWITCH_CLIENT_SECRET=your_client_secret_here
   ```

### 3.2 Edit Configuration

Open `config.yaml` and configure the following:

#### Twitch Settings
- `twitch.broadcaster_channel`: Your Twitch channel name (lowercase)

#### Discord Settings (Optional)
- `discord.webhook_url`: Your Discord webhook URL (leave empty if not using Discord)

#### Voting Settings
- `voting.minimum_votes`: Minimum votes needed to trigger a clip (default: `2`)
- `voting.command_window`: Time window in seconds for votes to count (default: `15`)
- `voting.command_cooldown`: Cooldown period in seconds after a clip is generated (default: `30`)

#### Permission Settings
- `permissions.vote_permissions`: Who can vote
  - Options: `Everyone`, `Subscribers`, `Moderators`, `Owner`
- `permissions.override_permissions`: Who can instantly trigger a clip without voting
  - Options: `Moderators`, `Owner`

---

## Step 4: (Optional) Set Up Discord Webhook

If you want clip notifications sent to Discord:

1. Open your Discord server settings
2. Navigate to **Integrations** → **Webhooks**
3. Click **"New Webhook"**
4. Customize the webhook name and select the target channel
5. Click **"Copy Webhook URL"**
6. Paste the URL into `config.yaml` under `discord.webhook_url`

---

## Step 5: Run the Bot

Start the bot with:

```bash
python main.py
```

### First Run Authentication

On the first run, the bot will:

1. Open your default browser for Twitch authentication
2. Ask you to authorize the application
3. Redirect you to `http://localhost:3000`
4. Save your authentication tokens for future use

> **Tip**: Keep the authorization page open until the bot confirms successful authentication.

---

## Configuration Options

### Commands

Configure multiple commands that trigger voting:

```yaml
commands:
  - "!clipit"
  - "!clip"
```

### Permissions

#### Vote Permissions

Control who can participate in voting:

- `Everyone`: Anyone in chat can vote
- `Subscribers`: Only subscribers can vote
- `Moderators`: Only moderators can vote
- `Owner`: Only the broadcaster can vote

#### Subscriber Requirements

When using `Subscribers` as the vote permission, you can specify minimum subscription months:

```yaml
permissions:
  vote_permissions: "Subscribers"
  subscriber_months: "SUB:3"  # Requires 3+ months subscription
```

#### Override Permissions

Users with override permissions can instantly trigger a clip without waiting for votes:

```yaml
permissions:
  override_permissions: "Moderators"  # Moderators can instant-clip
```

---

## Troubleshooting

### Authentication Issues

**Problem**: Bot fails to authenticate or token errors occur.

**Solutions**:
- Verify your OAuth Redirect URL in Twitch Console is exactly `http://localhost:3000`
- Ensure port `3000` is not in use by another application
- Check that `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in `.env` are correct
- Delete `clipitbot.db` and re-authenticate from scratch

### Bot Not Responding

**Problem**: Bot connects but doesn't respond to commands.

**Solutions**:
- Verify the broadcaster channel name in `config.yaml` is correct (lowercase, no `#` symbol)
- Ensure the bot has proper permissions in your Twitch channel
- Check `app.log` for error messages
- Confirm you're using the correct command (e.g., `!clipit`)

### Clips Not Generating

**Problem**: Votes are counted but clips aren't created.

**Solutions**:
- Ensure the broadcaster is **live** when the command is used (clips can only be made during live streams)
- Verify you authorized the `clips:edit` scope during authentication
- Check that your Twitch API credentials are valid
- Review `app.log` for API error messages

### Discord Notifications Not Working

**Problem**: Clips are created but not posted to Discord.

**Solutions**:
- Verify the webhook URL in `config.yaml` is correct
- Test the webhook URL manually using a tool like curl or Postman
- Ensure the Discord channel hasn't been deleted
- Check `app.log` for Discord API errors

---

## Logs

The bot creates the log file `app.log` with detailed information about:

- Bot startup and initialization
- Authentication status
- Command execution
- Vote tracking
- Clip generation
- Error messages and stack traces

Use this file to diagnose issues and monitor bot activity.

---

## Database

The bot uses a SQLite database (`clipitbot.db`) to store:

- **Authentication tokens**: OAuth tokens for Twitch API access
- **Clip statistics**: History of generated clips and voting data

### Resetting the Database

To start fresh (e.g., to re-authenticate):

**Windows:**
```bash
del clipitbot.db
```

**Linux/Mac:**
```bash
rm clipitbot.db
```

> **Warning**: This will delete all stored authentication tokens and clip history. You will need to re-authenticate with Twitch.

---

## Need Help?

If you encounter issues not covered in this guide:

1. Check `app.log` for detailed error messages
2. Review the [Twitch API Documentation](https://dev.twitch.tv/docs/api/)
3. Verify your configuration matches the examples in `config.yaml.example`

---

## Summary

You should now have !Clipit successfully connected to your Twitch channel! The bot will:

- ✅ Monitor chat for clip commands
- ✅ Track votes within the configured time window
- ✅ Generate clips when vote threshold is met
- ✅ Send notifications to Discord (if configured)
- ✅ Handle permissions based on your configuration

Happy Clipping! 🎬
