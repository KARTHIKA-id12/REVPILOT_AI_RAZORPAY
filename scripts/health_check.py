#!/usr/bin/env python3
"""Quick end-to-end sanity check: is the backend up, and in what mode?
Run after `docker compose up` (or local uvicorn) before a demo."""

import json
import os
import sys
import urllib.request

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def check(path: str) -> dict:
    with urllib.request.urlopen(f"{BACKEND_URL}{path}", timeout=5) as resp:
        return json.loads(resp.read())


def main() -> int:
    try:
        health = check("/health")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Backend unreachable at {BACKEND_URL}: {exc}")
        return 1

    print(f"status:           {health['status']}")
    print(f"database:         {health['database']}")
    print(f"ai:               {health['ai']}")
    print(f"payment_provider: {health['payment_provider']}")

    if health["database"] != "healthy":
        print("⚠️  Database not healthy — run migrations / start postgres (Phase 2+).")
        return 1

    print("✅ Backend healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
