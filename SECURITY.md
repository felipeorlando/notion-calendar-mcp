# Security Policy

## How authentication works

This server does **not** implement Notion OAuth. It reuses a **session JWT** from a signed-in [calendar.notion.so](https://calendar.notion.so) browser session and sends it as an `Authorization: Bearer …` header to `https://calendar-api.notion.so`.

Credentials are loaded in this order of sources (see `client.py`):

1. Environment: `NOTION_CALENDAR_AUTHORIZATION` or `NOTION_CALENDAR_TOKEN` (raw token or `Bearer …`).
2. A JSON file, first match among:
   - `~/.config/notion-calendar/credentials.json`
   - `~/.config/notion-calendar/notion-calendar.json`
   - optional Grok Bot box fallbacks under `/home/box/agent-data/connector-secrets/` and `/home/box/sand-data/connector-secrets/` (ignored on machines where those paths do not exist)
3. Optional `base_url` and extra `headers` from that JSON (timezone / client headers). The client never lets file headers override `Authorization`.

`list_tools` does not require a token. **Every tool call** that hits the API does. Missing or expired tokens return an error payload; tokens are never logged.

Treat the JWT like a session cookie: it can read and change the signed-in user’s calendars until it expires (typically **~5 hours**) or the session is revoked.

## Never commit credentials

Do not commit, paste, or screenshot:

- `credentials.json` / `notion-calendar.json`
- `.env` files
- `Authorization` headers, raw JWTs, or browser cookies
- MCP host config that inlines `NOTION_CALENDAR_AUTHORIZATION`

`.gitignore` already excludes `credentials.json`, `**/notion-calendar.json`, `.env`, and virtualenvs. Copy [credentials.json.example](credentials.json.example) and keep the real file at `~/.config/notion-calendar/credentials.json` with mode `600`.

If a token leaks, sign out of Notion Calendar sessions you control and rotate by signing in again and copying a fresh JWT. Assume a leaked JWT is fully privileged until it expires.

## JWT refresh

On **401** or **403**, the session JWT is probably expired or invalid:

1. Sign in at [calendar.notion.so](https://calendar.notion.so).
2. Copy a new `Authorization` value from DevTools → Network (a `calendar-api.notion.so` request).
3. Update `~/.config/notion-calendar/credentials.json` or the env var.
4. Retry. Do not invent or reuse a guessed token.

There is no refresh-token flow in this project.

## Scope and risk

The upstream API is undocumented. Using it may violate Notion’s terms. Bugs here can create, update, or delete real events. Prefer `send_updates: none` unless you intend to notify guests. Confirm before `delete_events`, `delete_hold`, or `delete_calendar_list`.

## Reporting a vulnerability

Please **do not** open a public issue for security reports, especially anything that includes session tokens, credentials, or full API error bodies.

**Placeholder — responsible disclosure**

Until a dedicated security contact is published:

- Use GitHub’s private vulnerability reporting on [this repository](https://github.com/felipeorlando/notion-calendar-mcp) if it is enabled, or
- Contact the maintainer (Felipe Orlando) via GitHub.

Include impact, a reproduction that does **not** contain live JWTs, and affected versions. We will try to acknowledge reports and remediate promptly.
