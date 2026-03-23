"""CLI module for check_connections DAG tasks."""

import argparse
import base64
import logging
import os
import sys
from pathlib import Path

import boto3

from aind_airflow_jobs.handlers.slurm_v2_handler import SlurmClientSettings

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
)


def check_param_store_connection():
    """Check AWS parameter store connections."""
    # Airflow Variables and Connections must be passed as env vars
    default_transfer_settings = os.getenv("DEFAULT_TRANSFER_SETTINGS")
    slurm_uri = os.getenv("SLURM_URI")
    ams_uri = os.getenv("AMS_URI")
    co_uri = os.getenv("CO_URI")

    logging.info(f"default_transfer_settings: {default_transfer_settings}")
    logging.info(f"ams_uri: {ams_uri}")

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
    finally:
        s3_client.close()


def check_slurm_connection():
    """Check SLURM connection."""

    settings = SlurmClientSettings()
    slurm_api = settings.create_api_client()
    response = slurm_api.slurm_v0040_get_ping()
    logging.info(f"SLURM ping response: {response}")


def check_vast_connection():
    """Check that airflow can read files from VAST."""

    logs_dir = os.getenv("SLURM_LOGS_DIR")
    if not logs_dir:
        raise AssertionError("SLURM_LOGS_DIR environment variable not set!")

    mounted_directory = logs_dir.replace("/allen/aind/", "/data/", 1)
    is_dir = Path(mounted_directory).is_dir()
    if not is_dir:
        raise NotADirectoryError(f"{mounted_directory} not recognized!")


def check_hpc_connection():
    """Check hpc ssh command output can be read"""

    # Airflow XCom output must be passed as env var
    ssh_command_output = os.getenv("SSH_COMMAND_OUTPUT", "")
    decoded_value = base64.b64decode(ssh_command_output).decode("utf-8")
    logging.info(
        f"SSH Command Output: {ssh_command_output}. Decoded: {decoded_value}"
    )

    if decoded_value.strip() != "Hello World":
        raise AssertionError(f"Unexpected SSH command output: {decoded_value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run tasks for check_connections DAG"
    )
    parser.add_argument("task_id", help="Id of the task to run")

    args = parser.parse_args()

    # Get function by name from current module
    current_module = sys.modules[__name__]
    task_func = getattr(current_module, args.task_id, None)

    if task_func is None or not callable(task_func):
        raise ValueError(
            f"Task function '{args.task_id}' not found or not callable!"
        )

    task_func()
    logging.info(f"Task '{args.task_id}' completed successfully!")
