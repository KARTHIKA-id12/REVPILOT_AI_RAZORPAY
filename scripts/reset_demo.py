#!/usr/bin/env python3
"""Restore the demo merchant to its known deterministic seed state.
Thin wrapper around seed_demo.py's reset path — this is what the
'Reset Demo' button in Settings calls (once that endpoint exists)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_demo import main  # noqa: E402

if __name__ == "__main__":
    main(reset=True)
