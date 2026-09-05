#!/usr/bin/env python3
"""Run the full deterministic analytics pipeline (metrics, RFM, affinity,
opportunity detection/scoring) against a merchant and print a summary.

Usage:
    python scripts/run_analytics.py                  # runs against TechNest
    python scripts/run_analytics.py --merchant NAME
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.identity import Merchant  # noqa: E402
from app.opportunities.service import run_full_analytics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merchant", default="TechNest")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        merchant = db.query(Merchant).filter(Merchant.name == args.merchant).one_or_none()
        if not merchant:
            print(f"No merchant named '{args.merchant}' found. Run scripts/seed_demo.py first.")
            return 1

        print(f"Running analytics for {merchant.name} ({merchant.id})...\n")
        summary = run_full_analytics(db, merchant.id)

        print("--- Revenue metrics ---")
        print(json.dumps(summary["metrics"], indent=2))

        print("\n--- Top 5 products ---")
        for p in summary["top_products"]:
            print(f"  {p['name']:35s} revenue=₹{p['revenue']:>12,.2f}  units={p['units']:<5}  orders={p['orders']}")

        print("\n--- Customer segments (RFM) ---")
        for s in summary["segments"]:
            print(f"  {s['label']:22s} customers={s['customer_count']:<5}  revenue=₹{s['total_revenue']:>14,.2f}  avg_freq={s['average_frequency']}")

        print(f"\n--- Opportunities: {summary['opportunities_detected']} detected ---")
        print(json.dumps(summary["opportunities_by_type"], indent=2))

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
