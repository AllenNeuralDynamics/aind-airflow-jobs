"""CLI module for check_connections DAG tasks."""

import argparse
import os
import sys
import boto3

from aind_airflow_jobs.handlers.slurm_v2_handler import SlurmClientSettings

def check_param_store_connection():
    """Check AWS parameter store connections."""
    # Airflow Variables and Connections are loaded as env vars
    default_transfer_settings = os.getenv("DEFAULT_TRANSFER_SETTINGS")
    slurm_uri = os.getenv("SLURM_URI")
    ams_uri = os.getenv("AMS_URI")
    co_uri = os.getenv("CO_URI")
    
    print(f"default_transfer_settings: {default_transfer_settings}")
    print(f"ams_uri: {ams_uri}")

    if not default_transfer_settings:
        raise AssertionError("Unable to retrieve default_transfer_settings!")
    if not slurm_uri:
        raise AssertionError("Unable to retrieve slurm_uri!")
    if not ams_uri:
        raise AssertionError("Unable to retrieve ams_uri!")
    if not co_uri:
        raise AssertionError("Unable to retrieve co_uri!")


def check_aws_connection():
    """Check AWS S3 connection."""

    s3_bucket = os.getenv("S3_BUCKET")
    if not s3_bucket:
        raise AssertionError("S3_BUCKET environment variable not set!")
    
    s3_client = boto3.client("s3")
    try:
        s3_client.list_objects_v2(
            Bucket=s3_bucket,
            MaxKeys=1,
        )
        print(f"Successfully connected to S3 bucket: {s3_bucket}")
    finally:
        s3_client.close()


def check_slurm_connection():
    """Check SLURM connection."""

    settings = SlurmClientSettings()
    slurm_api = settings.create_api_client()
    response = slurm_api.slurm_v0040_get_ping()
    print(f"SLURM ping response: {response}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tasks for check_connections DAG")
    parser.add_argument('task_id', help='Id of the task to run')
    
    args = parser.parse_args()
    
    # Get function by name from current module
    current_module = sys.modules[__name__]
    task_func = getattr(current_module, args.task_id, None)
    
    if task_func is None or not callable(task_func):
        print(f"Task function '{args.task_id}' not found or not callable!")
        sys.exit(1)
    
    try:
        task_func()
        print(f"Task '{args.task_id}' completed successfully!")
    except Exception as e:
        print(f"Task '{args.task_id}' failed: {e}")
        sys.exit(1)