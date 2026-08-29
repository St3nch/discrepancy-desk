"""Governed entry point for the FND-PG01 proof task.

Run as::

    /home/chaz/projects/vedaops/discrepancy-desk/.venv/bin/python \\
        -m tools.postgres_foundation_proofs

with the repository root as the working directory and ``VEDAOPS_POSTGRES_URL``
in the environment. The task is flagless by contract.
"""

from __future__ import annotations

import sys

from .runner import main

if __name__ == "__main__":
    sys.exit(main())
