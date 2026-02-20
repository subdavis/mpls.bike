#!/usr/bin/env python3
"""Pull database from S3-compatible storage (GCP bucket via interoperability API)."""

import sys
from pathlib import Path

from botocore.exceptions import ClientError

from s3_config import BUCKET_NAME, DB_KEY, LOCAL_DB_PATH, get_s3_client


def main():
    local_path = Path(LOCAL_DB_PATH)

    # Ensure data directory exists
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Get S3 client
    s3 = get_s3_client()

    try:
        print(f"Downloading s3://{BUCKET_NAME}/{DB_KEY} to {local_path}...")
        s3.download_file(BUCKET_NAME, DB_KEY, str(local_path))
        print(f"✓ Successfully downloaded database to {local_path}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            print(
                f"No existing database found at s3://{BUCKET_NAME}/{DB_KEY}, starting fresh"
            )
        else:
            print(f"Error downloading database: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
