"""Tests for task_handler module"""

import unittest
from unittest.mock import MagicMock, call, patch

from aind_airflow_jobs.task_handler import (
    get_merged_task_settings,
    nested_update,
)


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    def test_nested_update(self):
        """Tests nested_update method."""

        first_dict = {"a": {"b": 1}, "c": {"d": 3, "e": 4}}
        second_dict = {"a": {"f": 5}}
        nested_update(first_dict, second_dict)
        expected_output = {"a": {"b": 1, "f": 5}, "c": {"d": 3, "e": 4}}
        self.assertEqual(expected_output, first_dict)

    @patch("aind_airflow_jobs.log_handler.Variable.get")
    def test_get_merged_task_settings_custom(self, mock_variable: MagicMock):
        """Tests get_merged_task_settings method with custom job_type"""

        user_task = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        with self.assertLogs(level="INFO") as captured:
            output = get_merged_task_settings(
                job_type="custom",
                user_task=user_task,
                task_id="check_source_folders",
            )
        self.assertEqual(user_task, output)
        self.assertEqual(3, len(captured.output))
        mock_variable.assert_not_called()

    @patch("aind_airflow_jobs.log_handler.Variable.get")
    def test_get_merged_task_settings_preset(self, mock_variable: MagicMock):
        """Tests get_merged_task_settings method with ecephys job_type"""

        user_task = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        mock_variable.return_value = {"a": 4, "b": {"f": 7}}
        with self.assertLogs(level="INFO") as captured:
            output = get_merged_task_settings(
                job_type="ecephys",
                user_task=user_task,
                task_id="check_source_folders",
            )
        expected_output = {"a": 1, "b": {"f": 7, "c": 2, "d": 3}, "e": 4}
        self.assertEqual(expected_output, output)
        self.assertEqual(3, len(captured.output))
        mock_variable.assert_called_once_with(
            key="job_types/v2/ecephys/tasks/check_source_folders",
            default_var=None,
            deserialize_json=True,
        )

    @patch("aind_airflow_jobs.log_handler.Variable.get")
    def test_get_merged_task_settings_default(self, mock_variable: MagicMock):
        """Tests get_merged_task_settings method with default fallback"""

        user_task = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        mock_variable.side_effect = [None, {"a": 4, "b": {"f": 7}}]
        with self.assertLogs(level="INFO") as captured:
            output = get_merged_task_settings(
                job_type="ecephys",
                user_task=user_task,
                task_id="check_source_folders",
            )
        expected_output = {"a": 1, "b": {"f": 7, "c": 2, "d": 3}, "e": 4}
        self.assertEqual(expected_output, output)
        self.assertEqual(3, len(captured.output))
        mock_variable.assert_has_calls(
            [
                call(
                    key="job_types/v2/ecephys/tasks/check_source_folders",
                    default_var=None,
                    deserialize_json=True,
                ),
                call(
                    key="job_types/v2/default/tasks/check_source_folders",
                    default_var={},
                    deserialize_json=True,
                ),
            ]
        )

    @patch("aind_airflow_jobs.log_handler.Variable.get")
    def test_get_merged_task_settings_modality(self, mock_variable: MagicMock):
        """Tests get_merged_task_settings method with modality"""

        user_task = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        mock_variable.return_value = {"a": 4, "b": {"f": 7}}
        with self.assertLogs(level="INFO") as captured:
            output = get_merged_task_settings(
                job_type="ecephys",
                user_task=user_task,
                task_id="modality_transformation_settings",
                modality_abbreviation="behavior-videos",
            )
        expected_output = {"a": 1, "b": {"f": 7, "c": 2, "d": 3}, "e": 4}
        self.assertEqual(expected_output, output)
        self.assertEqual(3, len(captured.output))
        mock_variable.assert_called_once_with(
            key=(
                "job_types/v2/ecephys/tasks/"
                "modality_transformation_settings/behavior-videos"
            ),
            default_var=None,
            deserialize_json=True,
        )


if __name__ == "__main__":
    unittest.main()
