# !Clipit

Hosted Twitch clip voting for multiple broadcasters.

## What Changed

Clipit now runs as a FastAPI service instead of a single local bot tied to one `localhost` OAuth callback and one stored token row. Each broadcaster logs in with their own Twitch account, gets their own worker, creates clips using their own Twitch authorization, and now also receives an authenticated app session for managing their own channel settings.

## Current Scope

This implementation is backend-first.

- FastAPI handles Twitch OAuth login and callback.
- Twitch OAuth callback now also signs the user into the app with a secure cookie session.
- Each broadcaster gets their own installation record and their own runtime settings row.
- Each successful login starts or restarts one Twitch chat worker for that broadcaster.
- Commands, voting rules, permissions, deny list, and Discord webhook are stored per broadcaster.

## Quick Start

1. Install dependencies with `uv sync --group dev`.
2. Copy `config.yaml.example` to `config.yaml`.
3. Set `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `APP_BASE_URL`, and `SESSION_SECRET`.
4. Register your Twitch app callback URL as `{APP_BASE_URL}/auth/twitch/callback`.
5. Start the service with `python main.py`.
6. Visit `/auth/twitch/login` in a browser and authorize with the broadcaster account.
7. After login, use `/me` or the broadcaster endpoints from the same browser session.

## Environment Variables

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `APP_BASE_URL`
- `SESSION_SECRET`
- `HOST` (optional)
- `PORT` (optional)

## Routes

Public:
- `/`
- `/health`
- `/auth/twitch/login`
- `/auth/twitch/callback`
- `/auth/logout`

Authenticated with Twitch session cookie:
- `/me`
- `/broadcasters`
- `/broadcasters/{id}`
- `/broadcasters/{id}/settings`
- `/broadcasters/{id}/disable`
- `/broadcasters/{id}/enable`
- `DELETE /broadcasters/{id}`

Each signed-in user can only manage their own broadcaster record.

## Settings Model

Values from `config.yaml` are bootstrap defaults only. The first time a broadcaster connects, those defaults are copied into the database. After that, each broadcaster can have their own:

- commands
- vote thresholds and cooldowns
- permission rules
- deny list
- Discord webhook

## Notes

- Connected broadcasters and their settings are stored in `clipitbot.db`.
- Clip history is recorded per broadcaster.
- Session cookies are signed by `SESSION_SECRET`.
- Cookie `secure` mode is enabled automatically when `APP_BASE_URL` uses `https://`.

