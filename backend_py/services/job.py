from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response
from psycopg.types.json import Jsonb

from common import config, storage
from common.auth import check_origin, download_token, internal, session, verify_download
from common.broker import start_outbox
from common.contracts import JobRequest, event
from common.db import connect, enqueue, initialize

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY,
    owner text NOT NULL,
    request_id uuid NOT NULL,
    document_id uuid NOT NULL,
    filename text NOT NULL,
    source_key text NOT NULL,
    page_count integer NOT NULL,
    settings jsonb NOT NULL,
    status text NOT NULL DEFAULT 'QUEUED',
    result_key text,
    previews jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    UNIQUE(owner, request_id)
);
CREATE TABLE IF NOT EXISTS received_events (id uuid PRIMARY KEY, received_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS jobs_document ON jobs(document_id);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize(SCHEMA)
    stop, thread = start_outbox()
    yield
    stop.set()
    thread.join(timeout=3)


app = FastAPI(title="ClearDoc Job Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    with connect() as database:
        database.execute("SELECT 1")
    return {"status": "ok", "service": "job"}


@app.post("/api/jobs", status_code=202, dependencies=[Depends(check_origin)])
def submit(body: JobRequest, owner: str = Depends(session)):
    with connect() as database:
        previous = database.execute("SELECT * FROM jobs WHERE owner=%s AND request_id=%s", (owner, body.request_id)).fetchone()
    if previous:
        if previous["document_id"] != body.document_id or previous["settings"] != body.settings.model_dump():
            raise HTTPException(409, "This request ID has already been used for different settings.")
        return {"id": previous["id"], "status": previous["status"]}
    try:
        response = httpx.get(
            f"{config.DOCUMENT_URL}/internal/documents/{body.document_id}", params={"owner": owner},
            headers={"x-internal-token": config.INTERNAL_TOKEN}, timeout=15,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Document service is temporarily unavailable. Please retry.")
    if response.status_code != 200:
        raise HTTPException(response.status_code if response.status_code in (404, 410) else 503, "Document is unavailable. Please upload it again.")
    document = response.json()
    identifier = str(uuid4())
    settings = body.settings.model_dump()
    with connect() as database:
        inserted = database.execute(
            """INSERT INTO jobs(id, owner, request_id, document_id, filename, source_key, page_count, settings, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(owner, request_id) DO NOTHING RETURNING id""",
            (identifier, owner, body.request_id, body.document_id, document["filename"], document["source_key"], document["page_count"], Jsonb(settings), document["expires_at"]),
        ).fetchone()
        if not inserted:
            previous = database.execute("SELECT * FROM jobs WHERE owner=%s AND request_id=%s", (owner, body.request_id)).fetchone()
            if previous["document_id"] != body.document_id or previous["settings"] != settings:
                raise HTTPException(409, "This request ID has already been used for different settings.")
            return {"id": previous["id"], "status": previous["status"]}
        enqueue(database, "processing", event("ProcessingRequested", identifier, {
            "document_id": str(body.document_id), "source_key": document["source_key"], "settings": settings,
        }))
    return {"id": identifier, "status": "QUEUED"}


def get_job(identifier, owner):
    with connect() as database:
        row = database.execute("SELECT * FROM jobs WHERE id=%s AND owner=%s", (identifier, owner)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found.")
    if row["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(410, "This result has expired. Upload your document again.")
    return row


@app.get("/api/jobs/{identifier}")
def status(identifier: UUID, response: Response, owner: str = Depends(session)):
    response.headers["Cache-Control"] = "no-store"
    row = get_job(identifier, owner)
    result = {key: row[key] for key in ("id", "document_id", "filename", "page_count", "status", "error", "created_at", "expires_at", "settings")}
    result["download_url"] = f"/api/jobs/{identifier}/download?token={download_token(str(identifier), owner)}" if row["result_key"] else None
    result["preview_ready"] = bool(row["previews"])
    return result


@app.get("/api/jobs/{identifier}/download")
def download(identifier: UUID, token: str, owner: str = Depends(session)):
    verify_download(token, str(identifier), owner)
    row = get_job(identifier, owner)
    if not row["result_key"]:
        raise HTTPException(409, "Your document is still processing.")
    return Response(storage.get(row["result_key"]), media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="cleardoc-watermarked.pdf"', "Cache-Control": "no-store",
    })


@app.get("/api/jobs/{identifier}/preview/{variant}/{page}")
def preview(identifier: UUID, variant: str, page: int, owner: str = Depends(session)):
    row = get_job(identifier, owner)
    if variant not in ("original", "result") or not 0 <= page < row["page_count"]:
        raise HTTPException(404, "Preview page not found.")
    if not row["previews"]:
        raise HTTPException(409, "Your preview is not available yet.")
    return Response(storage.get(row["previews"][variant][page]), media_type="image/png", headers={"Cache-Control": "private, no-store"})


@app.get("/internal/documents/{identifier}/activity", dependencies=[Depends(internal)])
def activity(identifier: UUID):
    with connect() as database:
        active = database.execute(
            "SELECT EXISTS(SELECT 1 FROM jobs WHERE document_id=%s AND status IN ('QUEUED','PROCESSING','GENERATING_PREVIEW')) AS active", (identifier,),
        ).fetchone()["active"]
    return {"active": active}

