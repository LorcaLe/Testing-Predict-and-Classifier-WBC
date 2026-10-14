import os

SERVICE = os.getenv("SERVICE", "unknown")
DATABASE_URL = os.getenv("DATABASE_URL", "")
AMQP_URL = os.getenv("AMQP_URL", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-test-only")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "development-test-only")
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "http://localhost:8080")
DOCUMENT_URL = os.getenv("DOCUMENT_URL", "http://document:8000")
JOB_URL = os.getenv("JOB_URL", "http://job:8000")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 50
BUCKET = os.getenv("S3_BUCKET", "cleardoc")

