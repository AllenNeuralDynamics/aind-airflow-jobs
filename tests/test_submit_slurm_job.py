"""Tests methods in the submit_slurm_jobs module."""

import binascii
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from aind_slurm_rest import (
    V0036Error,
    V0036JobResponseProperties,
    V0036JobsResponse,
    V0036JobSubmissionResponse,
)
from aind_slurm_rest.models.v0036_job_properties import V0036JobProperties

from aind_airflow_jobs.submit_slurm_job import (
    JobState,
    SlurmClientSettings,
    SubmitSlurmJob,
)

TEST_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "resources"
EXAMPLE_SCRIPT = TEST_DIR / "test_slurm_script.txt"


class TestSubmitSlurmJob(unittest.TestCase):
    """Test methods in the SubmitSlurmJob class"""

    EXAMPLE_ENV_VAR = {
        "SLURM_CLIENT_HOST": "slurm",
        "SLURM_CLIENT_USERNAME": "username",
        "SLURM_CLIENT_PASSWORD": "password",
        "SLURM_CLIENT_ACCESS_TOKEN": "abc-123",
        "SLURM_LOG_PATH": "/a/dir/to/write/logs/to",
        "SLURM_PARTITION": "some_part",
    }

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    def test_default_job_properties(self):
        """Tests that default job properties are set correctly."""
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={})
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        self.assertEqual("some_part", slurm_job.job_properties.partition)
        self.assertEqual("dev", slurm_job.job_properties.qos)
        self.assertTrue(slurm_job.job_properties.name.startswith("job_"))
        self.assertTrue(
            slurm_job.job_properties.standard_out.startswith(
                "/a/dir/to/write/logs/to/job_"
            )
        )
        self.assertTrue(slurm_job.job_properties.standard_out.endswith(".out"))
        self.assertTrue(
            slurm_job.job_properties.standard_error.startswith(
                "/a/dir/to/write/logs/to/job_"
            )
        )
        self.assertTrue(
            slurm_job.job_properties.standard_error.endswith("_error.out")
        )
        self.assertEqual(
            {
                "PATH": "/bin:/usr/bin/:/usr/local/bin/",
                "LD_LIBRARY_PATH": "/lib/:/lib64/:/usr/local/lib",
            },
            slurm_job.job_properties.environment,
        )
        self.assertEqual(360, slurm_job.job_properties.time_limit)
        self.assertEqual(50000, slurm_job.job_properties.memory_per_node)
        self.assertEqual([1, 1], slurm_job.job_properties.nodes)
        self.assertEqual(1, slurm_job.job_properties.tasks)

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    def test_mixed_job_properties(self):
        """Tests that job properties are not overwritten."""
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(
            environment={},
            name="my_job",
            partition="part2",
            qos="prod",
            time_limit=5,
            memory_per_node=500,
        )
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        self.assertEqual("part2", slurm_job.job_properties.partition)
        self.assertEqual("prod", slurm_job.job_properties.qos)
        self.assertTrue("my_job", slurm_job.job_properties.name)
        self.assertEqual(
            "/a/dir/to/write/logs/to/my_job.out",
            slurm_job.job_properties.standard_out,
        )
        self.assertEqual(
            "/a/dir/to/write/logs/to/my_job_error.out",
            slurm_job.job_properties.standard_error,
        )
        self.assertEqual(
            {
                "PATH": "/bin:/usr/bin/:/usr/local/bin/",
                "LD_LIBRARY_PATH": "/lib/:/lib64/:/usr/local/lib",
            },
            slurm_job.job_properties.environment,
        )
        self.assertEqual(5, slurm_job.job_properties.time_limit)
        self.assertEqual(500, slurm_job.job_properties.memory_per_node)
        self.assertEqual([1, 1], slurm_job.job_properties.nodes)
        self.assertEqual(1, slurm_job.job_properties.tasks)

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurmctld_submit_job_0")
    def test_submit_job_with_errors(self, mock_submit_job: MagicMock):
        """Tests that an exception is raised if there are errors in the
        SubmitJobResponse"""

        mock_submit_job.return_value = V0036JobSubmissionResponse(
            errors=[V0036Error(error="An error occurred.")]
        )
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={})
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        with self.assertRaises(Exception) as e:
            slurm_job._submit_job()
        expected_errors = (
            "There were errors submitting the job to slurm: "
            "[V0036Error(error='An error occurred.', errno=None)]"
        )
        self.assertEqual(expected_errors, e.exception.args[0])

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurmctld_submit_job_0")
    def test_submit_job(self, mock_submit_job: MagicMock):
        """Tests that job is submitted successfully"""

        mock_submit_job.return_value = V0036JobSubmissionResponse(
            errors=[], job_id=12345
        )
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={})
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        response = slurm_job._submit_job()
        expected_response = V0036JobSubmissionResponse(errors=[], job_id=12345)
        self.assertEqual(expected_response, response)

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurmctld_get_job_0")
    @patch("aind_airflow_jobs.submit_slurm_job.sleep", return_value=None)
    @patch("logging.info")
    def test_monitor_job(
        self,
        mock_log_info: MagicMock,
        mock_sleep: MagicMock,
        mock_get_job: MagicMock,
    ):
        """Tests that job is monitored successfully"""

        submit_job_response = V0036JobSubmissionResponse(
            errors=[], job_id=12345
        )

        submit_time = 1693788246
        start_time = 1693788400

        mock_get_job.side_effect = [
            V0036JobsResponse(
                errors=[],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.PD.value, submit_time=submit_time
                    )
                ],
            ),
            V0036JobsResponse(
                errors=[],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.R.value,
                        submit_time=submit_time,
                        start_time=start_time,
                    )
                ],
            ),
            V0036JobsResponse(
                errors=[],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.CD.value,
                        submit_time=submit_time,
                        start_time=start_time,
                    )
                ],
            ),
        ]
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={}, name="mock_job")
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        slurm_job._monitor_job(submit_response=submit_job_response)

        mock_sleep.assert_has_calls([call(120), call(120)])

        mock_log_info.assert_has_calls(
            [
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "PENDING", "start_time": null}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "RUNNING", "start_time": 1693788400}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "COMPLETED", "start_time": 1693788400}'
                ),
                call("Job is Finished!"),
            ]
        )

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurmctld_get_job_0")
    @patch("aind_airflow_jobs.submit_slurm_job.sleep", return_value=None)
    @patch("logging.info")
    def test_monitor_job_with_errors(
        self,
        mock_log_info: MagicMock,
        mock_sleep: MagicMock,
        mock_get_job: MagicMock,
    ):
        """Tests that errors are raised if response has errors."""

        submit_job_response = V0036JobSubmissionResponse(
            errors=[], job_id=12345
        )

        submit_time = 1693788246

        mock_get_job.side_effect = [
            V0036JobsResponse(
                errors=[V0036Error(error="An error occurred.")],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.F.value, submit_time=submit_time
                    )
                ],
            )
        ]
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={}, name="mock_job")
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        with self.assertRaises(Exception) as e:
            slurm_job._monitor_job(submit_response=submit_job_response)

        expected_error_message = (
            "There were errors with the slurm job. Job: "
            '{"job_id": 12345, "job_name": "mock_job", "job_state": "FAILED"}.'
            " Errors: [V0036Error(error='An error occurred.', errno=None)]"
        )

        self.assertEqual(expected_error_message, e.exception.args[0])
        mock_sleep.assert_not_called()
        mock_log_info.assert_has_calls(
            [
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "FAILED", "start_time": null}'
                )
            ]
        )

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    @patch("aind_slurm_rest.api.slurm_api.SlurmApi.slurmctld_get_job_0")
    @patch("aind_airflow_jobs.submit_slurm_job.sleep", return_value=None)
    @patch("logging.info")
    def test_monitor_job_with_fail_code(
        self,
        mock_log_info: MagicMock,
        mock_sleep: MagicMock,
        mock_get_job: MagicMock,
    ):
        """Tests that errors are raised if response has an error code."""

        submit_job_response = V0036JobSubmissionResponse(
            errors=[], job_id=12345
        )

        submit_time = 1693788246
        start_time = 1693788400

        mock_get_job.side_effect = [
            V0036JobsResponse(
                errors=[],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.PD.value, submit_time=submit_time
                    )
                ],
            ),
            V0036JobsResponse(
                errors=[],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.R.value,
                        submit_time=submit_time,
                        start_time=start_time,
                    )
                ],
            ),
            V0036JobsResponse(
                errors=[],
                jobs=[
                    V0036JobResponseProperties(
                        job_state=JobState.F.value,
                        submit_time=submit_time,
                        start_time=start_time,
                    )
                ],
            ),
        ]
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={}, name="mock_job")
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )
        with self.assertRaises(Exception) as e:
            slurm_job._monitor_job(submit_response=submit_job_response)

        expected_error_message = (
            "There were errors with the slurm job. Job: "
            '{"job_id": 12345, "job_name": "mock_job", "job_state": "FAILED"}.'
            " Errors: []"
        )

        self.assertEqual(expected_error_message, e.exception.args[0])
        mock_sleep.assert_has_calls([call(120), call(120)])
        mock_log_info.assert_has_calls(
            [
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "PENDING", "start_time": null}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "RUNNING", "start_time": 1693788400}'
                ),
                call(
                    '{"job_id": 12345, "job_name": "mock_job", '
                    '"job_state": "FAILED", "start_time": 1693788400}'
                ),
            ]
        )

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    @patch("aind_airflow_jobs.submit_slurm_job.SubmitSlurmJob._submit_job")
    @patch("aind_airflow_jobs.submit_slurm_job.SubmitSlurmJob._monitor_job")
    def test_run_job(self, mock_monitor: MagicMock, mock_submit: MagicMock):
        """Tests that run_job calls right methods."""
        slurm_client_settings = SlurmClientSettings()
        job_properties = V0036JobProperties(environment={})
        script = " ".join(["#!/bin/bash", "\necho", "'Hello World?'"])
        slurm = slurm_client_settings.create_api_client()
        slurm_job = SubmitSlurmJob(
            slurm=slurm,
            script=script,
            job_properties=job_properties,
        )

        slurm_job.run_job()
        mock_submit.assert_called()
        mock_monitor.assert_called()

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    def test_from_args_script_path(self):
        """Tests that a job args can be input via the command line."""
        slurm_client_settings = SlurmClientSettings()
        slurm = slurm_client_settings.create_api_client()
        job_properties_json = V0036JobProperties(
            environment={}
        ).model_dump_json()
        sys_args = [
            "--script-path",
            str(EXAMPLE_SCRIPT),
            "--job-properties",
            job_properties_json,
        ]
        job = SubmitSlurmJob.from_args(slurm=slurm, system_args=sys_args)
        expected_script = (
            "#!/bin/bash\n"
            "echo 'Hello World?' && sleep 120 && echo 'Goodbye!'"
        )
        self.assertEqual("some_part", job.job_properties.partition)
        self.assertEqual(expected_script, job.script)

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    def test_from_args_script_encoded(self):
        """Tests that a job args can be input via the command line using an
        encoded script."""
        expected_script = (
            "#!/bin/bash\n"
            "echo 'Hello World?' && sleep 120 && echo 'Goodbye!'"
        )
        script_encoded = binascii.hexlify(expected_script.encode()).decode()
        slurm_client_settings = SlurmClientSettings()
        slurm = slurm_client_settings.create_api_client()
        job_properties_json = V0036JobProperties(
            environment={}
        ).model_dump_json()
        sys_args = [
            "--script-encoded",
            script_encoded,
            "--job-properties",
            job_properties_json,
        ]
        job = SubmitSlurmJob.from_args(slurm=slurm, system_args=sys_args)
        self.assertEqual("some_part", job.job_properties.partition)
        self.assertEqual(expected_script, job.script)

    @patch.dict(os.environ, EXAMPLE_ENV_VAR, clear=True)
    def test_from_args_error(self):
        """Tests that an error is raised if no script is set"""
        slurm_client_settings = SlurmClientSettings()
        slurm = slurm_client_settings.create_api_client()
        job_properties_json = V0036JobProperties(
            environment={}
        ).model_dump_json()
        sys_args = ["--job-properties", job_properties_json]
        with self.assertRaises(Exception) as e:
            SubmitSlurmJob.from_args(slurm=slurm, system_args=sys_args)
        self.assertEqual(
            "Either script-path or script-encoded is needed",
            e.exception.args[0],
        )


if __name__ == "__main__":
    unittest.main()
