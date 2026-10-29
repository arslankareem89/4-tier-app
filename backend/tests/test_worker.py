import json

import worker


class FakeSQS:
    def __init__(self):
        self.deleted = []
        self.visibility_changes = []

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    def change_message_visibility(self, **kwargs):
        self.visibility_changes.append(kwargs)


def make_message(receive_count=1):
    return {
        "Body": json.dumps({
            "upload_id": "test-upload-id",
            "storage_key": "test-upload-id.txt",
        }),
        "ReceiptHandle": "test-receipt",
        "Attributes": {"ApproximateReceiveCount": str(receive_count)},
    }


def test_worker_deletes_only_after_success(monkeypatch):
    monkeypatch.setattr(
        worker.main,
        "process_upload",
        lambda upload_id, storage_key, raise_on_error: True,
    )
    client = FakeSQS()

    assert worker.handle_message(
        make_message(), client, "https://sqs.example/queue"
    )
    assert len(client.deleted) == 1
    assert client.visibility_changes == []


def test_worker_retries_failure_without_deleting(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("test processing failure")

    monkeypatch.setattr(worker.main, "process_upload", fail)
    monkeypatch.setattr(worker.random, "randint", lambda a, b: 0)
    monkeypatch.setattr(worker, "MAX_RECEIVES", 3)
    client = FakeSQS()

    assert not worker.handle_message(
        make_message(1), client, "https://sqs.example/queue"
    )
    assert client.deleted == []
    assert client.visibility_changes[0]["VisibilityTimeout"] == 2


def test_worker_marks_exhausted_job_failed_and_leaves_for_dlq(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("test processing failure")

    statuses = []
    monkeypatch.setattr(worker.main, "process_upload", fail)
    monkeypatch.setattr(
        worker.main,
        "update_upload_status",
        lambda upload_id, state: statuses.append((upload_id, state)) or True,
    )
    monkeypatch.setattr(worker, "MAX_RECEIVES", 3)
    client = FakeSQS()

    assert not worker.handle_message(
        make_message(3), client, "https://sqs.example/queue"
    )
    assert statuses == [("test-upload-id", "failed")]
    assert client.deleted == []
    assert client.visibility_changes == []
