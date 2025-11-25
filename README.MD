# !Clipit

A Python-based Twitch bot that automatically generates clips based on viewer votes in chat.

---

## Overview

!Clipit is a Python application that connects to your Twitch channel and monitors chat for clip commands. When viewers type `!clipit` in chat, the bot tracks votes and automatically generates a 30-second Twitch clip once the voting threshold is met.

### Key Features

- ✅ **Automatic Clip Generation**: Creates clips based on viewer voting
- ✅ **Flexible Voting System**: Configure minimum votes and time windows
- ✅ **Permission Controls**: Restrict voting by user type (Everyone, Subscribers, Moderators, Owner)
- ✅ **Discord Integration**: Optional webhook support for clip notifications
- ✅ **Comment Support**: Voters can add comments that are included with the clip
- ✅ **Cooldown Management**: Prevents spam with configurable cooldown periods
- ✅ **Automatic Authentication**: Handles Twitch OAuth flow seamlessly
- ✅ **Persistent Storage**: SQLite database for tokens and clip statistics

---

## How It Works

1. **Viewers vote**: Users type a clip command (e.g., `!clipit`) in your Twitch chat
2. **Comments are collected**: Voters can optionally add comments: `!clipit Nice play!`
3. **Votes are tracked**: The bot counts valid votes within the configured time window
4. **Clip is created**: Once the vote threshold is met, a 30-second clip is automatically generated
5. **Notifications sent**: The clip link and comments are posted to:
   - Twitch chat
   - Discord (if webhook configured)

### Example Usage

```
Viewer1: !clipit Amazing comeback!
Viewer2: !clipit
Viewer3: !clipit That was insane

Bot: Clip created! https://clips.twitch.tv/example | Comments: Amazing comeback! | That was insane
```

---

## Configuration

!Clipit is highly configurable to match your channel's needs.

### Commands

Define one or more commands that trigger clip votes:

```yaml
commands:
  - "!clipit"
  - "!clip"
  - "!makeclip"
```

### Vote Permissions

Control who can participate in voting. The permission system uses a hierarchy:

| Permission | Level | Description | Example |
|------------|-------|-------------|---------|
| **Everyone** | 1000 | Anyone in chat can vote | All viewers |
| **Subscribers** | 800 | Subscribers only | Can require minimum months: `SUB:3`, `SUB:6`, `SUB:12` |
| **Moderators** | 600 | Channel moderators only | Users with mod badge |
| **Owner** | 1 | Broadcaster only | Channel owner |

**Subscriber Duration Requirements:**

You can specify minimum subscription months:
- `SUB:3` - Requires 3+ months subscription
- `SUB:6` - Requires 6+ months subscription
- `SUB:12` - Requires 12+ months subscription

### Override Permissions

Allow specific user types to instantly generate clips without waiting for votes:

```yaml
permissions:
  override_permissions: "Moderators"  # Mods can instant-clip
```

When a user with override permissions votes, the clip is generated immediately regardless of the minimum votes setting.

### Voting Parameters

| Setting | Description | Default |
|---------|-------------|---------|
| **minimum_votes** | Minimum votes needed to trigger a clip | 3 |
| **command_window** | Time window (seconds) for votes to count | 30 |
| **command_cooldown** | Cooldown (seconds) after clip generation | 60 |

#### Command Window Example

With `command_window: 10` and `minimum_votes: 2`:

- User A votes at `0:00`
- User B votes at `0:11` (11 seconds later)
- ❌ Vote count resets to 1 because User B's vote exceeded the 10-second window
- A new vote must occur within 10 seconds

#### Command Cooldown Example

With `command_cooldown: 60`:

- Clip generated at `12:00`
- Bot ignores all votes until `12:01` (60 seconds later)
- Voting resumes at `12:01`

---

## Discord Integration

!Clipit can send embedded messages to Discord when clips are created.

### Webhook Setup

1. Configure a Discord webhook URL in `config.yaml`
2. The bot will post an embedded message containing:
   - 🎬 Clip URL
   - 💬 Combined comments from all voters
   - ⏰ Timestamp

### Message Format

When multiple users vote with comments:

```
!clipit Nice play dude
!clipit That was awesome
!clipit Best moment ever
```

The Discord message will include:
```
Nice play dude | That was awesome | Best moment ever
```

Comments are concatenated with the `|` separator.

---

## Requirements

### System Requirements

- Python 3.8 or higher
- Active internet connection
- Twitch account

### Broadcaster Requirements

- **Live Stream**: The broadcaster must be live for clips to be generated
- **API Access**: Valid Twitch API credentials (Client ID and Secret)
- **Authorization**: The bot requires the `clips:edit` scope

> **Note**: The bot can connect to the channel even when offline, but clips can only be created during live streams.

---

## Technical Details

### Authentication

!Clipit uses the **OAuth 2.0 Authorization Code Grant Flow** for secure Twitch authentication:

1. First run opens browser for user authorization
2. User logs in and authorizes the application
3. Bot receives and stores access & refresh tokens
4. Tokens are automatically refreshed when expired

### Database

Uses SQLite (`clipitbot.db`) to persist:

- **Access Tokens**: OAuth access tokens
- **Refresh Tokens**: For automatic token renewal
- **Clip Statistics**: History and metadata

### Third-Party Libraries

The bot leverages Python libraries for:

- **Twitch Authentication**: OAuth token generation, refresh, and management
- **Chat Monitoring**: Real-time IRC connection to Twitch chat
- **Clip Generation**: Twitch API integration for clip creation
- **User Type Detection**: Identifies user roles (subscriber, moderator, VIP, broadcaster)
- **Discord Webhooks**: Embedded message posting

---

## Twitch Capabilities

!Clipit interacts with Twitch through the following capabilities:

### Chat Monitoring
- Connects to Twitch IRC
- Monitors chat messages in real-time
- Detects configured clip commands
- Identifies user types and badges

### User Type Detection
- **Normal Users**: Regular viewers
- **Subscribers**: Active subscribers with duration tracking
- **Moderators**: Channel moderators
- **VIPs**: Very Important Persons
- **Broadcaster**: Channel owner

### Clip Management
- Generates 30-second clips via Twitch API
- Retrieves clip details (URL, ID, metadata)
- Posts clip links to chat
- Handles API rate limits and errors

---

## Installation & Setup

For detailed installation and configuration instructions, see the [SETUP.MD](SETUP.MD) file.

**Quick Start:**

1. Install dependencies: `pip install -r requirements.txt`
2. Create configuration: `copy config.yaml.example config.yaml`
3. Set Twitch credentials in `.env` file
4. Configure settings in `config.yaml`
5. Run the bot: `python main.py`

---

## Project Structure

```
clipit/
├── main.py              # Entry point
├── bot.py               # Main bot logic
├── auth.py              # Twitch authentication
├── voting.py            # Vote tracking system
├── clip.py              # Clip generation
├── discord.py           # Discord webhook integration
├── database.py          # SQLite database manager
├── permissions.py       # Permission system
├── logs.py              # Logging configuration
├── config.py            # Configuration loader
├── twitch_api.py        # Twitch API wrapper
├── config.yaml          # User configuration
├── requirements.txt     # Python dependencies
└── SETUP.MD             # Setup guide
```

---

## Contributing

Contributions are welcome! Feel free to:

- Report bugs
- Suggest features
- Submit pull requests

---

## License

This project is provided as-is for use with Twitch channels.

---

## Support

For setup instructions, troubleshooting, and configuration help, see [SETUP.MD](SETUP.MD).

---

**Happy Clipping!** 🎬
