"""Tests for hpc_handler module"""

import unittest
from unittest.mock import MagicMock, patch

from aind_airflow_jobs.hpc_handler import get_hpc_hook


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    @patch("aind_airflow_jobs.hpc_handler.SSHHook")
    def test_get_hpc_hook(self, mock_ssh_hook: MagicMock):
        """Tests get_hpc_hook method."""

        get_hpc_hook()
        mock_ssh_hook.assert_called_once_with(ssh_conn_id="hpc2/uri")

    @patch("aind_airflow_jobs.hpc_handler.SSHHook")
    def test_get_hpc_hook_custom(self, mock_ssh_hook: MagicMock):
        """Test get_hpc_hook method with custom connection id"""

        get_hpc_hook(ssh_conn_id="custom/hpc")

        mock_ssh_hook.assert_called_once_with(ssh_conn_id="custom/hpc")


if __name__ == "__main__":
    unittest.main()
