# Clipit

Personal Twitch clip bot/service for self-hosting.

This repo is public, but it is built for my own use: one hosted instance, broadcaster sign-in through Twitch, and per-channel clip settings stored in the app.

## Stack

- FastAPI backend
- Vue frontend
- SQLModel + Alembic
- Twitch OAuth per broadcaster

## Local/dev flow

```bash
uv sync --group dev
cp .env.example .env
uv run alembic upgrade head
```

Backend:

```bash
uv run fastapi dev
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Production-style frontend build:

```bash
cd frontend
pnpm build
```

That writes the site into `app/static/`, which FastAPI serves at `/`. The API lives under `/api`.

## Required env

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `APP_BASE_URL`
- `SESSION_SECRET`
- `SECRET_ENCRYPTION_KEY` (required, separate from `SESSION_SECRET`)

The Twitch redirect URL should be:

`{APP_BASE_URL}{TWITCH_REDIRECT_PATH}`

Default callback:

`/api/auth/twitch/callback`

## Notes

- Each broadcaster logs in with their own Twitch account.
- Clip creation happens with that broadcaster's own authorization.
- Commands, thresholds, permissions, denylist, and Discord webhook are per broadcaster.
- FastAPI docs/OpenAPI are disabled.
