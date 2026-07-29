"""Measure authenticated local product-query latency and report nearest-rank P95.

The script is intended to run inside the Compose network against either the
frontend same-origin proxy or the backend directly. It never prints a password
or bearer token.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def _percentile_nearest_rank(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", default="operator_content")
    parser.add_argument(
        "--password-env", default="M4_OPERATOR_PASSWORD", help="environment variable name"
    )
    parser.add_argument("--samples", type=int, default=80)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-p95-ms", type=float, default=1000.0)
    parser.add_argument("--environment-label", default="docker-compose-local")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("--samples must be at least 20 for a useful P95")
    if args.warmup < 0:
        parser.error("--warmup must not be negative")
    password = os.getenv(args.password_env, "")
    if not password:
        parser.error(f"required password environment variable is not set: {args.password_env}")

    base_url = args.base_url.rstrip("/")
    with httpx.Client(
        base_url=base_url,
        timeout=args.timeout_seconds,
        trust_env=False,
    ) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": args.username, "password": password},
        )
        if login.status_code != 200:
            raise SystemExit(
                f"login failed: HTTP {login.status_code} (response body intentionally omitted)"
            )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        def query() -> float:
            started = time.perf_counter_ns()
            response = client.get(
                "/api/products",
                headers=headers,
                params={"page": 1, "page_size": 20},
            )
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if response.status_code != 200:
                raise SystemExit(
                    "product query failed: "
                    f"HTTP {response.status_code} (response body intentionally omitted)"
                )
            payload = response.json()
            if not isinstance(payload.get("items"), list):
                raise SystemExit("product query response did not contain an items list")
            return elapsed_ms

        for _ in range(args.warmup):
            query()
        samples = [query() for _ in range(args.samples)]

    p95_ms = _percentile_nearest_rank(samples, 0.95)
    report = {
        "metric": "authenticated_product_list_latency",
        "route": "/api/products?page=1&page_size=20",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "environment_label": args.environment_label,
        "base_url": base_url,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "sample_count": len(samples),
        "warmup_count": args.warmup,
        "min_ms": round(min(samples), 3),
        "median_ms": round(_percentile_nearest_rank(samples, 0.50), 3),
        "p95_ms": round(p95_ms, 3),
        "max_ms": round(max(samples), 3),
        "threshold_ms": args.max_p95_ms,
        "passed": p95_ms <= args.max_p95_ms,
        "method": "sequential requests; nearest-rank percentile; client wall-clock",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
