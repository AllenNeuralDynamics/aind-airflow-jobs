"""CLI module for check_connections DAG tasks."""

import base64
import logging
import os
import sys
from pathlib import Path

import boto3

from aind_airflow_jobs.dag_tasks.base import DagTasks
from aind_airflow_jobs.models import SlurmClientSettings

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
)


class CheckConnectionsDag(DagTasks):
    """DAG tasks for checking connections to external services."""

    def check_param_store_connection(self):
        """Check AWS parameter store connections."""
        # Airflow Variables and Connections must be passed as env vars
        default_transfer_settings = (
            self.airflow_task_settings.var_param_default
        )
        slurm_uri = os.getenv("SLURM_URI")
        ams_uri = os.getenv("AMS_URI")
        co_uri = os.getenv("CO_URI")

        logging.info(f"default_transfer_settings: {default_transfer_settings}")
        logging.info(f"ams_uri: {ams_uri}")

        if not default_transfer_settings:
            raise AssertionError(
                "Unable to retrieve default_transfer_settings!"
            )
        if not slurm_uri:
            raise AssertionError("Unable to retrieve slurm_uri!")
        if not ams_uri:
            raise AssertionError("Unable to retrieve ams_uri!")
        if not co_uri:
            raise AssertionError("Unable to retrieve co_uri!")

    def check_aws_connection(self):
        """Check AWS S3 connection."""

        s3_bucket = self.airflow_task_settings.task_input_str
        if not s3_bucket:
            raise AssertionError("task_input_str must be set to S3 bucket!")

        s3_client = boto3.client("s3")
        try:
            s3_client.list_objects_v2(
                Bucket=s3_bucket,
                MaxKeys=1,
            )
        finally:
            s3_client.close()

    def check_slurm_connection(self):
        """Check SLURM connection."""

        settings = SlurmClientSettings()
        slurm_api = settings.create_api_client()
        response = slurm_api.slurm_v0040_get_ping()
        logging.info(f"SLURM ping response: {response}")

    def check_vast_connection(self):
        """Check that airflow can read files from VAST."""

        logs_dir = self.airflow_task_settings.task_input_str
        if not logs_dir:
            raise AssertionError(
                "task_input_str must be set to VAST logs directory!"
            )

        mounted_directory = logs_dir.replace("/allen/aind/", "/data/", 1)
        is_dir = Path(mounted_directory).is_dir()
        if not is_dir:
            raise NotADirectoryError(f"{mounted_directory} not recognized!")

    def check_hpc_connection(self):
        """Check hpc ssh command output can be read"""

        # Airflow XCom output must be passed as env var
        ssh_command_output = self.airflow_task_settings.task_input_str or ""
        decoded = base64.b64decode(ssh_command_output).decode("utf-8")
        logging.info(
            f"SSH Command Output: {ssh_command_output}. Decoded: {decoded}"
        )

        if decoded.strip() != "Hello World":
            raise AssertionError(f"Unexpected SSH command output: {decoded}")


if __name__ == "__main__":
    dag = CheckConnectionsDag()
    dag.run_task()
