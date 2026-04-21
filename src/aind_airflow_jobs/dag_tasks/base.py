"""Base class for running DAG tasks."""

import logging
from typing import Optional

from aind_airflow_jobs.models import AirflowTaskSettings


class DagTasks:
    """Base class for running DAG tasks."""

    def __init__(
        self, airflow_task_settings: Optional[AirflowTaskSettings] = None
    ):
        """Fetch Airflow context from environment variables"""
        self.airflow_task_settings = (
            AirflowTaskSettings()
            if airflow_task_settings is None
            else airflow_task_settings
        )

    def run_task(self):
        """Run the appropriate task based on Airflow task_id"""
        task_id = self.airflow_task_settings.ctx_task_id
        task_func = getattr(self, task_id, None)

        if task_func is None or not callable(task_func):
            raise ValueError(
                f"Task function '{task_id}' not found or not callable!"
            )

        logging.info(
            f"Task '{task_id}' starting.",
            extra={
                "process_name": task_id,
                "pipeline_name": "airflow DAG",
                "event_type": "stage_start",
            },
        )
        task_func()
        logging.info(
            f"Task '{task_id}' completed successfully!",
            extra={
                "process_name": task_id,
                "pipeline_name": "airflow DAG",
                "event_type": "stage_complete",
            },
        )
