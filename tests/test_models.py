import unittest
from unittest.mock import patch

from aind_airflow_jobs.models import (
    AirflowContextSettings,
    SlurmClientSettings,
)


class TestAirflowContextSettings(unittest.TestCase):
    """Tests for the AirflowContextSettings class"""

    def test_default(self):
        """Tests default AirflowContextSettings"""
        settings = AirflowContextSettings(task_id="task_1")
        self.assertEqual("task_1", settings.task_id)
        self.assertIsNone(settings.dag_id)
        self.assertIsNone(settings.dag_run_id)
        self.assertIsNone(settings.dag_run_conf)

    @patch.dict(
        "os.environ",
        {
            "AIRFLOW_CTX_TASK_ID": "my_task",
            "AIRFLOW_CTX_DAG_ID": "my_dag",
            "AIRFLOW_CTX_DAG_RUN_ID": "run_123",
            "AIRFLOW_CTX_DAG_RUN_CONF": '{"key": "value"}',
        },
        clear=True,
    )
    def test_from_env(self):
        """Tests creating settings from env vars"""
        settings = AirflowContextSettings()
        self.assertEqual("my_task", settings.task_id)
        self.assertEqual("my_dag", settings.dag_id)
        self.assertEqual("run_123", settings.dag_run_id)
        self.assertEqual({"key": "value"}, settings.dag_run_conf)


class TestSlurmClientSettings(unittest.TestCase):
    """Test methods in the SlurmClientSettings class"""

    def test_create_api_client(self):
        """Tests create_api_client method"""

        settings = SlurmClientSettings(
            host="http://example.com", username="user", access_token="abc-123"
        )

        api_client = settings.create_api_client()
        self.assertEqual("user", api_client.api_client.configuration.username)
        self.assertEqual(
            "abc-123", api_client.api_client.configuration.access_token
        )
