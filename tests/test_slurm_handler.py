"""Tests for slurm_handler module"""

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from aind_slurm_rest.models.v0040_job_desc_msg import V0040JobDescMsg
from aind_slurm_rest.models.v0040_job_info import V0040JobInfo
from aind_slurm_rest.models.v0040_openapi_error import V0040OpenapiError
from aind_slurm_rest.models.v0040_openapi_job_info_resp import (
    V0040OpenapiJobInfoResp,
)
from aind_slurm_rest.models.v0040_openapi_job_submit_response import (
    V0040OpenapiJobSubmitResponse,
)
from aind_slurm_rest.models.v0040_uint32_no_val import V0040Uint32NoVal
from aind_slurm_rest.models.v0040_uint64_no_val import V0040Uint64NoVal

from aind_airflow_jobs.slurm_handler import (
    JobState,
    SlurmClientSettings,
    SlurmHook,
    SubmitSlurmJobArray,
    create_slurm_environment_for_task,
    read_json_file,
    read_slurm_std_err,
)

TEST_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "resources"


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    @patch("aind_airflow_jobs.slurm_handler.uuid4")
    @patch("aind_airflow_jobs.slurm_handler.datetime")
    def test_create_slurm_environment_for_task(
        self, mock_datetime: MagicMock, mock_uuid4: MagicMock
    ):
        """Tests create_slurm_environment_for_task method."""

        mock_uuid4.return_value = "b4082467-522e-411b-a714-22f62ae09014"
        mock_datetime.utcnow.return_value = datetime(2025, 4, 23, tzinfo=timezone.utc)
        job = {"s3_prefix": "ecephys_123456_2020-10-10_10-10-10"}
        task_settings = {"logs_directory": "tests"}
        output = create_slurm_environment_for_task(
            job=job, task_settings=task_settings
        )
        expected_output = {
            "name": "ecephys_123456_job_1745366400_b4082",
            "current_working_directory": ".",
            "standard_error": (
                "tests/ecephys_123456_job_1745366400_b4082_error.out"
            ),
            "standard_output": (
                "tests/ecephys_123456_job_1745366400_b4082.out"
            ),
        }
        self.assertEqual(
            expected_output, output.model_dump(mode="json", exclude_none=True)
        )

    @patch("aind_airflow_jobs.slurm_handler.uuid4")
    @patch("aind_airflow_jobs.slurm_handler.datetime")
    def test_create_slurm_environment_for_task_no_prefix(
        self, mock_datetime: MagicMock, mock_uuid4: MagicMock
    ):
        """Tests create_slurm_environment_for_task method when no s3_prefix"""

        mock_uuid4.return_value = "b4082467-522e-411b-a714-22f62ae09014"
        mock_datetime.utcnow.return_value = datetime(2025, 4, 23, tzinfo=timezone.utc)
        job = dict()
        task_settings = {"logs_directory": "tests"}
        output = create_slurm_environment_for_task(
            job=job, task_settings=task_settings, name_suffix="cf"
        )
        expected_output = {
            "name": "job_1745366400_b4082_cf",
            "current_working_directory": ".",
            "standard_error": "tests/job_1745366400_b4082_cf_error.out",
            "standard_output": "tests/job_1745366400_b4082_cf.out",
        }
        self.assertEqual(
            expected_output, output.model_dump(mode="json", exclude_none=True)
        )

    def test_read_json_file(self):
        """Tests read_json_file"""

        contents = read_json_file(
            filepath=str(TEST_DIR / "metadata.nd.json"),
            remote_mnt_dir="",
            local_mnt_dir="",
        )
        self.assertEqual({"subject": {"subject_id": 123456}}, contents)

    def test_read_slurm_std_err(self):
        """Tests read_slurm_std_err"""

        contents = read_slurm_std_err(
            filepath=str(TEST_DIR / "example_error.out"),
            remote_mnt_dir="",
            local_mnt_dir="",
        ).split("\n")
        self.assertEqual(24, len(contents))
        self.assertIn("Traceback (most recent call last):", contents[0])
        self.assertIn("ValueError: The given", contents[-1])

    def test_read_slurm_std_err_max_length(self):
        """Tests read_slurm_std_err with lower max length"""

        contents = read_slurm_std_err(
            filepath=str(TEST_DIR / "example_error.out"),
            remote_mnt_dir="",
            local_mnt_dir="",
            max_length=10,
        ).split("\n")

        self.assertEqual(10, len(contents))
        self.assertIn("...", contents[0])
        self.assertIn("ValueError: The given", contents[-1])

    def test_read_slurm_std_err_no_file(self):
        """Tests read_slurm_std_err when file cannot be opened"""

        contents = read_slurm_std_err(
            filepath=str(TEST_DIR / "example_error_no_file.out"),
            remote_mnt_dir="",
            local_mnt_dir="",
            max_length=10,
        )

        self.assertIn("Unable to open std_err:", contents)


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


class TestSlurmHook(unittest.TestCase):
    """Test methods in SlurmHook class"""

    @patch(
        "aind_airflow_jobs.slurm_handler.Connection"
        ".get_connection_from_secrets"
    )
    def test_class_construct(
        self,
        mock_connection: MagicMock,
    ):
        """Tests class constructor."""

        mock_conn = MagicMock(
            conn_type="http",
            host="example.com",
            login="user",
            extra_dejson={"token": "abc-123"},
        )
        mock_connection.return_value = mock_conn
        slurm_hook = SlurmHook()
        self.assertEqual(
            "user", slurm_hook.conn.api_client.configuration.username
        )
        self.assertEqual(
            "abc-123", slurm_hook.conn.api_client.configuration.access_token
        )


class TestSubmitSlurmJobArray(unittest.TestCase):
    """Test methods in SubmitSlurmJobArray class"""

    @classmethod
    def setUpClass(cls):
        """Sets up objects to be shared across tests."""
        slurm_client_settings = SlurmClientSettings(
            host="http://example.com", username="user", access_token="abc-123"
        )
        job_properties = V0040JobDescMsg(
            environment=[
                "PATH=/bin:/usr/bin/:/usr/local/bin/",
                "LD_LIBRARY_PATH=/lib/:/lib64/:/usr/local/lib",
            ],
            partition="some_part",
            standard_error="tests/%x_%j_error.out",
            standard_output="tests/%x_%j.out",
            qos="dev",
            name="job_123",
            current_working_directory=".",
            time_limit=V0040Uint32NoVal(set=True, number=360),
        )
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJobArray(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
            remote_mnt_dir="",
            local_mnt_dir="",
        )
        cls.slurm_job = slurm_job

    def test_default_job_properties(self):
        """Tests that default job properties are set correctly."""

        slurm_job = self.slurm_job
        self.assertEqual("some_part", slurm_job.job_properties.partition)
        self.assertEqual("dev", slurm_job.job_properties.qos)
        self.assertEqual("job_123", slurm_job.job_properties.name, "job_123")
        self.assertEqual(
            "tests/%x_%j.out", slurm_job.job_properties.standard_output
        )
        self.assertEqual(
            "tests/%x_%j_error.out", slurm_job.job_properties.standard_error
        )
        self.assertEqual(
            [
                "PATH=/bin:/usr/bin/:/usr/local/bin/",
                "LD_LIBRARY_PATH=/lib/:/lib64/:/usr/local/lib",
            ],
            slurm_job.job_properties.environment,
        )
        self.assertEqual(360, slurm_job.job_properties.time_limit.number)

    def test_check_job_status(self):
        """Tests _check_job_status method"""

        job_status = dict()

        job_response = V0040OpenapiJobInfoResp(
            jobs=[
                V0040JobInfo(
                    job_id=1,
                    job_state=[JobState.R.value],
                    submit_time=V0040Uint64NoVal(set=True, number=0),
                ),
                V0040JobInfo(
                    job_id=2,
                    job_state=[JobState.R.value],
                    submit_time=V0040Uint64NoVal(set=True, number=0),
                ),
            ],
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        job = self.slurm_job
        output = job._check_job_status(
            job_response=job_response, job_status=job_status
        )
        self.assertEqual((False, False), output)
        self.assertEqual({1: "RUNNING", 2: "RUNNING"}, job_status)

    def test_check_job_status_completed_with_errors(self):
        """Tests _check_job_status method when there was an error"""

        # previous job_status that will be updated with new info
        job_status = {1: "RUNNING", 2: "RUNNING"}

        job_response = V0040OpenapiJobInfoResp(
            jobs=[
                V0040JobInfo(
                    job_id=1,
                    job_state=[JobState.CD.value],
                    submit_time=V0040Uint64NoVal(set=True, number=0),
                ),
                V0040JobInfo(
                    job_id=2,
                    job_state=[JobState.F.value],
                    submit_time=V0040Uint64NoVal(set=True, number=0),
                ),
            ],
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        job = self.slurm_job
        output = job._check_job_status(
            job_response=job_response, job_status=job_status
        )
        self.assertEqual((True, True), output)
        self.assertEqual({1: "COMPLETED", 2: "FAILED"}, job_status)

    def test_check_job_status_when_no_response(self):
        """Tests _check_job_status method when there was an error"""

        job_status = dict()

        job_response = V0040OpenapiJobInfoResp(
            jobs=[],
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        job = self.slurm_job
        output = job._check_job_status(
            job_response=job_response, job_status=job_status
        )
        self.assertEqual((True, True), output)
        self.assertEqual(dict(), job_status)

    @patch(
        "aind_slurm_rest.api.slurm_api.SlurmApi.slurm_v0040_post_job_submit"
    )
    def test_submit_job_with_errors(self, mock_submit_job: MagicMock):
        """
        Tests that an exception is raised if there are errors in the
        SubmitJobResponse
        """

        mock_submit_job.return_value = V0040OpenapiJobSubmitResponse(
            errors=[V0040OpenapiError(error="An error occurred.")]
        )
        slurm_job = self.slurm_job
        with self.assertRaises(Exception) as e:
            slurm_job._submit_job()
        expected_errors = (
            "There were errors submitting the job to slurm:"
            " [V0040OpenapiError(description=None, error_number=None, "
            "error='An error occurred.', source=None)]"
        )
        self.assertEqual(expected_errors, e.exception.args[0])

    @patch(
        "aind_slurm_rest.api.slurm_api.SlurmApi.slurm_v0040_post_job_submit"
    )
    def test_submit_job(self, mock_submit_job: MagicMock):
        """Tests that job is submitted successfully"""

        mock_submit_job.return_value = V0040OpenapiJobSubmitResponse(
            job_id=12345
        )
        slurm_job = self.slurm_job
        response = slurm_job._submit_job()
        expected_response = V0040OpenapiJobSubmitResponse(job_id=12345)
        self.assertEqual(expected_response, response)

    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    @patch("aind_airflow_jobs.slurm_handler.sleep", return_value=None)
    @patch("logging.info")
    def test_monitor_job(
        self,
        mock_log_info: MagicMock,
        mock_sleep: MagicMock,
        mock_get_job: MagicMock,
    ):
        """Tests that job is monitored successfully"""

        submit_job_response = V0040OpenapiJobSubmitResponse(job_id=12345)

        submit_time = 1693788246
        start_time = 1693788400

        mock_get_job.side_effect = [
            V0040OpenapiJobInfoResp(
                last_backfill=V0040Uint64NoVal(),
                last_update=V0040Uint64NoVal(),
                jobs=[
                    V0040JobInfo(
                        job_id=12345,
                        job_state=[JobState.PD.value],
                        submit_time=V0040Uint64NoVal(
                            set=True, number=submit_time
                        ),
                    )
                ],
            ),
            V0040OpenapiJobInfoResp(
                last_backfill=V0040Uint64NoVal(),
                last_update=V0040Uint64NoVal(),
                jobs=[
                    V0040JobInfo(
                        job_id=12345,
                        job_state=[JobState.R.value],
                        submit_time=V0040Uint64NoVal(
                            set=True, number=submit_time
                        ),
                        start_time=V0040Uint64NoVal(
                            set=True, number=start_time
                        ),
                    )
                ],
            ),
            V0040OpenapiJobInfoResp(
                last_backfill=V0040Uint64NoVal(),
                last_update=V0040Uint64NoVal(),
                jobs=[
                    V0040JobInfo(
                        job_id=12345,
                        job_state=[JobState.CD.value],
                        submit_time=V0040Uint64NoVal(
                            set=True, number=submit_time
                        ),
                        start_time=V0040Uint64NoVal(
                            set=True, number=start_time
                        ),
                    )
                ],
            ),
        ]
        slurm_job = self.slurm_job
        slurm_job._monitor_job(submit_response=submit_job_response)

        mock_sleep.assert_has_calls([call(120), call(120)])

        mock_log_info.assert_has_calls(
            [
                call(
                    '{"job_id": 12345, "job_name": "job_123", '
                    '"job_states": ["PENDING"], "start_time": null}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "job_123", '
                    '"job_states": ["RUNNING"], "start_time": 1693788400}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "job_123", '
                    '"job_states": ["COMPLETED"], "start_time": 1693788400}'
                ),
                call("Job is Finished!"),
            ]
        )

    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    @patch("aind_airflow_jobs.slurm_handler.sleep", return_value=None)
    @patch("logging.info")
    @patch("logging.exception")
    @patch("aind_airflow_jobs.slurm_handler.read_slurm_std_err")
    def test_monitor_job_with_fail_code(
        self,
        mock_read_std_err: MagicMock,
        mock_log_exception: MagicMock,
        mock_log_info: MagicMock,
        mock_sleep: MagicMock,
        mock_get_job: MagicMock,
    ):
        """Tests that job is monitored and fails correctly"""

        mock_read_std_err.return_value = "Error"
        submit_job_response = V0040OpenapiJobSubmitResponse(job_id=12345)

        submit_time = 1693788246
        start_time = 1693788400

        mock_get_job.side_effect = [
            V0040OpenapiJobInfoResp(
                last_backfill=V0040Uint64NoVal(),
                last_update=V0040Uint64NoVal(),
                jobs=[
                    V0040JobInfo(
                        job_id=12345,
                        job_state=[JobState.R.value],
                        submit_time=V0040Uint64NoVal(
                            set=True, number=submit_time
                        ),
                    )
                ],
            ),
            V0040OpenapiJobInfoResp(
                last_backfill=V0040Uint64NoVal(),
                last_update=V0040Uint64NoVal(),
                jobs=[
                    V0040JobInfo(
                        job_id=12345,
                        job_state=[JobState.F.value],
                        submit_time=V0040Uint64NoVal(
                            set=True, number=submit_time
                        ),
                        start_time=V0040Uint64NoVal(
                            set=True, number=start_time
                        ),
                    )
                ],
            ),
        ]
        slurm_job = self.slurm_job
        with self.assertRaises(Exception) as e:
            slurm_job._monitor_job(submit_response=submit_job_response)

        expected_error_message = (
            "There were errors with the slurm job. Job: "
            '{"job_id": 12345, "job_name": "job_123",'
            ' "job_status": {"12345": "FAILED"}}.'
            " Errors: None"
        )
        self.assertEqual(expected_error_message, e.exception.args[0])

        mock_log_exception.assert_called_once_with("std_err:\nError")
        mock_sleep.assert_has_calls([call(120)])

        mock_log_info.assert_has_calls(
            [
                call(
                    '{"job_id": 12345, "job_name": "job_123", '
                    '"job_states": ["RUNNING"], "start_time": null}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "job_123", '
                    '"job_states": ["FAILED"], "start_time": 1693788400}'
                ),
            ]
        )

    def test_std_err_filepath(self):
        """Tests _std_err_filepath method"""
        slurm_job = self.slurm_job

        output_path = slurm_job._std_err_filepath(job_id=12345)
        expected_path = "tests/job_123_12345_error.out"
        self.assertEqual(expected_path, output_path)

    @patch("aind_airflow_jobs.slurm_handler.SubmitSlurmJobArray._submit_job")
    @patch("aind_airflow_jobs.slurm_handler.SubmitSlurmJobArray._monitor_job")
    @patch("logging.info")
    def test_run_job(
        self,
        mock_log: MagicMock,
        mock_monitor: MagicMock,
        mock_submit: MagicMock,
    ):
        """Tests that run_job calls right methods."""
        slurm_job = self.slurm_job

        slurm_job.run_job()
        mock_submit.assert_called()
        mock_monitor.assert_called()
        mock_log.assert_called()


if __name__ == "__main__":
    unittest.main()
