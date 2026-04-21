"""Module to handle sending alerts."""

import logging
from typing import Any, Dict, Optional

from aind_airflow_jobs.models import AirflowTaskSettings


def get_job_info_from_airflow_task_settings(
    settings: AirflowTaskSettings,
) -> Dict[str, Any]:
    """
    Parses AirflowTaskSettings for job information.

    Parameters
    ----------
    settings : AirflowTaskSettings

    Returns
    -------
    Dict[str, Any]
    """
    job = settings.ctx_dag_run_conf
    run_id = settings.ctx_dag_run_id
    task_id = settings.ctx_task_id
    return {
        "job_name": job.get("s3_prefix", "unknown_job"),
        "run_id": run_id,
        "task_id": task_id,
    }


def get_job_info_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses airflow context dictionary for job information.

    Parameters
    ----------
    context : Dict[str, Any]

    Returns
    -------
    Dict[str, Any]

    """
    job = context["dag_run"].conf
    run_id = context["dag_run"].run_id
    task_id = context["task"].task_id
    return {
        "job_name": job.get("s3_prefix", "unknown_job"),
        "run_id": run_id,
        "task_id": task_id,
    }


def send_log_message(
    job_info: Dict[str, Any],
    message: Optional[str] = None,
    log_level: str = "INFO",
) -> None:
    """
    Sends a log message given the job information.

    Parameters
    ----------
    job_info : Dict[str, Any]
    message : str | None
    log_level : str

    Returns
    -------
    None

    """

    job_name = job_info["job_name"]
    run_id = job_info["run_id"]
    task_id = job_info["task_id"]
    logging_message = (
        f"{job_name} on {run_id} and {task_id}"
        if message is None
        else f"{job_name} on {run_id} and {task_id}: {message}"
    )
    sanitized_message = logging_message.replace("\n", " ")
    level_name = logging.getLevelName(log_level)
    level = level_name if isinstance(level_name, int) else logging.INFO
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.log(
        level,
        sanitized_message,
        extra={
            "acquisition_name": job_name,
            "process_name": task_id,
            "run_id": run_id,
        },
    )
