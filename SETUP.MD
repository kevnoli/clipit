# !Clipit Setup Guide

This version of Clipit is designed to be hosted and shared across multiple broadcasters.

## 1. Create a Twitch Application

In the Twitch Developers Console:

1. Register an application.
2. Set the OAuth redirect URL to your deployed callback URL:
   - `https://your-domain.example.com/auth/twitch/callback`
3. Choose a suitable category such as `Chat Bot`.
4. Copy the client ID and client secret.

## 2. Install Dependencies

```bash
uv sync --group dev
```

## 3. Configure the Service

Copy the sample config:

```bash
cp config.yaml.example config.yaml
```

Set environment variables:

```env
TWITCH_CLIENT_ID=your_client_id_here
TWITCH_CLIENT_SECRET=your_client_secret_here
APP_BASE_URL=https://your-domain.example.com
SESSION_SECRET=replace-this-with-a-long-random-secret
```

Adjust `config.yaml` for your preferred bootstrap defaults. Those values are copied into a broadcaster-specific settings row the first time a broadcaster connects.

## 4. Run the Service

```bash
python main.py
```

Optional flags:

```bash
python main.py --host 0.0.0.0 --port 8000 --log-level INFO
```

## 5. Connect and Sign In as a Broadcaster

Open the hosted service in a browser and visit:

- `/auth/twitch/login`

After the broadcaster authorizes the app:

- their Twitch user ID and tokens are stored in SQLite
- their per-broadcaster settings row is created from the current defaults
- their channel worker starts on this instance
- clips are created using that broadcaster's Twitch authorization
- the browser receives a signed session cookie for managing that broadcaster

## Authenticated Management API

After login, the browser session can access:

- `GET /me` for the signed-in broadcaster's status
- `GET /broadcasters` for that broadcaster's record
- `GET /broadcasters/{id}` for that same broadcaster
- `PUT /broadcasters/{id}/settings` to update commands, voting, permissions, deny list, and webhook
- `POST /broadcasters/{id}/disable` to stop and disable that broadcaster
- `POST /broadcasters/{id}/enable` to enable and start that broadcaster again
- `DELETE /broadcasters/{id}` to disconnect and remove that broadcaster installation
- `GET /auth/logout` to clear the app session cookie

Each signed-in user can only manage their own broadcaster installation.

## Operational Notes

- One worker runs per enabled broadcaster.
- Settings are per broadcaster instead of shared.
- If a broadcaster token can no longer be refreshed, that broadcaster is disabled until they log in again.
- `clipitbot.db` stores broadcaster auth data, broadcaster settings, and clip history.
- Session cookies are signed using `SESSION_SECRET`.
- When `APP_BASE_URL` uses HTTPS, Clipit marks the auth cookie as secure automatically.

## Health Check

Use `/health` to verify the service is up and to see connected broadcaster counts.
