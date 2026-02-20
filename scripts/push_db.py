#!/usr/bin/env python3
"""Push database to S3-compatible storage (GCP bucket via interoperability API)."""

import sys
from pathlib import Path

from botocore.exceptions import ClientError

from s3_config import BUCKET_NAME, DB_KEY, LOCAL_DB_PATH, get_s3_client


def main():
    local_path = Path(LOCAL_DB_PATH)

    # Check if database file exists
    if not local_path.exists():
        print(f"Error: Database file not found at {local_path}")
        sys.exit(1)

    # Get S3 client
    s3 = get_s3_client()

    try:
        print(f"Uploading {local_path} to s3://{BUCKET_NAME}/{DB_KEY}...")
        with open(local_path, "rb") as f:
            s3.put_object(Bucket=BUCKET_NAME, Key=DB_KEY, Body=f)
        print(f"✓ Successfully uploaded database to s3://{BUCKET_NAME}/{DB_KEY}")
    except ClientError as e:
        print(f"Error uploading database: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
