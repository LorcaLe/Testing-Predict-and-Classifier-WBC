import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from psycopg.types.json import Jsonb

from common.broker import connection, flush_outbox, publish, topology
from common.contracts import Event, event
from common.db import connect, enqueue, initialize

logging.basicConfig(level=logging.INFO, format='%(asctime)s level=%(levelname)s %(message)s')
logger = logging.getLogger("cleardoc")
ROLE = os.environ.get("WORKER_ROLE", "processing")
WORKER_SCHEMA = "CREATE TABLE IF NOT EXISTS receipts(job_id uuid PRIMARY KEY, output jsonb NOT NULL, completed_at timestamptz NOT NULL DEFAULT now());"


def apply_job_event(payload):
    with connect() as database:
        if not database.execute("INSERT INTO received_events(id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING id", (payload["event_id"],)).fetchone():
            return
        row = database.execute("SELECT * FROM jobs WHERE id=%s FOR UPDATE", (payload["job_id"],)).fetchone()
        if not row:
            raise ValueError("Unknown job")
        kind, data, status = payload["type"], payload["data"], row["status"]
        if kind == "ProcessingStarted" and status == "QUEUED":
            database.execute("UPDATE jobs SET status='PROCESSING', updated_at=now() WHERE id=%s", (row["id"],))
        elif kind == "ProcessingCompleted" and status in ("QUEUED", "PROCESSING"):
            database.execute("UPDATE jobs SET status='GENERATING_PREVIEW', result_key=%s, updated_at=now() WHERE id=%s", (data["result_key"], row["id"]))
            enqueue(database, "preview", event("PreviewRequested", str(row["id"]), {
                "document_id": str(row["document_id"]), "source_key": row["source_key"], "result_key": data["result_key"],
            }))
        elif kind == "ProcessingFailed" and status in ("QUEUED", "PROCESSING"):
            database.execute("UPDATE jobs SET status='FAILED', error=%s, updated_at=now() WHERE id=%s", (data["error"], row["id"]))
        elif kind == "PreviewReady" and status == "GENERATING_PREVIEW":
            database.execute("UPDATE jobs SET status='COMPLETED', previews=%s, updated_at=now() WHERE id=%s", (Jsonb(data["previews"]), row["id"]))
        elif kind == "PreviewFailed" and status == "GENERATING_PREVIEW":
            database.execute("UPDATE jobs SET status='COMPLETED_WITH_PREVIEW_ERROR', error=%s, updated_at=now() WHERE id=%s", (data["error"], row["id"]))


def process(payload, channel):
    expected = "ProcessingRequested" if ROLE == "processing" else "PreviewRequested"
    if payload["type"] != expected:
        raise ValueError("Unexpected event type")
    with connect() as database:
        # A transaction lock serializes duplicate deliveries across worker replicas.
        database.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (payload["job_id"],))
        if database.execute("SELECT 1 FROM receipts WHERE job_id=%s", (payload["job_id"],)).fetchone():
            return
        if ROLE == "processing":
            publish(channel, "job-events", event("ProcessingStarted", payload["job_id"], {}))
        result = subprocess.run(
            [sys.executable, "-m", "services.transform"], input=json.dumps(payload),
            capture_output=True, text=True, timeout=120 if ROLE == "preview" else 60,
        )
        if result.returncode == 2:
            output = json.loads(result.stdout)
            record_failure(database, payload, output["permanent_error"])
            return
        if result.returncode:
            raise RuntimeError("Document processing subprocess failed")
        output = json.loads(result.stdout)
        database.execute("INSERT INTO receipts(job_id, output) VALUES (%s,%s)", (payload["job_id"], Jsonb(output)))
        enqueue(database, "job-events", event("ProcessingCompleted" if ROLE == "processing" else "PreviewReady", payload["job_id"], output))


def record_failure(database, payload, message):
    inserted = database.execute(
        "INSERT INTO receipts(job_id, output) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING job_id",
        (payload["job_id"], Jsonb({"error": message})),
    ).fetchone()
    if inserted:
        enqueue(database, "job-events", event("ProcessingFailed" if ROLE == "processing" else "PreviewFailed", payload["job_id"], {"error": message}))


def run():
    if ROLE == "job-events":
        from services.job import SCHEMA
        initialize(SCHEMA)
    else:
        initialize(WORKER_SCHEMA)
    while True:
        try:
            with connection() as rabbit:
                channel = rabbit.channel()
                topology(channel)
                for method, properties, body in channel.consume(ROLE, inactivity_timeout=1):
                    Path("/tmp/worker-alive").touch()
                    flush_outbox(channel)
                    if not method:
                        continue
                    payload = None
                    attempts = int((properties.headers or {}).get("attempts", 0))
                    try:
                        payload = Event.model_validate_json(body).model_dump(mode="json")
                        if ROLE == "job-events":
                            apply_job_event(payload)
                        else:
                            process(payload, channel)
                        channel.basic_ack(method.delivery_tag)
                        logger.info("event_completed role=%s job_id=%s", ROLE, payload["job_id"])
                    except Exception as error:
                        logger.warning("event_failed role=%s job_id=%s attempt=%s error=%s", ROLE, payload and payload["job_id"], attempts, type(error).__name__)
                        if payload and attempts < 2:
                            publish(channel, ROLE + ".retry", payload, attempts + 1)
                            channel.basic_ack(method.delivery_tag)
                        else:
                            if payload and ROLE != "job-events":
                                with connect() as database:
                                    record_failure(database, payload, "Processing could not finish after three attempts. Please try a new job.")
                            channel.basic_nack(method.delivery_tag, requeue=False)
        except Exception as error:
            logger.warning("worker_reconnecting role=%s error=%s", ROLE, type(error).__name__)
            time.sleep(3)


if __name__ == "__main__":
    run()

