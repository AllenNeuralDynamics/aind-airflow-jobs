"""Tests methods in the alert_handler module."""

import unittest
from unittest.mock import MagicMock, call, patch

from aind_airflow_jobs.handlers.alert_handler import (
    get_job_info_from_airflow_task_settings,
    get_job_info_from_context,
    send_log_message,
)
from aind_airflow_jobs.models import AirflowTaskSettings


class TestMethods(unittest.TestCase):
    """Tests methods in module."""

    def test_get_job_info_from_airflow_task_settings(self):
        """Tests get_job_info_from_airflow_task_settings method"""

        settings = AirflowTaskSettings(
            ctx_task_id="def-456",
            ctx_dag_run_id="abc-123",
            ctx_dag_run_conf={
                "s3_prefix": "ecephys_123456_2020-10-10_10-10-10"
            },
        )
        job_info = get_job_info_from_airflow_task_settings(settings=settings)
        expected_info = {
            "job_name": "ecephys_123456_2020-10-10_10-10-10",
            "run_id": "abc-123",
            "task_id": "def-456",
        }
        self.assertEqual(expected_info, job_info)

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

    @patch("logging.getLogger")
    def test_send_log_message(self, mock_logger: MagicMock):
        """Tests send_log_message method"""

        job_info = {
            "job_name": "ecephys_123456_2020-10-10_10-10-10",
            "run_id": "abc-123",
            "task_id": "def-456",
        }
        mock_log = MagicMock()
        mock_logger.return_value.log = mock_log
        send_log_message(job_info=job_info, log_level="DEBUG", message="Hello")

        mock_logger.assert_has_calls(
            [call("aind_airflow_jobs.handlers.alert_handler")]
        )
        mock_log.assert_called_once_with(
            10,
            "ecephys_123456_2020-10-10_10-10-10 on abc-123 and def-456: Hello",
        )


if __name__ == "__main__":
    unittest.main()
