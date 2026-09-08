"""Thin HTTP client for Notion Calendar (calendar-api.notion.so).

Undocumented reverse-engineered API. Auth from env or a credentials file.
Never logs tokens or Authorization headers.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("notion-calendar-mcp")

DEFAULT_BASE_URL = "https://calendar-api.notion.so"
DEFAULT_ORIGIN = "https://calendar.notion.so"
DEFAULT_TIMEZONE = "America/Sao_Paulo"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

SECRET_PATHS = (
    Path.home() / ".config" / "notion-calendar" / "credentials.json",
    Path.home() / ".config" / "notion-calendar" / "notion-calendar.json",
    Path("/home/box/agent-data/connector-secrets/notion-calendar.json"),  # Grok Bot box
    Path("/home/box/sand-data/connector-secrets/notion-calendar.json"),
)
_SECRET_ROOTS = (
    Path("/home/box/agent-data/connector-secrets"),
    Path("/home/box/sand-data/connector-secrets"),
)

MISSING_TOKEN_MESSAGE = (
    "Notion Calendar session JWT is not set. Provide "
    "NOTION_CALENDAR_AUTHORIZATION or NOTION_CALENDAR_TOKEN (raw token or "
    "'Bearer …'), or ~/.config/notion-calendar/credentials.json with keys "
    "authorization, headers, base_url. Session JWTs expire ~5h — refresh "
    "from a signed-in calendar.notion.so browser session."
)

PROVIDERS = ("google", "notion", "icloud", "outlook")
SEND_UPDATES = ("all", "none", "externalOnly")
RSVP_STATUSES = ("accepted", "declined", "tentative")


class NotionCalendarAPIError(RuntimeError):
    def __init__(self, status: int, body: Any, message: str) -> None:
        super().__init__(f"Notion Calendar API {status}: {message}")
        self.status = status
        self.body = body
        self.message = message


class MissingTokenError(NotionCalendarAPIError):
    def __init__(self) -> None:
        super().__init__(0, None, MISSING_TOKEN_MESSAGE)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _json_loads(s: str) -> Any:
    return json.loads(s)


def _normalize_authorization(raw: str) -> str:
    tok = raw.strip()
    if not tok:
        return ""
    if tok.lower().startswith("bearer "):
        return "Bearer " + tok[7:].strip()
    return "Bearer " + tok


def _load_secret_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _iter_secret_files() -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for p in SECRET_PATHS:
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp not in seen:
            seen.add(rp)
            paths.append(p)
    for root in _SECRET_ROOTS:
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir():
                secret = child / "notion-calendar.json"
            elif child.name == "notion-calendar.json":
                secret = child
            else:
                continue
            try:
                rp = secret.resolve()
            except OSError:
                rp = secret
            if rp not in seen:
                seen.add(rp)
                paths.append(secret)
    return paths


def _creds() -> tuple[str, str, dict[str, str]]:
    """Return (authorization, base_url, extra_headers). Never log values."""
    auth_env = os.environ.get("NOTION_CALENDAR_AUTHORIZATION") or os.environ.get(
        "NOTION_CALENDAR_TOKEN"
    )
    base_url = os.environ.get("NOTION_CALENDAR_BASE_URL") or DEFAULT_BASE_URL
    headers: dict[str, str] = {}

    file_data: dict[str, Any] | None = None
    for path in _iter_secret_files():
        file_data = _load_secret_file(path)
        if file_data:
            break

    if file_data:
        if not auth_env:
            raw_auth = file_data.get("authorization")
            if isinstance(raw_auth, str) and raw_auth.strip():
                auth_env = raw_auth
        bu = file_data.get("base_url")
        if isinstance(bu, str) and bu.strip() and not os.environ.get(
            "NOTION_CALENDAR_BASE_URL"
        ):
            base_url = bu.strip().rstrip("/")
        fh = file_data.get("headers")
        if isinstance(fh, dict):
            for k, v in fh.items():
                if isinstance(k, str) and isinstance(v, str) and k.lower() != "authorization":
                    headers[k] = v

    if not auth_env or not str(auth_env).strip():
        raise MissingTokenError()

    authorization = _normalize_authorization(str(auth_env))
    base_url = base_url.rstrip("/")
    return authorization, base_url, headers


def _default_headers(authorization: str, extra: dict[str, str]) -> dict[str, str]:
    h = {
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": DEFAULT_ORIGIN,
        "Referer": DEFAULT_ORIGIN + "/",
        "User-Agent": USER_AGENT,
        "x-notion-authenticated": "true",
        "x-timezone": DEFAULT_TIMEZONE,
        "x-client-type": "web",
        "x-client-platform": "web",
        "x-client-os": "linux",
    }
    # Secrets may override timezone / client headers; never override Authorization.
    for k, v in extra.items():
        if k.lower() == "authorization":
            continue
        h[k] = v
    h["Authorization"] = authorization
    return h


def _parse_error_body(body_text: str) -> tuple[Any, str]:
    try:
        parsed = _json_loads(body_text)
    except Exception:
        parsed = body_text
    if isinstance(parsed, dict):
        message = (
            parsed.get("message")
            or parsed.get("error")
            or parsed.get("detail")
            or parsed.get("status")
            or "request failed"
        )
        if isinstance(message, dict):
            message = message.get("message") or message.get("code") or str(message)
        if not isinstance(message, str):
            message = str(message)
    else:
        message = str(parsed) if parsed else "request failed"
    return parsed, message or "request failed"


def _retry_after_seconds(headers: Any) -> int:
    raw = "5"
    try:
        raw = headers.get("Retry-After", "5") if headers is not None else "5"
    except Exception:
        raw = "5"
    try:
        wait = int(raw)
    except (TypeError, ValueError):
        wait = 5
    return min(max(wait, 0), 60)


def api_call(endpoint: str, body: dict[str, Any] | None = None) -> Any:
    """POST /v2/{endpoint}. endpoint like 'getUser' (no leading slash)."""
    ep = endpoint.strip().lstrip("/")
    if ep.startswith("v2/"):
        ep = ep[3:]
    authorization, base_url, extra = _creds()
    url = f"{base_url}/v2/{ep}"
    payload = body if body is not None else {}
    data = _json_dumps(payload).encode("utf-8")
    headers = _default_headers(authorization, extra)

    last_err: NotionCalendarAPIError | None = None
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {"ok": True}
                try:
                    return _json_loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            parsed, message = _parse_error_body(body_text)
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(_retry_after_seconds(e.headers))
                last_err = NotionCalendarAPIError(e.code, parsed, message)
                continue
            # Actionable auth hint without leaking token.
            if e.code in (401, 403):
                message = (
                    f"{message}. Session JWT may be expired (~5h). Refresh "
                    "authorization in ~/.config/notion-calendar/credentials.json "
                    "or set NOTION_CALENDAR_AUTHORIZATION."
                )
            raise NotionCalendarAPIError(e.code, parsed, message) from None
        except urllib.error.URLError as e:
            raise NotionCalendarAPIError(0, None, f"connection failed: {e.reason}") from None
    if last_err:
        raise last_err
    raise NotionCalendarAPIError(0, None, "request failed")


def new_event_id() -> str:
    return uuid.uuid4().hex


def build_event_data(
    *,
    summary: str,
    start: dict[str, Any],
    end: dict[str, Any],
    provider: str,
    account_id: str,
    calendar_id: str,
    event_id: str | None = None,
    status: str = "confirmed",
    description: str | None = None,
    location: str | None = None,
    attendees: list[dict[str, Any]] | None = None,
    reminders: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": event_id or new_event_id(),
        "summary": summary,
        "start": start,
        "end": end,
        "status": status,
        "provider": provider,
        "accountId": account_id,
        "calendarId": calendar_id,
        "reminders": reminders if reminders is not None else {"useDefault": True},
    }
    if description is not None:
        data["description"] = description
    if location is not None:
        data["location"] = location
    if attendees is not None:
        data["attendees"] = attendees
    if extra:
        for k, v in extra.items():
            if k in ("startTime", "endTime"):
                continue  # IH() omits these — use start/end only
            if k not in data:
                data[k] = v
    return data


# --- Endpoint wrappers -----------------------------------------------------


def get_user() -> Any:
    return api_call("getUser", {})


def get_holds() -> Any:
    return api_call("getHolds", {})


def get_notion_session_users() -> Any:
    return api_call("getNotionSessionUsers", {})


def get_calendar_lists(queries: list[dict[str, Any]]) -> Any:
    return api_call("getCalendarLists", {"queries": queries})


def get_calendars(queries: list[dict[str, Any]]) -> Any:
    return api_call("getCalendars", {"queries": queries})


def get_events(queries: list[dict[str, Any]]) -> Any:
    normalized = []
    for q in queries:
        item = dict(q)
        if "provider" not in item:
            item["provider"] = "google"
        normalized.append(item)
    return api_call("getEvents", {"queries": normalized})


def get_event(query: dict[str, Any]) -> Any:
    return api_call("getEvent", {"query": query})


def search_events(
    *,
    query: str,
    time_min: int,
    time_max: int,
    accounts: list[dict[str, Any]],
    user_time_zone: str | None = None,
    limit: int | None = None,
) -> Any:
    body: dict[str, Any] = {
        "query": query,
        "timeMin": time_min,
        "timeMax": time_max,
        "accounts": accounts,
    }
    if user_time_zone is not None:
        body["userTimeZone"] = user_time_zone
    if limit is not None:
        body["limit"] = limit
    return api_call("searchEvents", body)


def create_event(
    *,
    provider: str,
    account_id: str,
    calendar_id: str,
    event_data: dict[str, Any],
    send_updates: str | None = None,
    order: str | None = None,
) -> Any:
    mutation: dict[str, Any] = {
        "provider": provider,
        "accountId": account_id,
        "calendarId": calendar_id,
        "eventData": event_data,
    }
    if send_updates is not None:
        mutation["sendUpdates"] = send_updates
    if order is not None:
        mutation["order"] = order
    return api_call("createEvent", {"mutation": mutation})


def update_events(mutations: list[dict[str, Any]]) -> Any:
    return api_call("updateEvents", {"mutations": mutations})


def delete_events(mutations: list[dict[str, Any]]) -> Any:
    return api_call("deleteEvents", {"mutations": mutations})


def rsvp_event(
    *,
    account_id: str,
    calendar_id: str,
    event_id: str,
    response_status: str,
    comment: str | None = None,
    user_time_zone: str | None = None,
    counter_proposal: dict[str, Any] | None = None,
) -> Any:
    if response_status == "needsAction":
        raise NotionCalendarAPIError(
            0,
            None,
            "responseStatus must be accepted, declined, or tentative (not needsAction)",
        )
    body: dict[str, Any] = {
        "accountId": account_id,
        "calendarId": calendar_id,
        "eventId": event_id,
        "responseStatus": response_status,
    }
    if comment is not None:
        body["comment"] = comment
    if user_time_zone is not None:
        body["userTimeZone"] = user_time_zone
    if counter_proposal is not None:
        body["counterProposal"] = counter_proposal
    return api_call("rsvpEvent", body)


def get_calendar_free_busy(
    *,
    time_min: int,
    time_max: int,
    calendars: list[dict[str, Any]],
) -> Any:
    return api_call(
        "getCalendarFreeBusy",
        {"timeMin": time_min, "timeMax": time_max, "calendars": calendars},
    )


def get_user_preferences() -> Any:
    return api_call("getUserPreferences", {})


def update_user_preferences(user_preferences: dict[str, Any]) -> Any:
    return api_call("updateUserPreferences", {"userPreferences": user_preferences})


def get_contacts(body: dict[str, Any] | None = None) -> Any:
    return api_call("getContacts", body or {})


def get_people(
    *,
    account_ids: list[str] | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> Any:
    body: dict[str, Any] = {}
    if account_ids is not None:
        body["accountIds"] = account_ids
    if cursor is not None:
        body["cursor"] = cursor
    if limit is not None:
        body["limit"] = limit
    return api_call("getPeople", body)


def export_events(events: list[dict[str, Any]]) -> Any:
    return api_call("exportEvents", {"events": events})


def incremental_sync(
    *,
    sync_tokens: dict[str, Any] | list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    body: dict[str, Any] = {"syncTokens": sync_tokens if sync_tokens is not None else {}}
    if metadata is not None:
        body["metadata"] = metadata
    return api_call("incrementalSync", body)


def get_colors() -> Any:
    return api_call("getColors", {})


def get_synchronized_calendars() -> Any:
    return api_call("getSynchronizedCalendars", {})


def get_calendar_resources(accounts: list[str]) -> Any:
    return api_call("getCalendarResources", {"accounts": accounts})


def get_group_members(*, account_id: str, emails: list[str]) -> Any:
    return api_call("getGroupMembers", {"accountId": account_id, "emails": emails})


def get_hold(
    *,
    username: str | None = None,
    alias: str | None = None,
    hold_short_id: str | None = None,
    time_min: int | None = None,
    time_max: int | None = None,
) -> Any:
    body: dict[str, Any] = {}
    if username is not None:
        body["username"] = username
    if alias is not None:
        body["alias"] = alias
    if hold_short_id is not None:
        body["holdShortId"] = hold_short_id
    if time_min is not None:
        body["timeMin"] = time_min
    if time_max is not None:
        body["timeMax"] = time_max
    return api_call("getHold", body)


def create_hold(hold: dict[str, Any]) -> Any:
    return api_call("createHold", hold)


def update_hold(hold: dict[str, Any]) -> Any:
    return api_call("updateHold", hold)


def delete_hold(hold_id: str) -> Any:
    return api_call("deleteHold", {"holdId": hold_id})


def update_calendars(mutations: list[dict[str, Any]]) -> Any:
    return api_call("updateCalendars", {"mutations": mutations})


def insert_calendar_list(mutation: dict[str, Any]) -> Any:
    return api_call("insertCalendarList", {"mutation": mutation})


def delete_calendar_list(mutation: dict[str, Any]) -> Any:
    return api_call("deleteCalendarList", {"mutation": mutation})
