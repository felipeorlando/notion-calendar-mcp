# Contributing

Thanks for helping improve notion-calendar-mcp.

## Issues

- Search existing issues before opening a new one.
- Include Python version, OS, and the MCP host (Claude Desktop, Cursor, stdio, …).
- Paste **redacted** tool names and error `message` fields only. Never paste `Authorization` headers, JWTs, `credentials.json`, or full API bodies that might contain tokens.

## Pull requests

- Keep diffs focused. Match existing style (stdlib HTTP client, no extra deps beyond `mcp==1.29.1`).
- Do **not** bump the `mcp` pin unless you have verified `Server.list_tools` still works.
- Do not add telemetry, login, or auth-bypass helpers.
- Update [CHANGELOG.md](CHANGELOG.md) under **Unreleased** when the change is user-visible.

## No secrets in PRs

Never commit:

- `credentials.json`, `notion-calendar.json`, `.env`
- real JWTs, cookies, or `Bearer` values (placeholders only, as in `credentials.json.example`)
- host MCP configs that inline tokens

If you accidentally commit a secret, rotate the Notion Calendar session immediately and say so in the PR (without pasting the token).

## Smoke test

Syntax-only check (no live API):

```bash
python3 -m py_compile client.py server.py smoke_test.py
```

Live smoke test (needs valid credentials; creates then deletes a 30-minute probe event two weeks out):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python smoke_test.py
```

The smoke test must not print tokens.

## License

By contributing you agree that your changes are licensed under the [MIT License](LICENSE).
