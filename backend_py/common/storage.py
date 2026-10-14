import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from common import config


def client():
    return boto3.client(
        "s3", endpoint_url=os.getenv("S3_ENDPOINT", "http://storage:9000"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "cleardoc"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY", ""), region_name="us-east-1",
        config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=30,
                      retries={"max_attempts": 2}, s3={"addressing_style": "path"}),
    )


def ensure_bucket():
    s3 = client()
    try:
        s3.head_bucket(Bucket=config.BUCKET)
    except ClientError as error:
        if error.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise
        try:
            s3.create_bucket(Bucket=config.BUCKET)
        except ClientError as conflict:
            if conflict.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise


def put(key: str, data: bytes, content_type: str):
    client().put_object(Bucket=config.BUCKET, Key=key, Body=data, ContentType=content_type)


def get(key: str) -> bytes:
    body = client().get_object(Bucket=config.BUCKET, Key=key)["Body"]
    try:
        return body.read()
    finally:
        body.close()


def delete_prefix(prefix: str):
    s3 = client()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=config.BUCKET, Prefix=prefix):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            response = s3.delete_objects(Bucket=config.BUCKET, Delete={"Objects": objects})
            if response.get("Errors"):
                raise RuntimeError("Artifact cleanup could not remove all objects")

