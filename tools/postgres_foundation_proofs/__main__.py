"""Governed entry point for the FND-PG01 proof task.

The external VedaOps task ``postgres-foundation-proofs`` is bound to exactly::

    uv run --offline --no-sync python -m tools.postgres_foundation_proofs

run with the repository root as the working directory and
``VEDAOPS_POSTGRES_URL`` in the environment.

``--offline`` forbids network access and ``--no-sync`` forbids runtime
environment synchronization, so the dependencies must already have been
provisioned before commissioning: the task neither resolves nor installs
anything while a proof runs, and there is no fallback that could. The task
itself takes no caller flags -- those two belong to ``uv`` and are environment
policy, not proof inputs.
"""

from __future__ import annotations

import sys

from .runner import main

if __name__ == "__main__":
    sys.exit(main())
