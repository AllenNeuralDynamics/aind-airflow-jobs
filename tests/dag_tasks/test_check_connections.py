"""Tests for check_connections dag_tasks module"""

import unittest
from unittest.mock import MagicMock, patch

from aind_airflow_jobs.dag_tasks.check_connections import CheckConnectionsDag
from aind_airflow_jobs.models import AirflowTaskSettings


class TestCheckConnectionsDag(unittest.TestCase):
    """Test CheckConnectionsDag class"""

    @classmethod
    def setUpClass(cls):
        """Set up shared resources for tests."""

        settings = AirflowTaskSettings(
            ctx_task_id="task_1",
            var_param_default={"foo": "bar"},
            task_input_str="my-bucket",
        )
        dag = CheckConnectionsDag(airflow_task_settings=settings)
        cls.dag = dag

    @patch.dict(
        "os.environ",
        {
            "SLURM_URI": "http://slurm2/api",
            "AMS_URI": "http://example.com",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection(self):
        """Tests check_param_store_connection."""

        with self.assertLogs(level="INFO") as captured:
            self.dag.check_param_store_connection()

        self.assertEqual(
            [
                "INFO:root:default_transfer_settings: {'foo': 'bar'}",
                "INFO:root:ams_uri: http://example.com",
            ],
            captured.output,
        )

    @patch.dict(
        "os.environ",
        {
            "SLURM_URI": "http://slurm2/api",
            "AMS_URI": "http://example.com",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_default_settings(self):
        """Tests check_param_store_connection missing settings."""

        settings = AirflowTaskSettings(ctx_task_id="task_1")
        dag = CheckConnectionsDag(airflow_task_settings=settings)

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                dag.check_param_store_connection()

        self.assertEqual(
            "Unable to retrieve default_transfer_settings!",
            exc.exception.args[0],
        )

    @patch.dict(
        "os.environ",
        {
            "AMS_URI": "http://example.com",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_slurm_uri(self):
        """Tests check_param_store_connection missing slurm uri."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                self.dag.check_param_store_connection()

        self.assertEqual(
            "Unable to retrieve slurm_uri!", exc.exception.args[0]
        )

    @patch.dict(
        "os.environ",
        {
            "SLURM_URI": "http://slurm2/api",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_ams_uri(self):
        """Tests check_param_store_connection missing ams uri."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                self.dag.check_param_store_connection()

        self.assertEqual("Unable to retrieve ams_uri!", exc.exception.args[0])

    @patch.dict(
        "os.environ",
        {
            "SLURM_URI": "http://slurm2/api",
            "AMS_URI": "http://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_co_uri(self):
        """Tests check_param_store_connection missing co uri."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                self.dag.check_param_store_connection()

        self.assertEqual("Unable to retrieve co_uri!", exc.exception.args[0])

    @patch("aind_airflow_jobs.dag_tasks.check_connections.boto3.client")
    def test_check_aws_connection(self, mock_boto_client: MagicMock):
        """Tests check_aws_connection."""

        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client

        self.dag.check_aws_connection()

        mock_boto_client.assert_called_once_with("s3")
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket", MaxKeys=1
        )
        mock_s3_client.close.assert_called_once()

    @patch("aind_airflow_jobs.dag_tasks.check_connections.boto3.client")
    def test_check_aws_connection_closes_on_error(
        self, mock_boto_client: MagicMock
    ):
        """Tests check_aws_connection closes client after error."""

        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.side_effect = RuntimeError("error")
        mock_boto_client.return_value = mock_s3_client

        with self.assertRaises(RuntimeError) as exc:
            self.dag.check_aws_connection()

        self.assertEqual("error", exc.exception.args[0])
        mock_s3_client.close.assert_called_once()

    def test_check_aws_connection_missing_bucket(self):
        """Tests check_aws_connection when bucket env is missing."""

        settings = AirflowTaskSettings(ctx_task_id="task_1")
        dag = CheckConnectionsDag(airflow_task_settings=settings)
        with self.assertRaises(AssertionError) as exc:
            dag.check_aws_connection()

        self.assertEqual(
            "task_input_str must be set to S3 bucket!", exc.exception.args[0]
        )

    @patch("aind_airflow_jobs.dag_tasks.check_connections.SlurmClientSettings")
    def test_check_slurm_connection(
        self,
        mock_slurm_settings: MagicMock,
    ):
        """Tests check_slurm_connection."""

        mock_api = MagicMock()
        mock_api.slurm_v0040_get_ping.return_value = "pong"
        mock_slurm_settings.return_value.create_api_client.return_value = (
            mock_api
        )

        with self.assertLogs(level="INFO") as captured:
            self.dag.check_slurm_connection()

        mock_slurm_settings.assert_called_once_with()
        mock_slurm_settings.return_value.create_api_client.assert_called_once()
        mock_api.slurm_v0040_get_ping.assert_called_once_with()
        self.assertEqual(
            ["INFO:root:SLURM ping response: pong"],
            captured.output,
        )

    @patch("aind_airflow_jobs.dag_tasks.check_connections.Path.is_dir")
    def test_check_vast_connection(self, mock_is_dir: MagicMock):
        """Tests check_vast_connection validates mounted directory."""

        mock_is_dir.return_value = True
        self.dag.check_vast_connection()

        mock_is_dir.assert_called_once_with()

    @patch("aind_airflow_jobs.dag_tasks.check_connections.Path.is_dir")
    def test_check_vast_connection_not_directory(self, mock_is_dir: MagicMock):
        """Tests check_vast_connection when directory is invalid."""

        mock_is_dir.return_value = False
        with self.assertRaises(NotADirectoryError) as exc:
            self.dag.check_vast_connection()

        self.assertEqual("my-bucket not recognized!", exc.exception.args[0])

    def test_check_vast_connection_missing_env(self):
        """Tests check_vast_connection when env var is missing."""

        settings = AirflowTaskSettings(ctx_task_id="task_1")
        dag = CheckConnectionsDag(airflow_task_settings=settings)

        with self.assertRaises(AssertionError) as exc:
            dag.check_vast_connection()

        self.assertEqual(
            "task_input_str must be set to VAST logs directory!",
            exc.exception.args[0],
        )

    def test_check_hpc_connection(self):
        """Tests check_hpc_connection."""

        settings = AirflowTaskSettings(
            ctx_task_id="task_1",
            task_input_str="SGVsbG8gV29ybGQ=",
        )
        dag = CheckConnectionsDag(airflow_task_settings=settings)
        with self.assertLogs(level="INFO") as captured:
            dag.check_hpc_connection()

        self.assertEqual(
            [
                "INFO:root:"
                "SSH Command Output: SGVsbG8gV29ybGQ=. Decoded: Hello World"
            ],
            captured.output,
        )

    def test_check_hpc_connection_invalid_output(self):
        """Tests check_hpc_connection when command output is unexpected."""

        settings = AirflowTaskSettings(
            ctx_task_id="task_1",
            task_input_str="Zm9v",
        )
        dag = CheckConnectionsDag(airflow_task_settings=settings)

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                dag.check_hpc_connection()

        self.assertEqual(
            "Unexpected SSH command output: foo", exc.exception.args[0]
        )


if __name__ == "__main__":
    unittest.main()
