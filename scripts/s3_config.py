"""Shared S3 configuration for GCS bucket interoperability."""

import os
import sys

import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# S3/GCS configuration
BUCKET_NAME = "bikegroups-org"
DB_KEY = "calendar_sync_db/calendar_sync.db"
LOCAL_DB_PATH = "data/calendar_sync.db"


def get_s3_client():
    """Create and return an S3 client configured for GCS interoperability.

    Reads credentials from environment variables:
    - ACCESS_KEY_ID: GCS interoperability access key
    - SECRET_ACCESS_KEY: GCS interoperability secret key
    - API_URL: S3 endpoint URL (defaults to https://storage.googleapis.com)

    Returns:
        boto3.client: Configured S3 client

    Exits:
        If required credentials are not found in environment
    """
    access_key = os.getenv("ACCESS_KEY_ID")
    secret_key = os.getenv("SECRET_ACCESS_KEY")
    endpoint_url = os.getenv("API_URL", "https://storage.googleapis.com")

    if not access_key or not secret_key:
        print("Error: ACCESS_KEY_ID and SECRET_ACCESS_KEY must be set in environment")
        sys.exit(1)

    # GCS S3 interoperability requires signature version 's3' (v2)
    config = Config(signature_version="s3")

    return boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint_url,
        config=config,
    )
