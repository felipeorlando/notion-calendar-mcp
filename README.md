# notion-calendar-mcp

Stdio [MCP](https://modelcontextprotocol.io) server for [Notion Calendar](https://calendar.notion.so). It talks to the private `calendar-api.notion.so` HTTP API (no public docs; reverse-engineered).

**This project is not affiliated with, endorsed by, or supported by Notion Labs, Inc.**

## Warning

Use this at your own risk.

- The Calendar HTTP API is **undocumented and reverse-engineered**. Endpoints, payloads, and auth can change or disappear without notice.
- Auth is a **browser session JWT** that typically lasts about **5 hours**. After that, calls return 401/403 until you refresh the token from a signed-in [calendar.notion.so](https://calendar.notion.so) session.
- Using an unofficial API **may violate [Notion’s Terms of Service](https://www.notion.com/terms)**. You are responsible for how you use this software.
- Never commit session tokens, `credentials.json`, or `.env` files. Never paste JWTs into chat, issues, or pull requests.

Licensed under the [MIT License](LICENSE).

## Requirements

- Python 3.10+
- A Notion Calendar account signed in at [calendar.notion.so](https://calendar.notion.so)

The MCP SDK is pinned to **`mcp==1.29.1`** so `Server.list_tools` remains available (later 2.x releases removed that registration API).

## Install

```bash
git clone https://github.com/felipeorlando/notion-calendar-mcp.git
cd notion-calendar-mcp
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Authentication

Provide a session JWT in **one** of these ways (file wins for `base_url` / extra headers; env can supply or override the token).

### 1. Credentials file (recommended)

```bash
mkdir -p ~/.config/notion-calendar
cp credentials.json.example ~/.config/notion-calendar/credentials.json
chmod 600 ~/.config/notion-calendar/credentials.json
```

Edit `~/.config/notion-calendar/credentials.json`:

```json
{
  "authorization": "Bearer YOUR_SESSION_JWT",
  "base_url": "https://calendar-api.notion.so",
  "headers": {
    "x-timezone": "America/New_York",
    "x-client-type": "web",
    "x-client-platform": "web",
    "x-client-os": "linux"
  }
}
```

`headers` is optional. Set `x-timezone` to your IANA timezone. See [credentials.json.example](credentials.json.example) for the full placeholder shape.

How to copy the JWT from the browser:

1. Sign in at [calendar.notion.so](https://calendar.notion.so).
2. Open DevTools → Network.
3. Trigger any calendar load and inspect a request to `calendar-api.notion.so`.
4. Copy the `Authorization` value (`Bearer …`).

### 2. Environment variables

```bash
export NOTION_CALENDAR_AUTHORIZATION="Bearer YOUR_SESSION_JWT"
# or a raw token / Bearer value:
# export NOTION_CALENDAR_TOKEN="YOUR_SESSION_JWT"
# optional:
# export NOTION_CALENDAR_BASE_URL="https://calendar-api.notion.so"
```

Do not put real tokens in shell history files you share, or in MCP config that lives inside a git repo.

On 401/403, refresh the JWT. `list_tools` works without a token; tool calls fail with a clear error if it is missing or expired.

## Run

```bash
.venv/bin/python server.py
```

The process speaks MCP over **stdio** (no HTTP port).

## Claude Desktop

Add the server to the Claude Desktop MCP config:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "notion-calendar": {
      "command": "/ABSOLUTE/PATH/TO/notion-calendar-mcp/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/notion-calendar-mcp/server.py"]
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/notion-calendar-mcp` with the real clone path. Prefer the credentials file above instead of embedding the JWT in this JSON.

Restart Claude Desktop after saving.

## Cursor

User config: `~/.cursor/mcp.json`. Project config: `.cursor/mcp.json` (do not commit tokens).

```json
{
  "mcpServers": {
    "notion-calendar": {
      "command": "/ABSOLUTE/PATH/TO/notion-calendar-mcp/.venv/bin/python",
      "args": ["server.py"],
      "cwd": "/ABSOLUTE/PATH/TO/notion-calendar-mcp"
    }
  }
}
```

Restart Cursor after saving.

An agent-plugin layout (`plugin.json`, `mcp.json`, `skills/notion-calendar/SKILL.md`) is also included for hosts that load that format.

## Tools

Call **`get_user` first**, then **`get_calendar_lists`** (or `get_calendars`) before event reads/writes. Prefer **title/summary** over raw ids when presenting results.

| Tool | Kind | Purpose |
| --- | --- | --- |
| `get_user` | read | Signed-in profile and linked calendar accounts |
| `get_calendar_lists` | read | Sidebar calendars / `calendarId` values |
| `get_calendars` | read | Calendar metadata (color, role, time zone) |
| `get_events` | read | Events in a time window (`timeMin`/`timeMax` ms epoch) |
| `get_event` | read | One event by id |
| `search_events` | read | Keyword search across accounts/calendars |
| `create_event` | write | Create an event (`start`/`end` only — not `startTime`/`endTime`) |
| `update_events` | write | Patch one or more events |
| `delete_events` | destructive | Delete events (confirm first) |
| `rsvp_event` | write | `accepted` / `declined` / `tentative` (not `needsAction`) |
| `get_calendar_free_busy` | read | Free/busy blocks before scheduling |
| `get_user_preferences` | read | Working hours and defaults (includes `etag`) |
| `update_user_preferences` | write | Update prefs (send `etag` from the read) |
| `get_people` | read | Paginated directory / attendees |
| `get_contacts` | read | Contact lookup (prefer `get_people` when paginating) |
| `get_colors` | read | Color palette |
| `get_synchronized_calendars` | read | Mirrored/synced calendars |
| `get_calendar_resources` | read | Room/resource calendars |
| `get_group_members` | read | Expand Google group invitees |
| `export_events` | read | Normalize events for export |
| `incremental_sync` | read | Advanced sync tokens; prefer `get_events` for normal reads |
| `get_holds` / `get_hold` | read | Scheduling Holds (booking pages) |
| `create_hold` / `update_hold` | write | Create or update a Hold |
| `delete_hold` | destructive | Delete a Hold |
| `get_notion_session_users` | read | Notion identities tied to this Calendar session |
| `update_calendars` | write | Rename/recolor calendars |
| `insert_calendar_list` | write | Subscribe to a calendar |
| `delete_calendar_list` | destructive | Unsubscribe from the sidebar list |

`create_event` `eventData` needs `id` (uuid hex is fine), `summary`, `start`, `end`, `status`, `provider`, `accountId`, `calendarId`, and `reminders: { "useDefault": true }`. Default `send_updates` to `none` unless you intend to email guests (`all` / `externalOnly`).

## Smoke test

With valid credentials:

```bash
.venv/bin/python smoke_test.py
```

Creates a 30-minute probe event two weeks out, then deletes it. It does not print tokens.

## Security

See [SECURITY.md](SECURITY.md). Short version: session JWT, ~5 hour TTL, never commit secrets, refresh on 401/403.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © Felipe Orlando
