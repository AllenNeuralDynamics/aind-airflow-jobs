"""Tests for base dag_tasks module"""

import unittest
from unittest.mock import MagicMock, patch

from aind_airflow_jobs.dag_tasks.base import DagTasks


class TestDagTasks(unittest.TestCase):
    """Tests for the DagTasks base class"""

    @patch.dict("os.environ", {"AIRFLOW_CTX_TASK_ID": "task_1"}, clear=True)
    def test_init(self):
        """Tests that __init__ reads Airflow context from env vars."""

        dag = DagTasks()
        self.assertEqual("task_1", dag.airflow_task_settings.ctx_task_id)

    @patch.dict("os.environ", {"AIRFLOW_CTX_TASK_ID": "task_1"}, clear=True)
    def test_run_task(self):
        """Tests run_task calls the method matching task_id."""

        mock_task = MagicMock()
        with self.assertLogs(level="INFO") as captured:
            with patch.object(DagTasks, "task_1", mock_task, create=True):
                dag = DagTasks()
                dag.run_task()

        mock_task.assert_called_once()
        self.assertEqual(
            [
                "INFO:root:Task 'task_1' starting.",
                "INFO:root:Task 'task_1' completed successfully!",
            ],
            captured.output,
        )

    @patch.dict("os.environ", {"AIRFLOW_CTX_TASK_ID": "foo"}, clear=True)
    def test_run_task_missing_task_method(self):
        """Tests run_task raises ValueError when task_id has no matching
        method."""

        with self.assertRaises(ValueError) as error:
            dag = DagTasks()
            dag.run_task()

        self.assertEqual(
            "Task function 'foo' not found or not callable!",
            error.exception.args[0],
        )
