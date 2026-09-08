#!/usr/bin/env python3
"""Notion Calendar MCP server (stdio).

Reverse-engineered calendar-api.notion.so tools. list_tools works without a
token; tool calls return a clear error if the session JWT is missing/expired.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from client import (
    MissingTokenError,
    NotionCalendarAPIError,
    build_event_data,
    create_event as api_create_event,
    create_hold as api_create_hold,
    delete_calendar_list as api_delete_calendar_list,
    delete_events as api_delete_events,
    delete_hold as api_delete_hold,
    export_events as api_export_events,
    get_calendar_free_busy as api_get_calendar_free_busy,
    get_calendar_lists as api_get_calendar_lists,
    get_calendar_resources as api_get_calendar_resources,
    get_calendars as api_get_calendars,
    get_colors as api_get_colors,
    get_contacts as api_get_contacts,
    get_event as api_get_event,
    get_events as api_get_events,
    get_group_members as api_get_group_members,
    get_hold as api_get_hold,
    get_holds as api_get_holds,
    get_notion_session_users as api_get_notion_session_users,
    get_people as api_get_people,
    get_synchronized_calendars as api_get_synchronized_calendars,
    get_user as api_get_user,
    get_user_preferences as api_get_user_preferences,
    incremental_sync as api_incremental_sync,
    insert_calendar_list as api_insert_calendar_list,
    rsvp_event as api_rsvp_event,
    search_events as api_search_events,
    update_calendars as api_update_calendars,
    update_events as api_update_events,
    update_hold as api_update_hold,
    update_user_preferences as api_update_user_preferences,
)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="%(name)s %(levelname)s: %(message)s",
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)

mcp = FastMCP(
    "notion-calendar",
    instructions=(
        "Notion Calendar (calendar.notion.so) private API tooling. "
        "Call get_user first, then get_calendar_lists / get_calendars before "
        "events. Title/summary first — never lead with ids. Session JWT expires "
        "~5h. Secrets never logged."
    ),
    log_level="WARNING",
)


def _dump(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, NotionCalendarAPIError):
        out: dict[str, Any] = {
            "error": True,
            "status": exc.status,
            "message": exc.message,
        }
        if exc.body is not None:
            out["body"] = exc.body
        return _dump(out)
    return _dump({"error": True, "status": 0, "message": str(exc)})


def _call(fn, **kwargs: Any) -> str:
    try:
        return _dump(fn(**kwargs))
    except (NotionCalendarAPIError, MissingTokenError) as e:
        return _error_text(e)
    except Exception as e:
        return _dump({"error": True, "status": 0, "message": str(e)})


def _parse_json_arg(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise NotionCalendarAPIError(
                0, None, f"{name} must be valid JSON ({e.msg})"
            ) from None
    raise NotionCalendarAPIError(0, None, f"{name} must be a JSON object/array or string")


# --- Core tools ------------------------------------------------------------


@mcp.tool(
    name="get_user",
    description=(
        "Call first to learn who is signed in and which calendar accounts exist. "
        "POST /v2/getUser {}. Returns profile + linked accounts (title/email first). "
        "Use before get_calendar_lists / get_events. Session JWT required."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_user() -> str:
    return _call(api_get_user)


@mcp.tool(
    name="get_holds",
    description=(
        "List scheduling Holds (booking pages) for the signed-in user. "
        "POST /v2/getHolds {}. Call when you need hold aliases/ids before "
        "get_hold / create_hold. Name/alias first, never lead with id."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_holds() -> str:
    return _call(api_get_holds)


@mcp.tool(
    name="get_notion_session_users",
    description=(
        "List Notion session users tied to this Calendar session. "
        "POST /v2/getNotionSessionUsers {}. Call when bridging Calendar ↔ Notion "
        "identity. Display name/email first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_notion_session_users() -> str:
    return _call(api_get_notion_session_users)


@mcp.tool(
    name="get_calendar_lists",
    description=(
        "List calendars for one or more accounts (sidebar calendar list). "
        "Call after get_user when you need calendarId values. "
        "POST /v2/getCalendarLists {queries:[{provider, accountId}]}. "
        "queries_json: JSON array. Calendar summary/name first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_calendar_lists(queries_json: str) -> str:
    def run() -> Any:
        queries = _parse_json_arg(queries_json, "queries_json")
        if not isinstance(queries, list) or not queries:
            raise NotionCalendarAPIError(
                0, None, "queries_json must be a non-empty JSON array of {provider, accountId}"
            )
        return api_get_calendar_lists(queries)

    return _call(run)


@mcp.tool(
    name="get_calendars",
    description=(
        "Fetch calendar metadata (colors, access role, timeZone) for accounts. "
        "POST /v2/getCalendars {queries:[{provider, accountId, query?}]}. "
        "queries_json: JSON array. Prefer get_calendar_lists for the sidebar list. "
        "Summary first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_calendars(queries_json: str) -> str:
    def run() -> Any:
        queries = _parse_json_arg(queries_json, "queries_json")
        if not isinstance(queries, list) or not queries:
            raise NotionCalendarAPIError(
                0, None, "queries_json must be a non-empty JSON array"
            )
        return api_get_calendars(queries)

    return _call(run)


@mcp.tool(
    name="get_events",
    description=(
        "Fetch events in a time window for specific calendars. "
        "Call after you know provider/accountId/calendarId. "
        "POST /v2/getEvents {queries:[...]}. timeMin/timeMax are ms epoch. "
        "queries_json: JSON array; provider defaults to google. "
        "Return order: summary/title first, never lead with event id."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_events(queries_json: str) -> str:
    def run() -> Any:
        queries = _parse_json_arg(queries_json, "queries_json")
        if not isinstance(queries, list) or not queries:
            raise NotionCalendarAPIError(
                0, None, "queries_json must be a non-empty JSON array"
            )
        return api_get_events(queries)

    return _call(run)


@mcp.tool(
    name="get_event",
    description=(
        "Fetch one event by id. Call when you already have "
        "provider/accountId/calendarId/eventId. "
        "POST /v2/getEvent {query:{...}}. Optional userTimeZone. "
        "Summary first in any presentation."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_event(
    provider: str,
    account_id: str,
    calendar_id: str,
    event_id: str,
    user_time_zone: str | None = None,
) -> str:
    def run() -> Any:
        query: dict[str, Any] = {
            "provider": provider,
            "accountId": account_id,
            "calendarId": calendar_id,
            "eventId": event_id,
        }
        if user_time_zone:
            query["userTimeZone"] = user_time_zone
        return api_get_event(query)

    return _call(run)


@mcp.tool(
    name="search_events",
    description=(
        "Full-text search events across accounts/calendars in a time range. "
        "Call when the user asks to find meetings by keyword. "
        "POST /v2/searchEvents. time_min/time_max are ms epoch. "
        "accounts_json: [{accountId, calendarIds:[]}]. Title/summary first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def search_events(
    query: str,
    time_min: int,
    time_max: int,
    accounts_json: str,
    user_time_zone: str | None = None,
    limit: int | None = None,
) -> str:
    def run() -> Any:
        accounts = _parse_json_arg(accounts_json, "accounts_json")
        if not isinstance(accounts, list) or not accounts:
            raise NotionCalendarAPIError(
                0, None, "accounts_json must be a non-empty JSON array"
            )
        return api_search_events(
            query=query,
            time_min=time_min,
            time_max=time_max,
            accounts=accounts,
            user_time_zone=user_time_zone,
            limit=limit,
        )

    return _call(run)


@mcp.tool(
    name="create_event",
    description=(
        "Create a calendar event. Call after confirming calendar + time with the user. "
        "POST /v2/createEvent. eventData must include id (uuid hex ok), summary, "
        "start, end, status, provider, accountId, calendarId, reminders:{useDefault:true}. "
        "Use start/end only (never startTime/endTime). "
        "start_json/end_json: {dateTime,timeZone} or {date}. "
        "send_updates: all|none|externalOnly. Summary first."
    ),
    annotations=WRITE,
    structured_output=False,
)
def create_event(
    provider: str,
    account_id: str,
    calendar_id: str,
    summary: str,
    start_json: str,
    end_json: str,
    status: str = "confirmed",
    event_id: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees_json: str | None = None,
    send_updates: str | None = "none",
    reminders_json: str | None = None,
    extra_event_json: str | None = None,
) -> str:
    def run() -> Any:
        start = _parse_json_arg(start_json, "start_json")
        end = _parse_json_arg(end_json, "end_json")
        if not isinstance(start, dict) or not isinstance(end, dict):
            raise NotionCalendarAPIError(
                0, None, "start_json and end_json must be JSON objects"
            )
        attendees = _parse_json_arg(attendees_json, "attendees_json")
        reminders = _parse_json_arg(reminders_json, "reminders_json")
        extra = _parse_json_arg(extra_event_json, "extra_event_json")
        event_data = build_event_data(
            summary=summary,
            start=start,
            end=end,
            provider=provider,
            account_id=account_id,
            calendar_id=calendar_id,
            event_id=event_id,
            status=status,
            description=description,
            location=location,
            attendees=attendees if isinstance(attendees, list) else None,
            reminders=reminders if isinstance(reminders, dict) else None,
            extra=extra if isinstance(extra, dict) else None,
        )
        return api_create_event(
            provider=provider,
            account_id=account_id,
            calendar_id=calendar_id,
            event_data=event_data,
            send_updates=send_updates,
        )

    return _call(run)


@mcp.tool(
    name="update_events",
    description=(
        "Update one or more existing events. Call when changing time/title/details. "
        "POST /v2/updateEvents {mutations:[{provider, accountId, eventId, calendarId, "
        "eventData, userTimeZone?, sendUpdates?}]}. mutations_json: JSON array. "
        "Patch eventData with fields to change; keep summary visible. "
        "sendUpdates: all|none|externalOnly."
    ),
    annotations=WRITE,
    structured_output=False,
)
def update_events(mutations_json: str) -> str:
    def run() -> Any:
        mutations = _parse_json_arg(mutations_json, "mutations_json")
        if not isinstance(mutations, list) or not mutations:
            raise NotionCalendarAPIError(
                0, None, "mutations_json must be a non-empty JSON array"
            )
        return api_update_events(mutations)

    return _call(run)


@mcp.tool(
    name="delete_events",
    description=(
        "Delete one or more events. Call only after confirming which event(s). "
        "POST /v2/deleteEvents {mutations:[{provider, accountId, calendarId, eventId, "
        "sendUpdates?}]}. mutations_json: JSON array. Destructive. "
        "sendUpdates: all|none|externalOnly."
    ),
    annotations=DESTRUCTIVE,
    structured_output=False,
)
def delete_events(mutations_json: str) -> str:
    def run() -> Any:
        mutations = _parse_json_arg(mutations_json, "mutations_json")
        if not isinstance(mutations, list) or not mutations:
            raise NotionCalendarAPIError(
                0, None, "mutations_json must be a non-empty JSON array"
            )
        return api_delete_events(mutations)

    return _call(run)


@mcp.tool(
    name="rsvp_event",
    description=(
        "RSVP to an event invite (accepted|declined|tentative). "
        "Call when the user wants to respond to an invitation. "
        "POST /v2/rsvpEvent. response_status must NOT be needsAction. "
        "Optional comment and counter_proposal_json {start,end}."
    ),
    annotations=WRITE,
    structured_output=False,
)
def rsvp_event(
    account_id: str,
    calendar_id: str,
    event_id: str,
    response_status: str,
    comment: str | None = None,
    user_time_zone: str | None = None,
    counter_proposal_json: str | None = None,
) -> str:
    def run() -> Any:
        cp = _parse_json_arg(counter_proposal_json, "counter_proposal_json")
        return api_rsvp_event(
            account_id=account_id,
            calendar_id=calendar_id,
            event_id=event_id,
            response_status=response_status,
            comment=comment,
            user_time_zone=user_time_zone,
            counter_proposal=cp if isinstance(cp, dict) else None,
        )

    return _call(run)


@mcp.tool(
    name="get_calendar_free_busy",
    description=(
        "Get free/busy blocks for calendars in a time range. "
        "Call when checking availability before scheduling. "
        "POST /v2/getCalendarFreeBusy. time_min/time_max ms epoch. "
        "calendars_json: [{accountId, calendarId}]."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_calendar_free_busy(
    time_min: int,
    time_max: int,
    calendars_json: str,
) -> str:
    def run() -> Any:
        calendars = _parse_json_arg(calendars_json, "calendars_json")
        if not isinstance(calendars, list) or not calendars:
            raise NotionCalendarAPIError(
                0, None, "calendars_json must be a non-empty JSON array"
            )
        return api_get_calendar_free_busy(
            time_min=time_min, time_max=time_max, calendars=calendars
        )

    return _call(run)


@mcp.tool(
    name="get_user_preferences",
    description=(
        "Read Calendar user preferences (working hours, defaults, etag). "
        "Call before update_user_preferences (etag required for force check). "
        "POST /v2/getUserPreferences {}."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_user_preferences() -> str:
    return _call(api_get_user_preferences)


@mcp.tool(
    name="update_user_preferences",
    description=(
        "Update Calendar user preferences. Call only with an etag from "
        "get_user_preferences (412 if stale). "
        "POST /v2/updateUserPreferences {userPreferences:{...}}. "
        "user_preferences_json: full/partial prefs object including etag."
    ),
    annotations=WRITE,
    structured_output=False,
)
def update_user_preferences(user_preferences_json: str) -> str:
    def run() -> Any:
        prefs = _parse_json_arg(user_preferences_json, "user_preferences_json")
        if not isinstance(prefs, dict):
            raise NotionCalendarAPIError(
                0, None, "user_preferences_json must be a JSON object (include etag)"
            )
        return api_update_user_preferences(prefs)

    return _call(run)


@mcp.tool(
    name="get_contacts",
    description=(
        "Fetch contacts via POST /v2/getContacts (Spectral-proven; may be alias). "
        "Call for quick contact lookup; prefer get_people for paginated directory. "
        "Optional body_json object. Display name/email first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_contacts(body_json: str | None = None) -> str:
    def run() -> Any:
        body = _parse_json_arg(body_json, "body_json")
        if body is not None and not isinstance(body, dict):
            raise NotionCalendarAPIError(0, None, "body_json must be a JSON object")
        return api_get_contacts(body if isinstance(body, dict) else None)

    return _call(run)


@mcp.tool(
    name="get_people",
    description=(
        "List people/contacts from connected accounts (paginated). "
        "POST /v2/getPeople {accountIds?, cursor?, limit?}. "
        "Call when searching attendees by directory. Display name/email first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_people(
    account_ids_json: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> str:
    def run() -> Any:
        ids = _parse_json_arg(account_ids_json, "account_ids_json")
        if ids is not None and not isinstance(ids, list):
            raise NotionCalendarAPIError(
                0, None, "account_ids_json must be a JSON array of strings"
            )
        return api_get_people(
            account_ids=ids if isinstance(ids, list) else None,
            cursor=cursor,
            limit=limit,
        )

    return _call(run)


@mcp.tool(
    name="export_events",
    description=(
        "Normalize/export partial event objects (ICS-oriented shape). "
        "POST /v2/exportEvents {events:[...]}. events_json: array of partial "
        "events with id/start/end/summary/…. Call when packaging events for export."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def export_events(events_json: str) -> str:
    def run() -> Any:
        events = _parse_json_arg(events_json, "events_json")
        if not isinstance(events, list):
            raise NotionCalendarAPIError(0, None, "events_json must be a JSON array")
        return api_export_events(events)

    return _call(run)


@mcp.tool(
    name="incremental_sync",
    description=(
        "Drive incremental calendar sync with sync tokens. "
        "POST /v2/incrementalSync {syncTokens, metadata:{caller}}. "
        "Often 400 without valid tokens from a prior sync — expose for advanced "
        "use; prefer get_events for normal reads. sync_tokens_json + optional "
        "metadata_json."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def incremental_sync(
    sync_tokens_json: str | None = None,
    metadata_json: str | None = None,
) -> str:
    def run() -> Any:
        tokens = _parse_json_arg(sync_tokens_json, "sync_tokens_json")
        meta = _parse_json_arg(metadata_json, "metadata_json")
        if tokens is not None and not isinstance(tokens, (dict, list)):
            raise NotionCalendarAPIError(
                0, None, "sync_tokens_json must be a JSON object or array"
            )
        if meta is not None and not isinstance(meta, dict):
            raise NotionCalendarAPIError(0, None, "metadata_json must be a JSON object")
        return api_incremental_sync(
            sync_tokens=tokens if tokens is not None else {},
            metadata=meta if isinstance(meta, dict) else None,
        )

    return _call(run)


# --- Thin passthrough tools ------------------------------------------------


@mcp.tool(
    name="get_colors",
    description=(
        "Fetch calendar color palette. Call when rendering/assigning calendar colors. "
        "POST /v2/getColors {}."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_colors() -> str:
    return _call(api_get_colors)


@mcp.tool(
    name="get_synchronized_calendars",
    description=(
        "List synchronized/mirrored calendars. Call when inspecting Calendar sync "
        "links between accounts. POST /v2/getSynchronizedCalendars {}. Name first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_synchronized_calendars() -> str:
    return _call(api_get_synchronized_calendars)


@mcp.tool(
    name="get_calendar_resources",
    description=(
        "List room/resource calendars for accounts. "
        "POST /v2/getCalendarResources {accounts:[accountId,...]}. "
        "accounts_json: JSON string array. Call when booking rooms."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_calendar_resources(accounts_json: str) -> str:
    def run() -> Any:
        accounts = _parse_json_arg(accounts_json, "accounts_json")
        if not isinstance(accounts, list) or not accounts:
            raise NotionCalendarAPIError(
                0, None, "accounts_json must be a non-empty JSON array of accountId strings"
            )
        return api_get_calendar_resources([str(a) for a in accounts])

    return _call(run)


@mcp.tool(
    name="get_group_members",
    description=(
        "Resolve Google group members for attendee expansion. "
        "POST /v2/getGroupMembers {accountId, emails:[...]}. "
        "emails_json: JSON array. Call when an invitee is a group address."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_group_members(account_id: str, emails_json: str) -> str:
    def run() -> Any:
        emails = _parse_json_arg(emails_json, "emails_json")
        if not isinstance(emails, list) or not emails:
            raise NotionCalendarAPIError(
                0, None, "emails_json must be a non-empty JSON array of emails"
            )
        return api_get_group_members(account_id=account_id, emails=[str(e) for e in emails])

    return _call(run)


@mcp.tool(
    name="get_hold",
    description=(
        "Fetch one Hold (scheduling page) by username, alias, or holdShortId. "
        "POST /v2/getHold. Optional time_min/time_max (ms). "
        "Call after get_holds when inspecting availability slots. Alias/name first."
    ),
    annotations=READ_ONLY,
    structured_output=False,
)
def get_hold(
    username: str | None = None,
    alias: str | None = None,
    hold_short_id: str | None = None,
    time_min: int | None = None,
    time_max: int | None = None,
) -> str:
    return _call(
        api_get_hold,
        username=username,
        alias=alias,
        hold_short_id=hold_short_id,
        time_min=time_min,
        time_max=time_max,
    )


@mcp.tool(
    name="create_hold",
    description=(
        "Create a Hold scheduling page. POST /v2/createHold. "
        "hold_json must include id, timeRanges, userPrimaryTimeZone (and usual "
        "Hold fields). Call when the user wants a new booking link. Alias/title first."
    ),
    annotations=WRITE,
    structured_output=False,
)
def create_hold(hold_json: str) -> str:
    def run() -> Any:
        hold = _parse_json_arg(hold_json, "hold_json")
        if not isinstance(hold, dict):
            raise NotionCalendarAPIError(0, None, "hold_json must be a JSON object")
        return api_create_hold(hold)

    return _call(run)


@mcp.tool(
    name="update_hold",
    description=(
        "Update an existing Hold. POST /v2/updateHold. "
        "hold_json should include id plus fields to change (alias, timeRanges, …). "
        "Call after get_hold / get_holds."
    ),
    annotations=WRITE,
    structured_output=False,
)
def update_hold(hold_json: str) -> str:
    def run() -> Any:
        hold = _parse_json_arg(hold_json, "hold_json")
        if not isinstance(hold, dict):
            raise NotionCalendarAPIError(0, None, "hold_json must be a JSON object")
        return api_update_hold(hold)

    return _call(run)


@mcp.tool(
    name="delete_hold",
    description=(
        "Delete a Hold by holdId. POST /v2/deleteHold {holdId}. "
        "Destructive — confirm with the user first."
    ),
    annotations=DESTRUCTIVE,
    structured_output=False,
)
def delete_hold(hold_id: str) -> str:
    return _call(api_delete_hold, hold_id=hold_id)


@mcp.tool(
    name="update_calendars",
    description=(
        "Patch calendar metadata (summary, color, selected, …). "
        "POST /v2/updateCalendars {mutations:[{provider, accountId, calendarId, "
        "calendarData, colorRgbFormat?, variant?}]}. mutations_json: JSON array. "
        "Call when renaming/recoloring calendars. Summary first."
    ),
    annotations=WRITE,
    structured_output=False,
)
def update_calendars(mutations_json: str) -> str:
    def run() -> Any:
        mutations = _parse_json_arg(mutations_json, "mutations_json")
        if not isinstance(mutations, list) or not mutations:
            raise NotionCalendarAPIError(
                0, None, "mutations_json must be a non-empty JSON array"
            )
        return api_update_calendars(mutations)

    return _call(run)


@mcp.tool(
    name="insert_calendar_list",
    description=(
        "Subscribe/add a calendar to the user's calendar list. "
        "POST /v2/insertCalendarList {mutation:{provider, accountId, calendarId, "
        "calendarData?}}. mutation_json: JSON object. Call when adding a shared calendar."
    ),
    annotations=WRITE,
    structured_output=False,
)
def insert_calendar_list(mutation_json: str) -> str:
    def run() -> Any:
        mutation = _parse_json_arg(mutation_json, "mutation_json")
        if not isinstance(mutation, dict):
            raise NotionCalendarAPIError(0, None, "mutation_json must be a JSON object")
        return api_insert_calendar_list(mutation)

    return _call(run)


@mcp.tool(
    name="delete_calendar_list",
    description=(
        "Unsubscribe/remove a calendar from the calendar list. "
        "POST /v2/deleteCalendarList {mutation:{provider, accountId, calendarId}}. "
        "mutation_json: JSON object. Destructive for the sidebar entry (not the calendar itself)."
    ),
    annotations=DESTRUCTIVE,
    structured_output=False,
)
def delete_calendar_list(mutation_json: str) -> str:
    def run() -> Any:
        mutation = _parse_json_arg(mutation_json, "mutation_json")
        if not isinstance(mutation, dict):
            raise NotionCalendarAPIError(0, None, "mutation_json must be a JSON object")
        return api_delete_calendar_list(mutation)

    return _call(run)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
