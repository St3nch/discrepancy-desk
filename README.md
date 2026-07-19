# The Discrepancy Desk

Local, human-approved research, drafting, review, manual-publication, and metrics support.

## Hard boundary

AI drafts. Human clears. Database remembers. Metrics judge.

No autonomous posting, replies, likes, follows, reposts, or direct messages.

## Development

```powershell
uv sync --extra dev
uv run alembic upgrade head
uv run pytest
```

Runtime databases, backups, credentials, and raw evidence are excluded from Git.
