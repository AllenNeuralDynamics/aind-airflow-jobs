"""Module to handle sending emails and alerts."""

import logging
from enum import Enum
from typing import Any, Dict, Optional

from airflow.utils.email import send_email

from aind_airflow_jobs.log_handler import LokiLoggerHook


class AlertType(str, Enum):
    """Types of email notifications a user can select"""

    BEGIN = "begin"
    END = "end"
    FAIL = "fail"
    RETRY = "retry"
    ALL = "all"

    def action(self) -> str:
        """Maps enum to action verb string"""
        return {
            self.BEGIN.value: "started",
            self.END.value: "finished",
            self.FAIL.value: "failed",
            self.RETRY.value: "retried",
        }[self.value]


def send_job_email(alert_type: AlertType, job: Dict[str, Any]) -> None:
    """
    Send an email given the alert type and job.
    Parameters
    ----------
    alert_type : AlertType
    job : Dict[str, Any]

    Returns
    -------
    None

    """
    s3_prefix = job.get("s3_prefix", "unknown")
    reason = alert_type.action()
    subject = f"Airflow {reason} {s3_prefix}"
    if job.get("user_email") is not None and (
        alert_type.value in job.get("email_notification_types", [])
        or alert_type.ALL.value in job.get("email_notification_types", [])
    ):
        to_email = job.get("user_email")
        body = (
            f"An airflow pipeline {reason} with the following conf\n\n"
            f"Conf: {job}\n\n"
        )
        send_email(to=to_email, subject=subject, html_content=body)


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
    handler = LokiLoggerHook().get_conn()
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
    logger.addHandler(handler)
    logger.log(level, sanitized_message)
    logger.removeHandler(handler)


def on_failure_or_retry_alert(
    alert_type: AlertType, context: Dict[str, Any]
) -> None:
    """
    Send alert when task fails or retries.
    Parameters
    ----------
    alert_type : AlertType
    context : Dict[str, Any]

    Returns
    -------
    None

    """
    job = context["params"]
    send_job_email(alert_type=alert_type, job=job)


def on_failure_or_retry_log_alert(
    alert_type: AlertType, context: Dict[str, Any]
) -> None:
    """
    Send log message when task fails or retries.
    Parameters
    ----------
    alert_type : AlertType
    context : Dict[str, Any]

    Returns
    -------
    None

    """
    job = context["params"]
    job_info = get_job_info_from_context(context)
    send_log_message(job_info, log_level="ERROR")
    send_job_email(alert_type=alert_type, job=job)


def on_begin_or_end_alert(alert_type: AlertType, job: Dict[str, Any]) -> None:
    """
    Send an email when DAG starts or finishes.
    Parameters
    ----------
    alert_type : AlertType
    job : Dict[str, Any]

    Returns
    -------
    None

    """
    send_job_email(alert_type=alert_type, job=job)
