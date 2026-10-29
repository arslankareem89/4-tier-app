#!/usr/bin/env python3
import json
import math
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BASE_URL = os.getenv(
    "BASE_URL",
    "https://dii6w08edudfe.cloudfront.net",
).rstrip("/")
DURATION = int(os.getenv("LOAD_DURATION_SECONDS", "45"))
WORKERS = int(os.getenv("LOAD_WORKERS", "3"))
PAUSE_SECONDS = 0.5

results = []
lock = threading.Lock()


def request(method, path, token=None, payload=None):
    headers = {"Accept": "application/json"}
    body = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()

    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method,
    )

    started = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8", errors="replace")
            return response.status, content, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        return exc.code, content, time.perf_counter() - started
    except Exception as exc:
        return None, repr(exc), time.perf_counter() - started


def require_status(method, path, expected, token=None, payload=None):
    status, body, elapsed = request(method, path, token, payload)

    if status != expected:
        raise RuntimeError(
            f"{method} {path}: expected HTTP {expected}, "
            f"got {status}; response={body[:500]}"
        )

    return json.loads(body) if body else None


def percentile(values, percent):
    if not values:
        return float("nan")
    values = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(values)) - 1)
    return values[index]


def worker(token, deadline):
    while time.monotonic() < deadline:
        status, body, elapsed = request("GET", "/tasks", token=token)

        with lock:
            results.append({
                "status": status,
                "elapsed": elapsed,
                "error": body[:300] if status != 200 else None,
            })

        time.sleep(PAUSE_SECONDS)


def main():
    email = (
        "loadtest-" +
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") +
        "-" + secrets.token_hex(3) +
        "@example.test"
    )
    password = secrets.token_urlsafe(24)
    fixture_ids = []
    start = time.monotonic()

    print(f"Target: {BASE_URL}")
    print(f"Started UTC: {datetime.now(timezone.utc).isoformat()}")
    print(f"Workers: {WORKERS}; duration: {DURATION}s")
    print("Registering a dedicated test account...")

    auth = require_status(
        "POST",
        "/auth/register",
        201,
        payload={"email": email, "password": password},
    )
    token = auth["access_token"]

    try:
        # Create a few fixtures so the task-list response isn't always empty.
        for number in range(5):
            task = require_status(
                "POST",
                "/tasks",
                201,
                token=token,
                payload={
                    "title": f"Temporary load-test task {number + 1}",
                    "description": "Created by scripts/load_test.py",
                    "status": "PENDING",
                },
            )
            fixture_ids.append(task["id"])

        # Warm the endpoint/cache before measurement begins.
        require_status("GET", "/tasks", 200, token=token)

        print("Starting low-rate authenticated read load...")
        measured_start = time.monotonic()
        deadline = measured_start + DURATION

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [
                pool.submit(worker, token, deadline)
                for _ in range(WORKERS)
            ]
            for future in futures:
                future.result()

        measured_seconds = time.monotonic() - measured_start
        latencies = [item["elapsed"] * 1000 for item in results]
        statuses = Counter(str(item["status"]) for item in results)
        failures = [item for item in results if item["status"] != 200]

        print("\n=== Load test results ===")
        print(f"Requests: {len(results)}")
        print(f"Measured duration: {measured_seconds:.1f}s")
        print(
            f"Throughput: {len(results) / measured_seconds:.2f} requests/sec"
            if measured_seconds else "Throughput: unavailable"
        )
        print(f"HTTP status counts: {dict(statuses)}")

        if latencies:
            print(f"Latency p50: {percentile(latencies, 50):.1f} ms")
            print(f"Latency p95: {percentile(latencies, 95):.1f} ms")
            print(f"Latency p99: {percentile(latencies, 99):.1f} ms")
            print(f"Latency max: {max(latencies):.1f} ms")

        print(f"Failed requests: {len(failures)}")
        for failure in failures[:5]:
            print(
                f"  status={failure['status']} "
                f"elapsed={failure['elapsed']:.3f}s "
                f"detail={failure['error']}"
            )

        if failures:
            raise SystemExit("Load test detected request failures.")

    finally:
        print("\nRemoving temporary task fixtures...")
        for task_id in fixture_ids:
            status, body, _ = request(
                "DELETE",
                f"/tasks/{task_id}",
                token=token,
            )
            if status != 204:
                print(
                    f"WARNING: could not delete fixture {task_id}: "
                    f"status={status}, response={body[:200]}"
                )

        print(
            "The dedicated test account remains in the database: "
            f"{email}"
        )


if __name__ == "__main__":
    main()
