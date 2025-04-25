"""Tests for log_handler module"""

import unittest
from unittest.mock import MagicMock, patch

from aind_airflow_jobs.log_handler import LokiLoggerHook


class TestLokiLoggerHook(unittest.TestCase):
    """Test methods in LokiLoggerHook class"""

    @patch("aind_airflow_jobs.log_handler.LokiHandler")
    @patch("aind_airflow_jobs.log_handler.Variable.get")
    @patch(
        "aind_airflow_jobs.log_handler.Connection.get_connection_from_secrets"
    )
    def test_class_construct(
        self,
        mock_connection: MagicMock,
        mock_variable: MagicMock,
        mock_loki_handler: MagicMock,
    ):
        """Tests class constructor."""

        mock_connection.return_value.get_uri.return_value = (
            "http://example.com"
        )
        mock_variable.return_value = "test"
        LokiLoggerHook()
        mock_loki_handler.assert_called_once_with(
            url="http://example.com/loki/api/v1/push",
            version="1",
            tags={"application": "aind-airflow-service-test"},
        )

    @patch("aind_airflow_jobs.log_handler.LokiHandler")
    @patch("aind_airflow_jobs.log_handler.Variable.get")
    @patch(
        "aind_airflow_jobs.log_handler.Connection.get_connection_from_secrets"
    )
    def test_class_construct_custom_host(
        self,
        mock_connection: MagicMock,
        mock_variable: MagicMock,
        mock_loki_handler: MagicMock,
    ):
        """Tests class constructor with custom host."""

        mock_connection.return_value.get_uri.return_value = "something"
        mock_variable.return_value = "test"
        LokiLoggerHook(host="http://example.com")
        mock_loki_handler.assert_called_once_with(
            url="http://example.com/loki/api/v1/push",
            version="1",
            tags={"application": "aind-airflow-service-test"},
        )


if __name__ == "__main__":
    unittest.main()
