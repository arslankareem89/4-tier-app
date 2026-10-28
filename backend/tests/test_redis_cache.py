from datetime import datetime, timezone

import main


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expirations = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value
        self.expirations[key] = ex

    def delete(self, key):
        self.data.pop(key, None)
        self.expirations.pop(key, None)


def install_fake_redis(monkeypatch, client):
    monkeypatch.setattr(
        main.redis.Redis,
        "from_url",
        classmethod(lambda cls, url, **kwargs: client),
    )


def test_redis_cache_round_trip_and_ttl(monkeypatch):
    client = FakeRedis()
    install_fake_redis(monkeypatch, client)
    cache = main.RedisTTLCache("rediss://cache.example:6379/0", ttl_seconds=12)

    value = [{
        "id": 7,
        "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
    }]
    cache.set("tasks:7", value)

    assert client.expirations["tasks:7"] == 12
    assert cache.get("tasks:7") == [{
        "id": 7,
        "created_at": "2026-01-02T00:00:00+00:00",
    }]


def test_redis_cache_invalid_payload_is_deleted(monkeypatch):
    client = FakeRedis()
    client.data["tasks:7"] = "{invalid json"
    install_fake_redis(monkeypatch, client)
    cache = main.RedisTTLCache("rediss://cache.example:6379/0")

    assert cache.get("tasks:7") is None
    assert "tasks:7" not in client.data


def test_redis_read_failure_returns_cache_miss(monkeypatch):
    class UnavailableRedis(FakeRedis):
        def get(self, key):
            raise main.redis.exceptions.ConnectionError("cache unavailable")

    install_fake_redis(monkeypatch, UnavailableRedis())
    cache = main.RedisTTLCache("rediss://cache.example:6379/0")

    assert cache.get("tasks:7") is None


def test_redis_write_and_invalidation_failures_do_not_raise(monkeypatch):
    class UnavailableRedis(FakeRedis):
        def set(self, key, value, ex=None):
            raise main.redis.exceptions.ConnectionError("cache unavailable")

        def delete(self, key):
            raise main.redis.exceptions.ConnectionError("cache unavailable")

    install_fake_redis(monkeypatch, UnavailableRedis())
    cache = main.RedisTTLCache("rediss://cache.example:6379/0")

    cache.set("tasks:7", [{"id": 7}])
    cache.invalidate("tasks:7")


def test_redis_lookup_logs_hits_and_misses_without_keys(
    monkeypatch, caplog
):
    caplog.set_level("INFO", logger="task_api")
    client = FakeRedis()
    install_fake_redis(monkeypatch, client)
    cache = main.RedisTTLCache("rediss://cache.example:6379/0")
    key = "tasks:private-user-id"

    assert cache.get(key) is None
    cache.set(key, [{"id": 7}])
    assert cache.get(key) == [{"id": 7}]

    messages = [
        record.getMessage()
        for record in caplog.records
        if "shared_cache_" in record.getMessage()
    ]

    assert any(
        "shared_cache_lookup backend=valkey result=miss" in message
        for message in messages
    )
    assert any(
        "shared_cache_lookup backend=valkey result=hit" in message
        for message in messages
    )
    assert all("private-user-id" not in message for message in messages)
