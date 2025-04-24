"""Tests methods in the alert_handler module."""

import unittest
from unittest.mock import MagicMock, call, patch

from aind_airflow_jobs.alert_handler import (
    AlertType,
    get_job_info_from_context,
    on_failure_or_retry_alert,
    on_failure_or_retry_log_alert,
    send_job_email,
    send_log_message, on_begin_or_end_alert,
)


class TestAlertType(unittest.TestCase):
    """Test methods in the AlertType class"""

    def test_action_map(self):
        """Tests action map method."""

        self.assertEqual("failed", AlertType.FAIL.action())
        self.assertEqual("started", AlertType.BEGIN.action())
        self.assertEqual("finished", AlertType.END.action())
        self.assertEqual("retried", AlertType.RETRY.action())


class TestMethods(unittest.TestCase):
    """Tests methods in module."""

    @patch("aind_airflow_jobs.alert_handler.send_email")
    def test_send_job_email(self, mock_send: MagicMock):
        """Tests send_job_email method"""

        job = {
            "s3_prefix": "ecephys_123456_2020-10-10_10-10-10",
            "user_email": "example@example.com",
            "email_notification_types": "all",
        }

        send_job_email(alert_type=AlertType.BEGIN, job=job)
        mock_send.assert_called_once_with(
            to="example@example.com",
            subject="Airflow started ecephys_123456_2020-10-10_10-10-10",
            html_content=(
                "An airflow pipeline started with the following conf\n\n"
                "Conf:"
                " {'s3_prefix': 'ecephys_123456_2020-10-10_10-10-10',"
                " 'user_email': 'example@example.com',"
                " 'email_notification_types': 'all'}\n\n"
            ),
        )

    def test_get_job_info_from_context(self):
        """Tests get_job_info_from_context method"""

        mock_dag_run = MagicMock(
            conf={"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"},
            run_id="abc-123",
        )
        mock_task = MagicMock(task_id="def-456")
        context = {"dag_run": mock_dag_run, "task": mock_task}
        job_info = get_job_info_from_context(context=context)
        expected_info = {
            "job_name": "ecephys_123456_2020-10-10_10-10-10",
            "run_id": "abc-123",
            "task_id": "def-456",
        }
        self.assertEqual(expected_info, job_info)

    @patch("aind_airflow_jobs.alert_handler.LokiLoggerHook")
    @patch("logging.getLogger")
    def test_send_log_message(
        self, mock_logger: MagicMock, mock_loki: MagicMock
    ):
        """Tests send_log_message method"""

        job_info = {
            "job_name": "ecephys_123456_2020-10-10_10-10-10",
            "run_id": "abc-123",
            "task_id": "def-456",
        }
        mock_log = MagicMock()
        mock_logger.return_value.log = mock_log
        send_log_message(job_info=job_info, log_level="DEBUG", message="Hello")

        mock_loki.assert_has_calls([call(), call().get_conn()])
        mock_logger.assert_has_calls([call("aind_airflow_jobs.alert_handler")])
        mock_log.assert_called_once_with(
            10,
            "ecephys_123456_2020-10-10_10-10-10 on abc-123 and def-456: Hello",
        )

    @patch("aind_airflow_jobs.alert_handler.send_job_email")
    def test_on_failure_or_retry_alert(self, mock_email: MagicMock):
        """Tests on_failure_or_retry_alert method"""

        context = {
            "params": {"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"}
        }
        on_failure_or_retry_alert(alert_type=AlertType.FAIL, context=context)

        mock_email.assert_called_once_with(
            alert_type=AlertType.FAIL,
            job={"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"},
        )

    @patch("aind_airflow_jobs.alert_handler.send_log_message")
    @patch("aind_airflow_jobs.alert_handler.send_job_email")
    def test_on_failure_or_retry_log_alert(
        self, mock_email: MagicMock, mock_log: MagicMock
    ):
        """Tests on_failure_or_retry_log_alert method"""

        mock_dag_run = MagicMock(
            conf={"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"},
            run_id="abc-123",
        )
        mock_task = MagicMock(task_id="def-456")
        context = {
            "dag_run": mock_dag_run,
            "task": mock_task,
            "params": {"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"},
        }

        on_failure_or_retry_log_alert(
            alert_type=AlertType.FAIL, context=context
        )

        mock_log.assert_called_once_with(
            {
                "job_name": "ecephys_123456_2020-10-10_10-10-10",
                "run_id": "abc-123",
                "task_id": "def-456",
            },
            log_level="ERROR",
        )
        mock_email.assert_called_once_with(
            alert_type=AlertType.FAIL,
            job={"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"},
        )

    @patch("aind_airflow_jobs.alert_handler.send_job_email")
    def test_on_begin_or_end_alert(self, mock_email: MagicMock):
        """Tests on_begin_or_end_alert method"""

        job = {
            "s3_prefix": "ecephys_123456_2020-10-10_10-10-10",
            "user_email": "example@example.com",
            "email_notification_types": "all",
        }
        on_begin_or_end_alert(alert_type=AlertType.BEGIN, job=job)

        mock_email.assert_called_once_with(
            alert_type=AlertType.BEGIN,
            job=job,
        )


if __name__ == "__main__":
    unittest.main()
