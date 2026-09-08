# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-08

### Added

- Initial stdio MCP server for Notion Calendar (`calendar-api.notion.so`).
- Session JWT auth from `~/.config/notion-calendar/credentials.json` or environment variables.
- Calendar tools: user/accounts, lists, events, search, create/update/delete, RSVP, free/busy, preferences, contacts/people, holds, colors, resources, and related passthroughs.
- `smoke_test.py` (create-then-delete probe event).
- Agent skill at `skills/notion-calendar/SKILL.md`.

[Unreleased]: https://github.com/felipeorlando/notion-calendar-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/felipeorlando/notion-calendar-mcp/releases/tag/v0.1.0
