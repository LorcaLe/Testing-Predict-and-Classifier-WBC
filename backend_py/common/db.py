import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from common import config


def connect():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row, connect_timeout=5)


def initialize(sql: str):
    with connect() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(28142026)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id uuid PRIMARY KEY,
                queue text NOT NULL,
                payload jsonb NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                published_at timestamptz
            );
        """)
        connection.execute(sql)


def enqueue(connection, queue: str, event: dict):
    connection.execute(
        "INSERT INTO outbox (id, queue, payload) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (event["event_id"], queue, Jsonb(event)),
    )

