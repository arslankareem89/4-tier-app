import json
import os
import statistics
import time
import urllib.error
import urllib.request
import uuid

from sqlalchemy import select

from main import SessionLocal, User, task_cache


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
WARM_REQUESTS = int(os.getenv("WARM_REQUESTS", "100"))


def request_json(path, method="GET", payload=None, token=None):
    headers = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        content = response.read()
        return response.status, json.loads(content) if content else None


def main():
    email = f"cache-benchmark-{uuid.uuid4().hex}@example.test"
    password = f"Bench-{uuid.uuid4().hex}-Pass"
    user_id = None
    task_id = None
    warm_samples_ms = []
    try:
        _, token_response = request_json(
            "/auth/register",
            method="POST",
            payload={"email": email, "password": password},
        )
        token = token_response["access_token"]
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.email == email))
        _, task = request_json(
            "/tasks",
            method="POST",
            payload={"title": "Temporary cache benchmark task"},
            token=token,
        )
        task_id = task["id"]

        cold_start = time.perf_counter()
        _, cold_result = request_json("/tasks", token=token)
        cold_latency_ms = (time.perf_counter() - cold_start) * 1000

        warm_start = time.perf_counter()
        for _ in range(WARM_REQUESTS):
            request_start = time.perf_counter()
            _, warm_result = request_json("/tasks", token=token)
            warm_samples_ms.append((time.perf_counter() - request_start) * 1000)
            if warm_result != cold_result:
                raise AssertionError("Cached task-list response differs from the cold response")
        warm_elapsed = time.perf_counter() - warm_start
        sorted_samples = sorted(warm_samples_ms)
        p95_index = int((len(sorted_samples) - 1) * 0.95)

        print(json.dumps({
            "api_base_url": BASE_URL,
            "concurrency": 1,
            "cold_task_list_latency_ms": round(cold_latency_ms, 2),
            "warm_requests": WARM_REQUESTS,
            "warm_duration_seconds": round(warm_elapsed, 3),
            "warm_throughput_rps": round(WARM_REQUESTS / warm_elapsed, 2),
            "warm_latency_ms_p50": round(statistics.median(sorted_samples), 2),
            "warm_latency_ms_p95": round(sorted_samples[p95_index], 2),
            "warm_latency_ms_max": round(max(sorted_samples), 2),
            "errors": 0,
            "responses_consistent": True,
            "note": "single-client local Docker baseline; not a sustained capacity or AWS performance result",
        }, indent=2))
    finally:
        if user_id is not None:
            with SessionLocal() as db:
                user = db.get(User, user_id)
                if user is not None:
                    db.delete(user)
                    db.commit()
            task_cache.invalidate(f"tasks:{user_id}")


if __name__ == "__main__":
    main()