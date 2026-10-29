"""Dedicated SQS upload-processing worker."""

import json
import logging
import os
import random
import signal
import threading

import boto3
from botocore.exceptions import BotoCoreError, ClientError

import main

logger = logging.getLogger("upload_worker")

QUEUE_URL = os.getenv("SQS_QUEUE_URL")
MAX_RECEIVES = int(os.getenv("SQS_MAX_RECEIVE_COUNT", "3"))
WAIT_SECONDS = min(20, max(0, int(os.getenv("SQS_WAIT_TIME_SECONDS", "20"))))
VISIBILITY_SECONDS = max(
    30, int(os.getenv("SQS_VISIBILITY_TIMEOUT_SECONDS", "120"))
)


def handle_message(message, client, queue_url):
    attributes = message.get("Attributes") or {}
    try:
        receive_count = int(attributes.get("ApproximateReceiveCount", "1"))
    except (TypeError, ValueError):
        receive_count = 1

    upload_id = None

    try:
        payload = json.loads(message["Body"])
        upload_id = payload.get("upload_id")
        storage_key = payload.get("storage_key")

        if not isinstance(upload_id, str) or not upload_id:
            raise ValueError("Missing upload_id")
        if not isinstance(storage_key, str) or not storage_key:
            raise ValueError("Missing storage_key")

        if main.process_upload(
            upload_id,
            storage_key,
            raise_on_error=True,
        ) is not True:
            raise RuntimeError("Processor did not confirm completion")

    except Exception:
        logger.exception(
            "upload_job_processing_failed receive_count=%s",
            receive_count,
        )

        if receive_count >= MAX_RECEIVES:
            if upload_id:
                try:
                    main.update_upload_status(upload_id, "failed")
                except Exception:
                    logger.exception("upload_job_final_status_update_failed")

            # Leave the message undeleted; SQS redrive policy sends it to DLQ.
            logger.error(
                "upload_job_max_receive_count_exceeded receives=%s",
                receive_count,
            )
        else:
            delay = min(
                VISIBILITY_SECONDS,
                2 ** min(receive_count, 6) + random.randint(0, 3),
            )
            try:
                client.change_message_visibility(
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                    VisibilityTimeout=delay,
                )
            except Exception:
                logger.exception("upload_job_retry_visibility_update_failed")

        return False

    try:
        client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=message["ReceiptHandle"],
        )
    except Exception:
        logger.exception("upload_job_acknowledgement_failed")
        return False

    logger.info("upload_job_acknowledged")
    return True


def run_worker():
    if not QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL is required")
    if not main.S3_BUCKET:
        raise RuntimeError("S3_BUCKET is required")
    if MAX_RECEIVES < 1:
        raise RuntimeError("SQS_MAX_RECEIVE_COUNT must be positive")

    client = boto3.client("sqs", region_name=main.AWS_REGION)
    stopping = threading.Event()

    def request_shutdown(signum, _frame):
        logger.info("upload_worker_shutdown_requested signal=%s", signum)
        stopping.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    logger.info("upload_worker_started")

    failures = 0
    while not stopping.is_set():
        try:
            response = client.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=WAIT_SECONDS,
                VisibilityTimeout=VISIBILITY_SECONDS,
                AttributeNames=["ApproximateReceiveCount"],
            )
            failures = 0
        except (BotoCoreError, ClientError):
            failures += 1
            delay = min(30, 2 ** min(failures, 5))
            delay *= random.uniform(0.75, 1.25)
            logger.exception(
                "upload_queue_receive_failed retry_seconds=%.1f",
                delay,
            )
            stopping.wait(delay)
            continue

        for message in response.get("Messages", []):
            handle_message(message, client, QUEUE_URL)

    logger.info("upload_worker_stopped")


if __name__ == "__main__":
    run_worker()
