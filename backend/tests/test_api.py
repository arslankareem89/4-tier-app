import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "test.sqlite3"
    test_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    test_session_local = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    main.Base.metadata.create_all(bind=test_engine)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(main, "SessionLocal", test_session_local)
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    main.task_cache.values.clear()

    def override_get_db():
        with test_session_local() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_get_db
    test_client = TestClient(main.app)
    yield test_client, test_session_local, upload_dir
    test_client.close()
    main.app.dependency_overrides.clear()
    main.task_cache.values.clear()
    test_engine.dispose()


def register(client, email):
    response = client.post("/auth/register", json={"email": email, "password": "safe-test-password"})
    assert response.status_code == 201
    return response.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_authentication_validation_and_duplicate_registration(client):
    api, _, _ = client
    assert api.get("/tasks").status_code == 401
    assert api.get("/uploads").status_code == 401
    assert api.post("/uploads", files={"file": ("unauthorized.txt", b"no", "text/plain")}).status_code == 401
    assert api.get("/tasks", headers=auth("not-a-token")).status_code == 401
    assert api.post("/auth/register", json={"email": "not-an-email", "password": "safe-test-password"}).status_code == 422
    assert api.post("/auth/register", json={"email": "short@example.test", "password": "short"}).status_code == 422

    token = register(api, " Person@Example.test ")
    duplicate = api.post("/auth/register", json={"email": "person@example.test", "password": "safe-test-password"})
    assert duplicate.status_code == 409
    login = api.post("/auth/login", json={"email": "PERSON@example.test", "password": "safe-test-password"})
    assert login.status_code == 200
    assert api.get("/auth/me", headers=auth(token)).json()["email"] == "person@example.test"
    assert api.post("/auth/login", json={"email": "person@example.test", "password": "wrong-password"}).status_code == 401


def test_task_crud_cache_invalidation_and_database_persistence(client):
    api, test_session_local, _ = client
    token = register(api, "owner@example.test")
    headers = auth(token)

    created = api.post("/tasks", headers=headers, json={"title": "Persist me", "description": "database check"})
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "PENDING"

    task_id = task["id"]
    with test_session_local() as db:
        persisted = db.get(main.Task, task_id)
        assert persisted is not None
        assert persisted.title == "Persist me"

    listed = api.get("/tasks", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [task_id]

    updated = api.patch(f"/tasks/{task_id}", headers=headers, json={"title": "Updated", "status": "COMPLETED"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated"
    assert updated.json()["status"] == "COMPLETED"
    assert api.get("/tasks", headers=headers).json()[0]["title"] == "Updated"

    deleted = api.delete(f"/tasks/{task_id}", headers=headers)
    assert deleted.status_code == 204
    assert api.get("/tasks", headers=headers).json() == []
    assert api.patch(f"/tasks/{task_id}", headers=headers, json={"title": "Missing"}).status_code == 404
    assert api.delete(f"/tasks/{task_id}", headers=headers).status_code == 404


def test_repeated_task_list_hits_cache_and_writes_invalidate_it(client):
    api, test_session_local, _ = client
    token = register(api, "cache-observer@example.test")
    headers = auth(token)
    created = api.post("/tasks", headers=headers, json={"title": "Cache me"})
    task_id = created.json()["id"]
    engine = test_session_local.kw["bind"]
    task_list_queries = []

    def count_task_list_query(connection, cursor, statement, parameters, context, executemany):
        normalized = statement.lower()
        if (
            normalized.lstrip().startswith("select")
            and "from tasks" in normalized
            and "tasks.user_id" in normalized
            and "order by tasks.id desc" in normalized
        ):
            task_list_queries.append(statement)

    event.listen(engine, "before_cursor_execute", count_task_list_query)
    try:
        first = api.get("/tasks", headers=headers)
        assert first.status_code == 200
        assert len(task_list_queries) == 1

        repeated = api.get("/tasks", headers=headers)
        assert repeated.json() == first.json()
        assert len(task_list_queries) == 1

        updated = api.patch(f"/tasks/{task_id}", headers=headers, json={"title": "Cache invalidated"})
        assert updated.status_code == 200
        after_update = api.get("/tasks", headers=headers)
        assert after_update.json()[0]["title"] == "Cache invalidated"
        assert len(task_list_queries) == 2

        deleted = api.delete(f"/tasks/{task_id}", headers=headers)
        assert deleted.status_code == 204
        after_delete = api.get("/tasks", headers=headers)
        assert after_delete.json() == []
        assert len(task_list_queries) == 3
    finally:
        event.remove(engine, "before_cursor_execute", count_task_list_query)


def test_users_cannot_read_or_mutate_each_others_tasks(client):
    api, _, _ = client
    owner_token = register(api, "owner@example.test")
    other_token = register(api, "other@example.test")
    created = api.post("/tasks", headers=auth(owner_token), json={"title": "Private task"})
    task_id = created.json()["id"]

    assert api.get("/tasks", headers=auth(other_token)).json() == []
    assert api.patch(f"/tasks/{task_id}", headers=auth(other_token), json={"title": "Hijack"}).status_code == 404
    assert api.delete(f"/tasks/{task_id}", headers=auth(other_token)).status_code == 404
    assert api.get("/tasks", headers=auth(owner_token)).json()[0]["title"] == "Private task"


def test_upload_is_processed_persisted_and_downloadable(client):
    api, test_session_local, upload_dir = client
    token = register(api, "uploader@example.test")
    content = b"repeatable upload test content"
    response = api.post(
        "/uploads",
        headers=auth(token),
        files={"file": ("report.txt", content, "text/plain")},
    )
    assert response.status_code == 202
    upload_id = response.json()["id"]

    uploads = api.get("/uploads", headers=auth(token))
    assert uploads.status_code == 200
    uploaded = next(item for item in uploads.json() if item["id"] == upload_id)
    assert uploaded["processing_status"] == "complete"
    assert uploaded["sha256"] == hashlib.sha256(content).hexdigest()

    with test_session_local() as db:
        record = db.get(main.Upload, upload_id)
        assert record is not None
        assert record.processing_status == "complete"
        stored_path = upload_dir / record.stored_name
        assert stored_path.read_bytes() == content

    download = api.get(f"/uploads/{upload_id}/file", headers=auth(token))
    assert download.status_code == 200
    assert download.content == content


def test_uploads_are_private_and_missing_files_return_not_found(client):
    api, test_session_local, upload_dir = client
    owner_token = register(api, "uploader@example.test")
    other_token = register(api, "observer@example.test")
    upload = api.post(
        "/uploads",
        headers=auth(owner_token),
        files={"file": ("private.txt", b"private", "text/plain")},
    )
    upload_id = upload.json()["id"]

    assert api.get("/uploads", headers=auth(other_token)).json() == []
    assert api.get(f"/uploads/{upload_id}/file", headers=auth(other_token)).status_code == 404
    assert api.get("/uploads/missing/file", headers=auth(owner_token)).status_code == 404
    with test_session_local() as db:
        record = db.get(main.Upload, upload_id)
        (upload_dir / record.stored_name).unlink()
    missing_bytes = api.get(f"/uploads/{upload_id}/file", headers=auth(owner_token))
    assert missing_bytes.status_code == 404
    assert missing_bytes.json()["detail"] == "Stored file is missing"


def test_empty_oversized_and_missing_uploads_are_rejected_safely(client, monkeypatch):
    api, _, upload_dir = client
    token = register(api, "validation@example.test")
    headers = auth(token)

    missing = api.post("/uploads", headers=headers)
    empty = api.post("/uploads", headers=headers, files={"file": ("empty.txt", b"", "text/plain")})
    assert missing.status_code == 422
    assert empty.status_code == 400
    assert list(upload_dir.iterdir()) == []

    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 4)
    oversized = api.post("/uploads", headers=headers, files={"file": ("large.txt", b"12345", "text/plain")})
    assert oversized.status_code == 413
    assert list(upload_dir.iterdir()) == []


def test_upload_processing_failure_is_persisted_and_logged(client, caplog):
    api, test_session_local, _ = client
    token = register(api, "failure@example.test")
    response = api.post(
        "/uploads",
        headers=auth(token),
        files={"file": ("will-fail.txt", b"test", "text/plain")},
    )
    upload_id = response.json()["id"]
    with test_session_local() as db:
        upload = db.get(main.Upload, upload_id)
        upload.processing_status = "processing"
        db.commit()

    main.process_upload(upload_id, "/file/that/does/not/exist")

    with test_session_local() as db:
        failed_upload = db.get(main.Upload, upload_id)
        assert failed_upload.processing_status == "failed"
    assert f"upload_processing_failed upload_id={upload_id}" in caplog.text


def test_ttl_cache_expires_and_can_be_invalidated(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: now[0])
    cache = main.TTLCache(ttl_seconds=5)
    cache.set("key", ["cached"])
    assert cache.get("key") == ["cached"]
    now[0] = 106.0
    assert cache.get("key") is None

    cache.set("key", ["fresh"])
    cache.invalidate("key")
    assert cache.get("key") is None