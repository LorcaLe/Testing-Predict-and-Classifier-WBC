import pytest
import time
from unittest.mock import patch
from fastapi import HTTPException

from common.auth import download_token, verify_download


def test_download_link_is_bound_to_job_and_session():
    token = download_token("job-a", "owner-a")
    verify_download(token, "job-a", "owner-a")
    with pytest.raises(HTTPException):
        verify_download(token, "job-b", "owner-a")
    with pytest.raises(HTTPException):
        verify_download(token, "job-a", "owner-b")
    with pytest.raises(HTTPException):
        verify_download(token + "tampered", "job-a", "owner-a")


def test_download_link_expires_after_fifteen_minutes():
    with patch("itsdangerous.TimestampSigner.get_timestamp", return_value=int(time.time()) - 901):
        token = download_token("job-a", "owner-a")
    with pytest.raises(HTTPException, match="expired"):
        verify_download(token, "job-a", "owner-a")
