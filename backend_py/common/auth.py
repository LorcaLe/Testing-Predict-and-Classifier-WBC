import hmac
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from common import config

SESSION_COOKIE = "cleardoc_session"
signer = URLSafeTimedSerializer(config.SESSION_SECRET)


def session(request: Request) -> str:
    try:
        value = signer.loads(request.cookies.get(SESSION_COOKIE, ""), salt="session", max_age=604800)
        if not isinstance(value, str):
            raise BadSignature("Invalid session")
        return value
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Your session has expired. Refresh the page to start a new session.")


def create_session(request: Request, response: Response) -> str:
    try:
        return session(request)
    except HTTPException:
        identifier = str(uuid4())
        response.set_cookie(
            SESSION_COOKIE, signer.dumps(identifier, salt="session"),
            httponly=True, secure=config.COOKIE_SECURE, samesite="lax", max_age=604800,
        )
        response.headers["Cache-Control"] = "no-store"
        return identifier


def check_origin(request: Request):
    if request.headers.get("origin") != config.PUBLIC_ORIGIN:
        raise HTTPException(403, "This request must originate from the ClearDoc application.")


def internal(request: Request):
    supplied = request.headers.get("x-internal-token", "")
    if not hmac.compare_digest(supplied, config.INTERNAL_TOKEN):
        raise HTTPException(403, "Internal access only.")


def download_token(job_id: str, owner: str) -> str:
    return signer.dumps({"job_id": job_id, "owner": owner}, salt="download")


def verify_download(token: str, job_id: str, owner: str):
    try:
        payload = signer.loads(token, salt="download", max_age=900)
        if payload != {"job_id": job_id, "owner": owner}:
            raise BadSignature("Token does not match")
    except (BadSignature, SignatureExpired):
        raise HTTPException(403, "This download link has expired. Generate a new link from your result.")

