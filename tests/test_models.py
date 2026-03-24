import unittest
from unittest.mock import patch

from aind_airflow_jobs.models import (
    AirflowTaskSettings,
    SlurmClientSettings,
)


class TestAirflowContextSettings(unittest.TestCase):
    """Tests for the AirflowContextSettings class"""

    def test_default(self):
        """Tests default AirflowContextSettings"""
        settings = AirflowTaskSettings(ctx_task_id="task_1")
        self.assertEqual("task_1", settings.ctx_task_id)
        self.assertIsNone(settings.ctx_dag_id)
        self.assertIsNone(settings.ctx_dag_run_id)
        self.assertIsNone(settings.ctx_dag_run_conf)

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
        settings = AirflowTaskSettings()
        self.assertEqual("my_task", settings.ctx_task_id)
        self.assertEqual("my_dag", settings.ctx_dag_id)
        self.assertEqual("run_123", settings.ctx_dag_run_id)
        self.assertEqual({"key": "value"}, settings.ctx_dag_run_conf)


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
