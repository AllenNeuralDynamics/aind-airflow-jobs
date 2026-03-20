"""Tests for example dag_tasks module"""

import unittest

from aind_airflow_jobs.dag_tasks.example import hello_world


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    def test_hello_world(self):
        """Tests hello_world task function."""

        with self.assertLogs(level="INFO") as captured:
            hello_world()

        self.assertEqual(["INFO:root:Hello, World!"], captured.output)


if __name__ == "__main__":
    unittest.main()
