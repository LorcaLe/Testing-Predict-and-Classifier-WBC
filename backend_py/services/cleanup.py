import logging
import time

import httpx

from common import config, storage
from common.db import connect, initialize
from services.document import SCHEMA

logging.basicConfig(level=logging.INFO)


def sweep():
    with connect() as database:
        rows = database.execute("SELECT id FROM documents WHERE expires_at < now() AND deleted_at IS NULL LIMIT 100").fetchall()
    for row in rows:
        response = httpx.get(
            f"{config.JOB_URL}/internal/documents/{row['id']}/activity",
            headers={"x-internal-token": config.INTERNAL_TOKEN}, timeout=10,
        )
        response.raise_for_status()
        if response.json()["active"]:
            continue
        storage.delete_prefix(f"documents/{row['id']}/")
        with connect() as database:
            database.execute("UPDATE documents SET deleted_at=now() WHERE id=%s", (row["id"],))
        logging.info("document_expired id=%s", row["id"])


if __name__ == "__main__":
    initialize(SCHEMA)
    while True:
        try:
            sweep()
        except Exception as error:
            logging.warning("cleanup_retry error=%s", type(error).__name__)
        time.sleep(60)
