#!/usr/bin/env python3
"""Pre-demo checks that require only a running backend."""

import json
import os
import sys
import urllib.request

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def get(path: str):
    request = urllib.request.Request(f"{BASE_URL}{path}", headers={"accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def main() -> int:
    checks = [
        ("/health", "backend health"),
        ("/", "API root"),
        ("/openapi.json", "OpenAPI route"),
    ]
    for path, label in checks:
        try:
            status, body = get(path)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {label}: {exc}")
            return 1
        if status != 200:
            print(f"FAIL {label}: HTTP {status}")
            return 1
        print(f"PASS {label}")
        if path == "/health":
            print(f"     database={body.get('database')} payment={body.get('payment_provider')}")

    print("Demo smoke checks passed. Open the frontend and follow docs/pitch.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())