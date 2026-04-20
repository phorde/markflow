"""Application entrypoint for MarkFlow."""

from __future__ import annotations

import sys

from markflow.cli import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
