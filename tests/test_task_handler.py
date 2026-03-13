"""Tests for task_handler module"""

import unittest
from unittest.mock import MagicMock, call, patch

from aind_airflow_jobs.task_handler import (
    create_slurm_job_name,
    get_gather_final_metadata_settings,
    get_gather_preliminary_metadata_settings,
    get_merged_task_settings,
    nested_update,
    update_command_script,
)


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    @classmethod
    def setUpClass(cls):
        """Set up example input data."""
        cls.example_data_processes = [
            (
                '{"name": "Other", "software_version": "", '
                '"start_date_time": "2025-10-04 04:07:21.783185+00:00", '
                '"end_date_time": "2025-10-04 04:09:23.011709+00:00", '
                '"input_location": "data/behavior", '
                '"output_location": "", "code_url": "", '
                '"parameters": {"input_source": "data/behavior"}, '
                '"notes": "Data was copied"}'
            ),
            (
                '{"name": "Other", "software_version": "0.1.7", '
                '"start_date_time": "2025-10-04 04:07:22.333658+00:00", '
                '"end_date_time": "2025-10-04 19:12:26.320761+00:00", '
                '"input_location": "data/behavior-videos", '
                '"output_location": "out/behavior-videos", '
                '"code_url": "ghcr.io/aind-behavior-video-transformation", '
                '"parameters": {"output_directory": "out/behavior-videos", '
                '"input_source": "data/behavior-videos"}, '
                '"notes": null}'
            ),
        ]
        cls.example_pipeline = {
            "object_type": "Code",
            "url": "https://github.com/AllenNeuralDynamics/aind-airflow-dags",
            "name": "transform_and_upload_v2",
            "version": "0.34.0",
            "language": "Python",
            "language_version": "3.10.19",
            "parameters": {
                "job_type": "default",
            },
        }

    def test_create_slurm_job_name(self):
        """Tests create_slurm_job_name method."""

        job_name = create_slurm_job_name(
            s3_prefix="behavior_789908_2025-10-03_20-37-40",
            run_id="manual__2025-11-01T10:00:39.933543+00:00",
        )
        self.assertEqual(
            "behavior_789908_2025-10-03_20-37-40_1e3abad4a9", job_name
        )

    def test_nested_update(self):
        """Tests nested_update method."""

        first_dict = {"a": {"b": 1}, "c": {"d": 3, "e": 4}}
        second_dict = {"a": {"f": 5}}
        nested_update(first_dict, second_dict)
        expected_output = {"a": {"b": 1, "f": 5}, "c": {"d": 3, "e": 4}}
        self.assertEqual(expected_output, first_dict)

    @patch("aind_airflow_jobs.task_handler.Variable.get")
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

    @patch("aind_airflow_jobs.task_handler.Variable.get")
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

    @patch("aind_airflow_jobs.task_handler.Variable.get")
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

    @patch("aind_airflow_jobs.task_handler.Variable.get")
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

    def test_update_command_script(self):
        """Tests update_command_script method."""

        job_settings = {
            "s3_location": "%S3_LOCATION",
            "input_source": "%INPUT_SOURCE",
            "output_location": "%OUTPUT_LOCATION",
        }
        input_script = (
            "run --env_file %ENV_FILE docker://%IMAGE:%IMAGE_VERSION"
            " --job_settings ' %JOB_SETTINGS '"
        )
        output = update_command_script(
            command_script=input_script,
            job_settings=job_settings,
            image="example",
            image_version="0.0.0",
            s3_location="some_s3_location",
            input_source="some_input_source",
            output_location="some_output_location",
            env_file="my_env",
        )
        expected_output = (
            "run --env_file my_env docker://example:0.0.0 --job_settings"
            ' \' {"s3_location": "some_s3_location",'
            ' "input_source": "some_input_source",'
            ' "output_location": "some_output_location"} \''
        )
        self.assertEqual(expected_output, output)

    def test_update_command_script_error(self):
        """Tests update_command_script when placeholders are missing."""

        input_script = (
            "run --env_file %ENV_FILE docker://%IMAGE:%IMAGE_VERSION"
            " --job_settings ' %JOB_SETTINGS '"
        )
        with self.assertRaises(ValueError) as e:
            update_command_script(command_script=input_script)

        self.assertEqual(
            f"{input_script} contains variable that needs replacement.",
            e.exception.args[0],
        )

    def test_gather_metadata_settings_legacy(self):
        """Tests legacy gather metadata settings."""

        job_settings = {
            "processing_settings": {
                "pipeline_process": {
                    "processor_full_name": "AIND Scientific Computing"
                }
            }
        }
        data_processes = self.example_data_processes
        pipeline = self.example_pipeline
        image = "ghcr.io/aind-metadata-mapper"
        image_version = "0.28.2"
        s3_prefix = "behavior_789908_2025-10-03_20-37-40"
        staging_folder = "stage"

        gather_settings = get_gather_final_metadata_settings(
            image=image,
            image_version=image_version,
            job_settings=job_settings,
            data_processes=data_processes,
            pipeline=pipeline,
            s3_prefix=s3_prefix,
            staging_folder=staging_folder,
            location=f"s3://example/{s3_prefix}",
        )
        expected_settings = {
            "directory_to_write_to": "stage",
            "processing_settings": {
                "pipeline_process": {
                    "processor_full_name": "AIND Scientific Computing",
                    "data_processes": [
                        {
                            "name": "Other",
                            "software_version": "",
                            "start_date_time": (
                                "2025-10-04 04:07:21.783185+00:00"
                            ),
                            "end_date_time": (
                                "2025-10-04 04:09:23.011709+00:00"
                            ),
                            "input_location": "data/behavior",
                            "output_location": "",
                            "code_url": "",
                            "parameters": {"input_source": "data/behavior"},
                            "notes": "Data was copied",
                        },
                        {
                            "name": "Other",
                            "software_version": "0.1.7",
                            "start_date_time": (
                                "2025-10-04 04:07:22.333658+00:00"
                            ),
                            "end_date_time": (
                                "2025-10-04 19:12:26.320761+00:00"
                            ),
                            "input_location": "data/behavior-videos",
                            "output_location": "out/behavior-videos",
                            "code_url": (
                                "ghcr.io/aind-behavior-video-transformation"
                            ),
                            "parameters": {
                                "output_directory": "out/behavior-videos",
                                "input_source": "data/behavior-videos",
                            },
                            "notes": None,
                        },
                    ],
                }
            },
            "metadata_settings": {
                "name": "behavior_789908_2025-10-03_20-37-40",
                "location": (
                    "s3://example/behavior_789908_2025-10-03_20-37-40"
                ),
                "subject_filepath": "stage/subject.json",
                "data_description_filepath": "stage/data_description.json",
                "processing_filepath": "stage/processing.json",
                "procedures_filepath": "stage/procedures.json",
                "session_filepath": "stage/session.json",
                "rig_filepath": "stage/rig.json",
                "acquisition_filepath": "stage/acquisition.json",
                "instrument_filepath": "stage/instrument.json",
                "quality_control_filepath": "stage/quality_control.json",
            },
        }

        self.assertEqual(expected_settings, gather_settings)

    def test_gather_metadata_settings_v1(self):
        """Tests version 1 gather metadata settings."""

        job_settings = {
            "processing_settings": {
                "pipeline_process": {
                    "processor_full_name": "AIND Scientific Computing"
                }
            }
        }
        data_processes = self.example_data_processes
        pipeline = self.example_pipeline
        image = "ghcr.io/aind-metadata-mapper"
        image_version = "v1-abc"
        s3_prefix = "behavior_789908_2025-10-03_20-37-40"
        staging_folder = "stage"

        gather_settings = get_gather_final_metadata_settings(
            image=image,
            image_version=image_version,
            job_settings=job_settings,
            data_processes=data_processes,
            pipeline=pipeline,
            s3_prefix=s3_prefix,
            staging_folder=staging_folder,
            location=f"s3://example/{s3_prefix}",
        )
        expected_settings = {
            "output_directory": "stage",
            "processing": {
                "object_type": "Processing",
                "data_processes": [
                    {
                        "object_type": "Data process",
                        "process_type": "Other",
                        "name": "Other",
                        "pipeline_name": "transform_and_upload_v2",
                        "stage": "Processing",
                        "code": {
                            "object_type": "Code",
                            "url": "",
                            "version": "",
                            "parameters": {"input_source": "data/behavior"},
                        },
                        "experimenters": ["AIND Scientific Computing"],
                        "start_date_time": "2025-10-04 04:07:21.783185+00:00",
                        "end_date_time": "2025-10-04 04:09:23.011709+00:00",
                        "notes": "Data was copied",
                    },
                    {
                        "object_type": "Data process",
                        "process_type": "Compression",
                        "name": "Compression",
                        "pipeline_name": "transform_and_upload_v2",
                        "stage": "Processing",
                        "code": {
                            "object_type": "Code",
                            "url": (
                                "ghcr.io/aind-behavior-video-transformation"
                            ),
                            "version": "0.1.7",
                            "parameters": {
                                "output_directory": "out/behavior-videos",
                                "input_source": "data/behavior-videos",
                            },
                        },
                        "experimenters": ["AIND Scientific Computing"],
                        "start_date_time": "2025-10-04 04:07:22.333658+00:00",
                        "end_date_time": "2025-10-04 19:12:26.320761+00:00",
                        "notes": None,
                    },
                ],
                "pipelines": [
                    {
                        "object_type": "Code",
                        "url": (
                            "https://github.com/AllenNeuralDynamics"
                            "/aind-airflow-dags"
                        ),
                        "name": "transform_and_upload_v2",
                        "version": "0.34.0",
                        "language": "Python",
                        "language_version": "3.10.19",
                        "parameters": {
                            "job_type": "default",
                        },
                    }
                ],
            },
        }

        self.assertEqual(expected_settings, gather_settings)

    def test_gather_preliminary_metadata_settings_legacy(self):
        """Tests legacy gather preliminary metadata settings."""
        job_settings = get_gather_preliminary_metadata_settings(
            image="ghcr.io/aind-metadata-mapper",
            image_version="0.28.2",
            staging_folder="stage",
            merged_job_settings={"metadata_dir": "tests"},
            subject_id="123456",
            s3_prefix="ecephys_123456_2025-10-03_20-37-40",
            acq_datetime="2025-10-03T20:37:40Z",
            project_name="Ephys Platform",
            modalities=[
                {
                    "name": "Extracellular electrophysiology",
                    "abbreviation": "ecephys",
                }
            ],
            metadata_service_domain="https://example.com",
        )
        expected_settings = {
            "directory_to_write_to": "stage",
            "metadata_dir": "tests",
            "raw_data_description_settings": {
                "name": "ecephys_123456_2025-10-03_20-37-40",
                "project_name": "Ephys Platform",
                "modality": [
                    {
                        "name": "Extracellular electrophysiology",
                        "abbreviation": "ecephys",
                    }
                ],
            },
            "subject_settings": {"subject_id": "123456"},
            "procedures_settings": {"subject_id": "123456"},
            "rig_settings": {"rig_id": ""},
            "instrument_settings": {"instrument_id": ""},
            "metadata_service_domain": "https://example.com",
        }
        self.assertEqual(expected_settings, job_settings)

    def test_gather_preliminary_metadata_settings_v1(self):
        """Tests version 1 gather preliminary metadata settings."""
        job_settings = get_gather_preliminary_metadata_settings(
            image="ghcr.io/aind-metadata-mapper",
            image_version="v1-abc",
            staging_folder="stage",
            merged_job_settings={"metadata_dir": "tests"},
            subject_id="123456",
            s3_prefix="ecephys_123456_2025-10-03_20-37-40",
            acq_datetime="2025-10-03T20:37:40Z",
            project_name="Ephys Platform",
            modalities=[
                {
                    "name": "Extracellular electrophysiology",
                    "abbreviation": "ecephys",
                }
            ],
            metadata_service_domain="https://example.com",
        )
        expected_settings = {
            "metadata_dir": "tests",
            "output_dir": "stage",
            "acquisition_start_time": "2025-10-03T20:37:40Z",
            "subject_id": "123456",
            "data_description_settings": {
                "project_name": "Ephys Platform",
                "modalities": [
                    {
                        "name": "Extracellular electrophysiology",
                        "abbreviation": "ecephys",
                    }
                ],
            },
            "metadata_service_url": "https://example.com",
        }
        self.assertEqual(expected_settings, job_settings)

    def test_gather_preliminary_metadata_settings_v1_merged(self):
        """Tests version 1 gather preliminary metadata settings
        when data_description_settings need to be merged."""
        job_settings = get_gather_preliminary_metadata_settings(
            image="ghcr.io/aind-metadata-mapper",
            image_version="v1-abc",
            staging_folder="stage",
            merged_job_settings={
                "metadata_dir": "tests",
                "data_description_settings": {
                    "tags": ["test"],
                    "data_summary": "This is a test dataset.",
                },
            },
            subject_id="123456",
            s3_prefix="ecephys_123456_2025-10-03_20-37-40",
            acq_datetime="2025-10-03T20:37:40Z",
            project_name="Ephys Platform",
            modalities=[
                {
                    "name": "Extracellular electrophysiology",
                    "abbreviation": "ecephys",
                }
            ],
            metadata_service_domain="https://example.com",
        )
        expected_settings = {
            "metadata_dir": "tests",
            "output_dir": "stage",
            "acquisition_start_time": "2025-10-03T20:37:40Z",
            "subject_id": "123456",
            "data_description_settings": {
                "project_name": "Ephys Platform",
                "modalities": [
                    {
                        "name": "Extracellular electrophysiology",
                        "abbreviation": "ecephys",
                    }
                ],
                "tags": ["test"],
                "data_summary": "This is a test dataset.",
            },
            "metadata_service_url": "https://example.com",
        }
        self.assertEqual(expected_settings, job_settings)


if __name__ == "__main__":
    unittest.main()
