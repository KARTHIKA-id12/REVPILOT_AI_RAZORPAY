#!/usr/bin/env python3
"""Purges any merchant other than TechNest from the database.

Why this exists: test fixtures that exercise the Action Pipeline commit
real data mid-test (agent actions must be durable), so their cleanup
depends on fixture teardown actually running. An interrupted test process
(killed mid-run, a timeout, Ctrl-C) skips teardown entirely — no fixture
design can prevent that, since Python doesn't run teardown code after a
process is killed. This script is the maintenance answer: run it whenever
`select count(*) from merchants` looks higher than expected.

Usage:
    python scripts/purge_test_merchants.py           # purge everything except TechNest
    python scripts/purge_test_merchants.py --dry-run # just list what would be purged
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.identity import Merchant  # noqa: E402
from app.services.merchant_cleanup import reset_merchant  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep", default="TechNest", help="Merchant name to preserve (default: TechNest)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        orphans = db.query(Merchant.id, Merchant.name).filter(Merchant.name != args.keep).all()
        if not orphans:
            print(f"No orphaned merchants found. Only '{args.keep}' (or nothing) present.")
            return 0

        print(f"Found {len(orphans)} merchant(s) other than '{args.keep}':")
        for merchant_id, name in orphans:
            print(f"  {name} ({merchant_id})")

        if args.dry_run:
            print("\n--dry-run: nothing deleted.")
            return 0

        for merchant_id, name in orphans:
            reset_merchant(db, merchant_id)
        print(f"\nPurged {len(orphans)} merchant(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
