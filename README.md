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
uv run uvicorn discrepancy_desk.web:app --host 127.0.0.1 --port 8000
```

Runtime databases, backups, credentials, and raw evidence are excluded from Git.

## Current M03 service boundary

The minimal operator service loop supports governed account setup, work capture, bounded source records, evidence registration, exact revision approval, manual-ready designation, matched or mismatched publication recording, metric observations, and control-room reads.

The production dashboard and all autonomous platform actions remain out of scope.
