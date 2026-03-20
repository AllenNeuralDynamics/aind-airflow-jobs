"""Tests for check_connections dag_tasks module"""

import unittest
from unittest.mock import MagicMock, patch

from aind_airflow_jobs.dag_tasks.check_connections import (
    check_aws_connection,
    check_hpc_connection,
    check_param_store_connection,
    check_slurm_connection,
    check_vast_connection,
)


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    @patch.dict(
        "os.environ",
        {
            "DEFAULT_TRANSFER_SETTINGS": '{"foo": "bar"}',
            "SLURM_URI": "http://slurm2/api",
            "AMS_URI": "http://example.com",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection(self):
        """Tests check_param_store_connection."""

        with self.assertLogs(level="INFO") as captured:
            check_param_store_connection()

        self.assertEqual(
            [
                'INFO:root:default_transfer_settings: {"foo": "bar"}',
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

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                check_param_store_connection()

        self.assertEqual(
            "Unable to retrieve default_transfer_settings!",
            exc.exception.args[0],
        )

    @patch.dict(
        "os.environ",
        {
            "DEFAULT_TRANSFER_SETTINGS": '{"foo": "bar"}',
            "AMS_URI": "http://example.com",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_slurm_uri(self):
        """Tests check_param_store_connection missing slurm uri."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                check_param_store_connection()

        self.assertEqual(
            "Unable to retrieve slurm_uri!", exc.exception.args[0]
        )

    @patch.dict(
        "os.environ",
        {
            "DEFAULT_TRANSFER_SETTINGS": '{"foo": "bar"}',
            "SLURM_URI": "http://slurm2/api",
            "CO_URI": "https://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_ams_uri(self):
        """Tests check_param_store_connection missing ams uri."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                check_param_store_connection()

        self.assertEqual("Unable to retrieve ams_uri!", exc.exception.args[0])

    @patch.dict(
        "os.environ",
        {
            "DEFAULT_TRANSFER_SETTINGS": '{"foo": "bar"}',
            "SLURM_URI": "http://slurm2/api",
            "AMS_URI": "http://example.com",
        },
        clear=True,
    )
    def test_check_param_store_connection_missing_co_uri(self):
        """Tests check_param_store_connection missing co uri."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                check_param_store_connection()

        self.assertEqual("Unable to retrieve co_uri!", exc.exception.args[0])

    @patch("aind_airflow_jobs.dag_tasks.check_connections.boto3.client")
    @patch.dict("os.environ", {"S3_BUCKET": "my-bucket"}, clear=True)
    def test_check_aws_connection(self, mock_boto_client: MagicMock):
        """Tests check_aws_connection."""

        mock_s3_client = MagicMock()
        mock_boto_client.return_value = mock_s3_client

        check_aws_connection()

        mock_boto_client.assert_called_once_with("s3")
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket="my-bucket", MaxKeys=1
        )
        mock_s3_client.close.assert_called_once()

    @patch("aind_airflow_jobs.dag_tasks.check_connections.boto3.client")
    @patch.dict("os.environ", {"S3_BUCKET": "my-bucket"}, clear=True)
    def test_check_aws_connection_closes_on_error(
        self, mock_boto_client: MagicMock
    ):
        """Tests check_aws_connection closes client after error."""

        mock_s3_client = MagicMock()
        mock_s3_client.list_objects_v2.side_effect = RuntimeError("error")
        mock_boto_client.return_value = mock_s3_client

        with self.assertRaises(RuntimeError) as exc:
            check_aws_connection()

        self.assertEqual("error", exc.exception.args[0])
        mock_s3_client.close.assert_called_once()

    @patch.dict("os.environ", {}, clear=True)
    def test_check_aws_connection_missing_bucket(self):
        """Tests check_aws_connection when bucket env is missing."""

        with self.assertRaises(AssertionError) as exc:
            check_aws_connection()

        self.assertEqual(
            "S3_BUCKET environment variable not set!", exc.exception.args[0]
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
            check_slurm_connection()

        mock_slurm_settings.assert_called_once_with()
        mock_slurm_settings.return_value.create_api_client.assert_called_once()
        mock_api.slurm_v0040_get_ping.assert_called_once_with()
        self.assertEqual(
            ["INFO:root:SLURM ping response: pong"],
            captured.output,
        )

    @patch("aind_airflow_jobs.dag_tasks.check_connections.Path.is_dir")
    @patch.dict(
        "os.environ", {"SLURM_LOGS_DIR": "/allen/aind/logs"}, clear=True
    )
    def test_check_vast_connection(self, mock_is_dir: MagicMock):
        """Tests check_vast_connection validates mounted directory."""

        mock_is_dir.return_value = True
        check_vast_connection()

        mock_is_dir.assert_called_once_with()

    @patch("aind_airflow_jobs.dag_tasks.check_connections.Path.is_dir")
    @patch.dict(
        "os.environ", {"SLURM_LOGS_DIR": "/allen/aind/logs"}, clear=True
    )
    def test_check_vast_connection_not_directory(self, mock_is_dir: MagicMock):
        """Tests check_vast_connection when directory is invalid."""

        mock_is_dir.return_value = False
        with self.assertRaises(NotADirectoryError) as exc:
            check_vast_connection()

        self.assertEqual("/data/logs not recognized!", exc.exception.args[0])

    @patch.dict("os.environ", {}, clear=True)
    def test_check_vast_connection_missing_env(self):
        """Tests check_vast_connection when env var is missing."""

        with self.assertRaises(AssertionError) as exc:
            check_vast_connection()

        self.assertEqual(
            "SLURM_LOGS_DIR environment variable not set!",
            exc.exception.args[0],
        )

    @patch.dict(
        "os.environ", {"SSH_COMMAND_OUTPUT": "SGVsbG8gV29ybGQ="}, clear=True
    )
    def test_check_hpc_connection(self):
        """Tests check_hpc_connection."""

        with self.assertLogs(level="INFO") as captured:
            check_hpc_connection()

        self.assertEqual(
            [
                "INFO:root:"
                "SSH Command Output: SGVsbG8gV29ybGQ=. Decoded: Hello World"
            ],
            captured.output,
        )

    @patch.dict("os.environ", {"SSH_COMMAND_OUTPUT": "Zm9v"}, clear=True)
    def test_check_hpc_connection_invalid_output(self):
        """Tests check_hpc_connection when command output is unexpected."""

        with self.assertLogs(level="INFO"):
            with self.assertRaises(AssertionError) as exc:
                check_hpc_connection()

        self.assertEqual(
            "Unexpected SSH command output: foo", exc.exception.args[0]
        )


if __name__ == "__main__":
    unittest.main()
