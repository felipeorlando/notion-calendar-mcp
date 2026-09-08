---
name: notion-calendar
description: >-
  WHEN to use Notion Calendar MCP tooling (calendar.notion.so). Structured
  list/search/create/update/delete/RSVP. Title first; get_user then calendar
  lists before events. Session JWT expires ~5h. Use this skill for Calendar
  API tooling, not casual chat about the schedule.
---

# Notion Calendar tooling

Use the **notion-calendar** MCP when you need structured Calendar API access (list calendars, fetch a window of events, create/update/delete, RSVP, free/busy, holds).

## WHEN to call

| Need | Tool |
| --- | --- |
| Who am I / which accounts? | `get_user` **first** |
| Sidebar calendars / `calendarId` | `get_calendar_lists` then `get_calendars` |
| Events in a range | `get_events` (ms `timeMin`/`timeMax`) |
| One event | `get_event` |
| Keyword search | `search_events` |
| Create / change / remove | `create_event` / `update_events` / `delete_events` |
| Respond to invite | `rsvp_event` (`accepted`/`declined`/`tentative`) |
| Availability | `get_calendar_free_busy` |
| Contacts / people | `get_people` (prefer) or `get_contacts` |
| Scheduling Holds | `get_holds` → `get_hold` / `create_hold` / `update_hold` / `delete_hold` |
| Prefs | `get_user_preferences` before `update_user_preferences` (etag) |

## How

1. **Auth**: `~/.config/notion-calendar/credentials.json` or `NOTION_CALENDAR_AUTHORIZATION` / `NOTION_CALENDAR_TOKEN`. JWT lasts ~**5 hours** — on 401/403 ask to refresh the session secret; do not invent tokens.
2. **Order**: `get_user` → pick `provider` + `accountId` → `get_calendar_lists` → then events.
3. **Voice**: **title/summary first**, never lead with ids. JSON tool results may include ids — when speaking to the user, lead with the human label.
4. **create_event**: `eventData` needs `id` (uuid hex ok), `summary`, `start`, `end`, `status`, `provider`, `accountId`, `calendarId`, `reminders:{useDefault:true}`. Use `start`/`end` only (no `startTime`/`endTime`). Default `send_updates` to `none` unless the user wants guest emails.
5. **Deletes / RSVP / hold deletes**: confirm intent first.
6. **incremental_sync**: often 400 without valid sync tokens — prefer `get_events` for normal reads.

## Never

- Log or paste Authorization / JWT values
- Skip `get_user` when account/calendar ids are unknown
- Call auth/login/telemetry endpoints (login URL, Splunk, device identify, …)
