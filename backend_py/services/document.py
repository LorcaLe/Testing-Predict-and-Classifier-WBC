from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pymupdf

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile

from common import config, storage
from common.auth import check_origin, create_session, internal, session
from common.db import connect, initialize
from common.pdf import UnsupportedDocument, open_pdf

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY,
    owner text NOT NULL,
    filename text NOT NULL,
    source_key text NOT NULL,
    byte_size integer NOT NULL,
    page_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '24 hours',
    deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS documents_owner ON documents(owner);
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize(SCHEMA)
    storage.ensure_bucket()
    yield


app = FastAPI(title="ClearDoc Document Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    with connect() as database:
        database.execute("SELECT 1")
    return {"status": "ok", "service": "document"}


@app.get("/api/session")
def bootstrap(request: Request, response: Response):
    create_session(request, response)
    return {"max_file_mb": 20, "max_pages": 50, "supported_formats": ["pdf"], "supported_operations": ["add"]}


@app.get("/api/sample")
def sample():
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=595, height=842)
        green = (0.09, 0.24, 0.20)
        page.draw_rect(pymupdf.Rect(48, 48, 72, 72), fill=green, color=green)
        page.insert_text((87, 65), "STUDIO NORTH", fontsize=11, color=green)
        page.insert_text((48, 133), "PROJECT PROPOSAL", fontsize=9, color=(0.45, 0.48, 0.46))
        page.insert_text((48, 185), "Making room", fontsize=38, color=green)
        page.insert_text((48, 230), "for better ideas.", fontsize=38, color=green)
        page.insert_text((48, 274), "Brand strategy & creative direction", fontsize=12)
        page.draw_line((48, 310), (547, 310), color=(0.8, 0.82, 0.79))
        sections = [
            ("01  The opportunity", "A clear identity brings people and purpose together. This proposal\nsets out a thoughtful approach to building a brand that feels distinct,\nworks beautifully, and grows with the people behind it."),
            ("02  Our approach", "Discover what matters. Define a shared direction. Design a coherent\nsystem across every touchpoint. We make space for collaboration\nand turn promising ideas into practical, lasting outcomes."),
            ("03  What comes next", "A discovery workshop, a focused creative exploration, and a shared\nroadmap. Together, we will shape the next chapter with intention."),
        ]
        y = 360
        for heading, paragraph in sections:
            page.insert_text((48, y), heading, fontsize=14, color=green)
            page.insert_text((48, y + 29), paragraph, fontsize=10, lineheight=1.7, color=(0.35, 0.38, 0.36))
            y += 120
        page.draw_line((48, 772), (547, 772), color=(0.8, 0.82, 0.79))
        page.insert_text((48, 793), "CLEARDOC SAMPLE DOCUMENT", fontsize=8, color=green)
        page.insert_text((490, 793), "01 / 01", fontsize=8, color=green)
        return Response(pdf.tobytes(), media_type="application/pdf")


@app.post("/api/documents", status_code=201, dependencies=[Depends(check_origin)])
def upload(file: UploadFile, owner: str = Depends(session)):
    filename = (file.filename or "document.pdf").replace("\\", "/").split("/")[-1][:180]
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(415, "This first release supports PDF files. DOCX support is planned.")
    data = file.file.read(config.MAX_BYTES + 1)
    if len(data) > config.MAX_BYTES:
        raise HTTPException(413, "Your document exceeds the 20 MB upload limit.")
    try:
        with open_pdf(data) as pdf:
            page_count = pdf.page_count
    except UnsupportedDocument as error:
        raise HTTPException(422, str(error))
    identifier = str(uuid4())
    key = f"documents/{identifier}/source.pdf"
    storage.put(key, data, "application/pdf")
    try:
        with connect() as database:
            row = database.execute(
                "INSERT INTO documents(id, owner, filename, source_key, byte_size, page_count) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                (identifier, owner, filename, key, len(data), page_count),
            ).fetchone()
    except Exception:
        storage.delete_prefix(f"documents/{identifier}/")
        raise
    return public_document(row)


def public_document(row):
    return {key: row[key] for key in ("id", "filename", "byte_size", "page_count", "created_at", "expires_at")}


def find_document(identifier, owner):
    with connect() as database:
        row = database.execute("SELECT * FROM documents WHERE id=%s AND owner=%s", (identifier, owner)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found.")
    if row["deleted_at"] or row["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(410, "This document has expired. Upload it again to continue.")
    return row


@app.get("/api/documents/{identifier}/original")
def original(identifier: UUID, owner: str = Depends(session)):
    row = find_document(identifier, owner)
    return Response(storage.get(row["source_key"]), media_type="application/pdf", headers={"Cache-Control": "no-store"})


@app.get("/internal/documents/{identifier}", dependencies=[Depends(internal)])
def internal_document(identifier: UUID, owner: str):
    return find_document(identifier, owner)

