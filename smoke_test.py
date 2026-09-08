"""Live smoke test for Notion Calendar MCP over stdio.

Creates a short probe event then deletes it. Never prints tokens.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
SERVER = str(ROOT / "server.py")
TZ = ZoneInfo("America/Sao_Paulo")


def _text(result: Any) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        parts.append(getattr(block, "text", str(block)))
    return "\n".join(parts)


def _parse(result: Any) -> Any:
    text = _text(result)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _assert_ok(label: str, payload: Any) -> Any:
    if isinstance(payload, dict) and payload.get("error"):
        msg = payload.get("message") or payload
        # Never dump full body if it might contain secrets — message only.
        raise SystemExit(f"FAIL {label}: {msg}")
    print(f"OK {label}")
    return payload


def _pick_account_and_calendar(user: Any, lists: Any) -> tuple[str, str, str]:
    """Return (provider, account_id, calendar_id). Prefer primary google."""
    accounts: list[dict[str, Any]] = []
    if isinstance(user, dict):
        for key in ("accounts", "calendarAccounts"):
            val = user.get(key)
            if isinstance(val, list):
                accounts = [a for a in val if isinstance(a, dict)]
                break
        data = user.get("data")
        if not accounts and isinstance(data, dict) and isinstance(data.get("accounts"), list):
            accounts = [a for a in data["accounts"] if isinstance(a, dict)]
        if not accounts and isinstance(data, list):
            accounts = [a for a in data if isinstance(a, dict)]

    provider = "google"
    account_id = ""
    for a in accounts:
        pid = a.get("id") or a.get("accountId")
        prov = str(a.get("provider") or a.get("providerName") or "google")
        if pid and prov.lower() == "google":
            account_id = str(pid)
            provider = "google"
            break
    if not account_id and accounts:
        a = accounts[0]
        account_id = str(a.get("id") or a.get("accountId") or "")
        provider = str(a.get("provider") or a.get("providerName") or "google")

    nodes: list[Any]
    if isinstance(lists, list):
        nodes = lists
    elif isinstance(lists, dict):
        nodes = []
        for key in ("data", "results", "calendarLists"):
            if isinstance(lists.get(key), list):
                nodes = lists[key]
                break
        if not nodes:
            nodes = [lists]
    else:
        nodes = []

    cleaned: list[tuple[str, str, str, bool, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        aid = str(node.get("accountId") or account_id or "")
        cals = node.get("calendars") or node.get("items")
        if cals is None and isinstance(node.get("id"), str) and (
            "summary" in node or "primary" in node or "calendarId" in node
        ):
            cals = [node]
        if not isinstance(cals, list):
            continue
        for c in cals:
            if not isinstance(c, dict):
                continue
            cid = c.get("id") or c.get("calendarId")
            if not cid:
                continue
            prov = str(c.get("provider") or provider)
            summary = str(c.get("summary") or c.get("name") or cid)
            primary = bool(c.get("primary"))
            cleaned.append((prov, aid or account_id, str(cid), primary, summary))

    for prov, aid, cid, primary, summary in cleaned:
        if primary and aid:
            print(f"using calendar: {summary} (primary)")
            return prov, aid, cid
    for prov, aid, cid, _primary, summary in cleaned:
        if aid and cid:
            print(f"using calendar: {summary}")
            return prov, aid, cid

    if account_id:
        email = None
        if isinstance(user, dict):
            email = user.get("email") or user.get("primaryEmail")
            if not email and accounts:
                email = accounts[0].get("email") or accounts[0].get("accountId")
        if isinstance(email, str) and email:
            print(f"using calendar fallback: {email}")
            return provider, account_id, email

    raise SystemExit(
        "FAIL could not resolve provider/accountId/calendarId from get_user/"
        "get_calendar_lists — check account linkage"
    )


async def smoke() -> None:
    from mcp.server.lowlevel.server import Server

    s = Server("t")
    if not hasattr(s, "list_tools"):
        raise SystemExit("Server.list_tools missing — wrong mcp version")
    print("mcp Server.list_tools present")

    env = os.environ.copy()
    # Keep secrets via file; do not inject tokens into env for the test.
    params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER],
        env=env,
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(t.name for t in listed.tools)
            print(f"list_tools ({len(names)}): {', '.join(names)}")
            if "get_user" not in names or "create_event" not in names:
                raise SystemExit(f"FAIL unexpected tools: {names}")

            user = _assert_ok("get_user", _parse(await session.call_tool("get_user", {})))

            # Discover account id for lists query
            account_id = None
            provider = "google"
            if isinstance(user, dict):
                accs = user.get("accounts") or []
                if isinstance(user.get("data"), dict):
                    accs = user["data"].get("accounts") or accs
                chosen = None
                if isinstance(accs, list):
                    for a in accs:
                        if not isinstance(a, dict):
                            continue
                        prov = str(a.get("provider") or a.get("providerName") or "")
                        if a.get("primary") and prov.lower() == "google":
                            chosen = a
                            break
                    if chosen is None:
                        for a in accs:
                            if isinstance(a, dict) and a.get("primary"):
                                chosen = a
                                break
                    if chosen is None and accs and isinstance(accs[0], dict):
                        chosen = accs[0]
                if chosen:
                    account_id = chosen.get("id") or chosen.get("accountId")
                    provider = str(
                        chosen.get("provider") or chosen.get("providerName") or "google"
                    )
                if not account_id:
                    account_id = user.get("primaryAccountId") or user.get("accountId")

            if not account_id:
                # dump shallow keys only
                keys = list(user.keys()) if isinstance(user, dict) else type(user)
                raise SystemExit(f"FAIL get_user: no account id (keys={keys})")

            queries = json.dumps([{"provider": provider, "accountId": str(account_id)}])
            lists = _assert_ok(
                "get_calendar_lists",
                _parse(await session.call_tool("get_calendar_lists", {"queries_json": queries})),
            )

            provider, account_id, calendar_id = _pick_account_and_calendar(user, lists)

            now = datetime.now(TZ)
            start = (now + timedelta(days=14)).replace(hour=11, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=30)
            time_min = int((start - timedelta(hours=1)).timestamp() * 1000)
            time_max = int((end + timedelta(hours=1)).timestamp() * 1000)

            ev_queries = json.dumps(
                [
                    {
                        "provider": provider,
                        "accountId": account_id,
                        "calendarId": calendar_id,
                        "timeMin": time_min,
                        "timeMax": time_max,
                        "singleEvents": True,
                        "userTimeZone": "America/Sao_Paulo",
                        "limit": 10,
                    }
                ]
            )
            _assert_ok(
                "get_events",
                _parse(await session.call_tool("get_events", {"queries_json": ev_queries})),
            )

            probe_id = uuid.uuid4().hex
            summary = f"MCP smoke probe {probe_id[:8]}"
            start_json = json.dumps(
                {
                    "dateTime": start.isoformat(),
                    "timeZone": "America/Sao_Paulo",
                }
            )
            end_json = json.dumps(
                {
                    "dateTime": end.isoformat(),
                    "timeZone": "America/Sao_Paulo",
                }
            )
            created = _assert_ok(
                "create_event",
                _parse(
                    await session.call_tool(
                        "create_event",
                        {
                            "provider": provider,
                            "account_id": account_id,
                            "calendar_id": calendar_id,
                            "summary": summary,
                            "start_json": start_json,
                            "end_json": end_json,
                            "event_id": probe_id,
                            "send_updates": "none",
                        },
                    )
                ),
            )

            # Resolve actual event id from response if different
            event_id = probe_id
            if isinstance(created, dict):
                for key in ("event", "data", "mutation"):
                    node = created.get(key)
                    if isinstance(node, dict) and node.get("id"):
                        event_id = str(node["id"])
                        break
                if created.get("id"):
                    event_id = str(created["id"])

            del_mutations = json.dumps(
                [
                    {
                        "provider": provider,
                        "accountId": account_id,
                        "calendarId": calendar_id,
                        "eventId": event_id,
                        "sendUpdates": "none",
                    }
                ]
            )
            _assert_ok(
                "delete_events",
                _parse(
                    await session.call_tool(
                        "delete_events", {"mutations_json": del_mutations}
                    )
                ),
            )

            print(f"smoke ok — tools={len(names)} probe_summary={summary!r}")
            print("TOOL_COUNT", len(names))
            print("TOOL_NAMES", ",".join(names))


def main() -> None:
    asyncio.run(smoke())


if __name__ == "__main__":
    main()
