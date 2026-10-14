import json
import logging
import threading
import time

import pika

from common import config
from common.db import connect

logger = logging.getLogger("cleardoc")
QUEUES = ("processing", "preview", "job-events")


def connection():
    parameters = pika.URLParameters(config.AMQP_URL)
    parameters.heartbeat = 300
    parameters.blocked_connection_timeout = 15
    parameters.socket_timeout = 10
    return pika.BlockingConnection(parameters)


def topology(channel):
    for queue in QUEUES:
        channel.queue_declare(queue=queue + ".dead", durable=True)
        channel.queue_declare(queue=queue, durable=True, arguments={
            "x-dead-letter-exchange": "", "x-dead-letter-routing-key": queue + ".dead",
        })
        channel.queue_declare(queue=queue + ".retry", durable=True, arguments={
            "x-message-ttl": 5000, "x-dead-letter-exchange": "", "x-dead-letter-routing-key": queue,
        })
    channel.confirm_delivery()
    channel.basic_qos(prefetch_count=1)


def publish(channel, queue: str, payload: dict, attempts: int = 0):
    channel.basic_publish(
        exchange="", routing_key=queue, body=json.dumps(payload).encode(), mandatory=True,
        properties=pika.BasicProperties(
            content_type="application/json", delivery_mode=2, message_id=payload["event_id"],
            correlation_id=payload["correlation_id"], headers={"attempts": attempts},
        ),
    )


def flush_outbox(channel):
    with connect() as database:
        rows = database.execute(
            "SELECT * FROM outbox WHERE published_at IS NULL ORDER BY created_at LIMIT 20 FOR UPDATE SKIP LOCKED"
        ).fetchall()
        for row in rows:
            publish(channel, row["queue"], row["payload"])
            database.execute("UPDATE outbox SET published_at=now() WHERE id=%s", (row["id"],))


def outbox_loop(stop: threading.Event):
    while not stop.is_set():
        try:
            with connection() as rabbit:
                channel = rabbit.channel()
                topology(channel)
                while not stop.is_set():
                    flush_outbox(channel)
                    rabbit.process_data_events(time_limit=0.1)
                    stop.wait(0.5)
        except Exception as error:
            logger.warning("outbox_retry service=%s error=%s", config.SERVICE, type(error).__name__)
            stop.wait(3)


def start_outbox():
    stop = threading.Event()
    thread = threading.Thread(target=outbox_loop, args=(stop,), daemon=True)
    thread.start()
    return stop, thread

