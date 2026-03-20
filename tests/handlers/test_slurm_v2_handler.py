"""Tests for slurm_v2_handler module"""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from aind_slurm_rest_v2 import (
    V0040Job,
    V0040JobDescMsg,
    V0040JobInfo,
    V0040JobState,
    V0040JobTime,
    V0040OpenapiError,
    V0040OpenapiJobInfoResp,
    V0040OpenapiJobSubmitResponse,
    V0040OpenapiSlurmdbdJobsResp,
    V0040Uint32NoVal,
    V0040Uint64NoVal,
)
from aind_slurm_rest_v2.exceptions import NotFoundException
from airflow.providers.ssh.hooks.ssh import SSHHook

from aind_airflow_jobs.handlers.slurm_v2_handler import (
    JobState,
    SlurmClientSettings,
    SlurmHook,
    SlurmJobSensor,
    SubmitSlurmJobArray,
    check_cache_job_submit_req,
    read_slurm_std_err,
)

TEST_DIR = (
    Path(os.path.dirname(os.path.realpath(__file__))).parent / "resources"
)


class TestMethods(unittest.TestCase):
    """Test methods in the module"""

    @classmethod
    def setUpClass(cls):
        """Sets up objects to be shared across tests."""

        array_job_properties = V0040JobDescMsg(
            array="0-9",
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
        image = "ghcr.io/example-image"
        image_version = "0.0.1"
        script = (
            "#!/bin/bash \nsingularity exec "
            f"docker://{image}:{image_version} "
            "python -m example_package.example_script"
        )
        cls.array_job_properties = array_job_properties
        cls.image = image
        cls.image_version = image_version
        cls.docker_run_script = script

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

    def test_check_cache_job_submit_req(self):
        """Tests check_cache_job_submit_req method"""

        for image_type in ["docker", "oras", "shub"]:
            command_script = self.docker_run_script.replace(
                "docker", image_type
            )
            submit_req = check_cache_job_submit_req(
                command_script=command_script,
                job_properties=self.array_job_properties,
                image=self.image,
                image_version=self.image_version,
            )

            self.assertEqual(
                "#!/bin/bash \nsingularity exec "
                f"{image_type}://ghcr.io/example-image:0.0.1 "
                "echo 'Hello'",
                submit_req.script,
            )
            self.assertEqual(2000, submit_req.job.memory_per_cpu.number)
            self.assertEqual(1, submit_req.job.minimum_cpus_per_node)
            self.assertEqual(1, submit_req.job.tasks)
            self.assertEqual(10, submit_req.job.time_limit.number)
            self.assertEqual(1, submit_req.job.maximum_nodes)
            self.assertEqual(1, submit_req.job.minimum_nodes)
            self.assertIsNone(submit_req.job.array)

    def test_check_cache_job_submit_req_none(self):
        """Tests check_cache_job_submit_req method when the image
        does not need to be cached"""

        # not array job
        job_properties = self.array_job_properties.model_copy(
            deep=True, update={"array": None}
        )
        submit_req0 = check_cache_job_submit_req(
            command_script=self.docker_run_script,
            job_properties=job_properties,
            image=self.image,
            image_version=self.image_version,
        )
        # image is None
        submit_req1 = check_cache_job_submit_req(
            command_script=self.docker_run_script,
            job_properties=self.array_job_properties,
            image=None,
            image_version=self.image_version,
        )
        # image_version is None
        submit_req2 = check_cache_job_submit_req(
            command_script=self.docker_run_script,
            job_properties=self.array_job_properties,
            image=self.image,
            image_version=None,
        )
        # not docker, oras, or shub image
        submit_req3 = check_cache_job_submit_req(
            command_script=" ".join(["#!/bin/bash", "\necho 'Hello World?'"]),
            job_properties=self.array_job_properties,
            image=self.image,
            image_version=self.image_version,
        )

        self.assertIsNone(submit_req0)
        self.assertIsNone(submit_req1)
        self.assertIsNone(submit_req2)
        self.assertIsNone(submit_req3)


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
        "aind_airflow_jobs.handlers.slurm_v2_handler.Connection"
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
            "http://example.com", slurm_hook.conn.api_client.configuration.host
        )
        self.assertEqual(
            "user", slurm_hook.conn.api_client.configuration.username
        )
        self.assertEqual(
            "abc-123", slurm_hook.conn.api_client.configuration.access_token
        )

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.Connection"
        ".get_connection_from_secrets"
    )
    def test_class_construct_custom_host(
        self,
        mock_connection: MagicMock,
    ):
        """Tests class constructor."""
        mock_conn = MagicMock(
            conn_type="http",
            host="something",
            login="user",
            extra_dejson={"token": "abc-123"},
        )
        mock_connection.return_value = mock_conn

        slurm_hook = SlurmHook(host="http://example.com")
        self.assertEqual(
            "http://example.com", slurm_hook.conn.api_client.configuration.host
        )
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
            retry_count=1,
            ssh_conn_id="hpc2/uri",
        )

        running_jobs = [
            V0040JobInfo(
                job_id=1,
                job_state=[JobState.R.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
            ),
            V0040JobInfo(
                job_id=2,
                job_state=[JobState.R.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
                array_job_id=V0040Uint32NoVal(set=True, number=2),
                array_task_id=V0040Uint32NoVal(set=True, number=1),
            ),
        ]
        jobs_to_retry = [
            V0040JobInfo(
                job_id=3,
                job_state=[JobState.F.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
            ),
            V0040JobInfo(
                job_id=4,
                job_state=[JobState.TO.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
            ),
        ]
        completed_jobs = [
            V0040JobInfo(
                job_id=5,
                job_state=[JobState.CD.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
                start_time=V0040Uint64NoVal(set=True, number=1),
                end_time=V0040Uint64NoVal(set=True, number=10),
            ),
        ]

        cls.slurm_job = slurm_job
        cls.running_jobs = running_jobs
        cls.jobs_to_retry = jobs_to_retry
        cls.completed_jobs = completed_jobs

    def test_class_construct(self):
        """Tests class constructor and that default job properties are
        set correctly."""

        slurm_job = self.slurm_job

        self.assertEqual(
            "#!/bin/bash \necho 'Hello World?'",
            slurm_job.script,
        )
        self.assertEqual("", slurm_job.remote_mnt_dir)
        self.assertEqual("", slurm_job.local_mnt_dir)
        self.assertEqual(120, slurm_job.polling_request_sleep)
        self.assertEqual(1, slurm_job.retry_count)
        self.assertEqual("hpc2/uri", slurm_job.ssh_conn_id)

        job_properties = slurm_job.job_properties
        self.assertEqual("some_part", job_properties.partition)
        self.assertEqual("dev", job_properties.qos)
        self.assertEqual("job_123", job_properties.name, "job_123")
        self.assertEqual("tests/%x_%j.out", job_properties.standard_output)
        self.assertEqual(
            "tests/%x_%j_error.out", job_properties.standard_error
        )
        self.assertEqual(
            [
                "PATH=/bin:/usr/bin/:/usr/local/bin/",
                "LD_LIBRARY_PATH=/lib/:/lib64/:/usr/local/lib",
            ],
            job_properties.environment,
        )
        self.assertEqual(360, job_properties.time_limit.number)
        self.assertEqual(".", job_properties.current_working_directory)

    def test_get_job_array_job_id(self):
        """Tests _get_job_array_job_id method"""

        job_id = SubmitSlurmJobArray._get_job_array_job_id(
            job=self.running_jobs[0]
        )
        self.assertEqual("1", job_id)

        job_id = SubmitSlurmJobArray._get_job_array_job_id(
            job=self.running_jobs[1]
        )
        self.assertEqual("2_1", job_id)

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.sleep")
    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.get_hpc_hook")
    def test_requeue_failed_jobs(
        self,
        mock_get_hpc_hook: MagicMock,
        mock_sleep: MagicMock,
    ):
        """Tests _requeue_failed_jobs method"""

        mock_hpc_hook = MagicMock(spec=SSHHook)
        mock_hpc_hook.exec_ssh_client_command.return_value = (
            0,
            "Requeued job 4",
            "",
        )
        mock_ssh_client = MagicMock()
        mock_hpc_hook.get_conn.return_value.__enter__.return_value = (
            mock_ssh_client
        )
        mock_get_hpc_hook.return_value = mock_hpc_hook

        with self.assertLogs(level="WARNING") as captured:
            result = self.slurm_job._requeue_failed_jobs(
                job_list=self.jobs_to_retry[0:1]
            )

        self.assertTrue(result)
        mock_get_hpc_hook.assert_called_once_with(self.slurm_job.ssh_conn_id)
        mock_sleep.assert_called_once_with(1)
        mock_hpc_hook.exec_ssh_client_command.assert_called_once_with(
            ssh_client=mock_ssh_client,
            command="scontrol requeue 3",
            get_pty=False,
            environment=dict(),
            timeout=60,
        )
        self.assertEqual(
            [
                "WARNING:root:Restarting ['FAILED'] job: 3. Restart count: 0",
            ],
            captured.output,
        )

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.sleep")
    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.get_hpc_hook")
    def test_requeue_failed_jobs_error(
        self,
        mock_get_hpc_hook: MagicMock,
        mock_sleep: MagicMock,
    ):
        """Tests _requeue_failed_jobs method when there is an error
        requeuing the job"""

        mock_hpc_hook = MagicMock(spec=SSHHook)
        mock_hpc_hook.exec_ssh_client_command.return_value = (
            4,
            "",
            "Error requeuing job",
        )
        mock_ssh_client = MagicMock()
        mock_hpc_hook.get_conn.return_value.__enter__.return_value = (
            mock_ssh_client
        )
        mock_get_hpc_hook.return_value = mock_hpc_hook

        with self.assertRaises(Exception) as e:
            with self.assertLogs(level="WARNING") as captured:
                self.slurm_job._requeue_failed_jobs(
                    job_list=self.jobs_to_retry[1:2]
                )

        self.assertEqual(
            "There was an error with job requeue! Error requeuing job",
            e.exception.args[0],
        )
        mock_get_hpc_hook.assert_called_once_with(self.slurm_job.ssh_conn_id)
        mock_sleep.assert_called_once_with(1)
        mock_hpc_hook.exec_ssh_client_command.assert_called_once_with(
            ssh_client=mock_ssh_client,
            command="scontrol requeue 4",
            get_pty=False,
            environment=dict(),
            timeout=60,
        )
        self.assertEqual(
            [
                "WARNING:root:Restarting ['TIMEOUT'] job: 4. Restart count: 0",
            ],
            captured.output,
        )

    def test_requeue_failed_jobs_none(self):
        """Tests _requeue_failed_jobs method when there are no jobs to retry"""

        result = self.slurm_job._requeue_failed_jobs(
            job_list=self.running_jobs
        )
        self.assertFalse(result)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SubmitSlurmJobArray"
        "._requeue_failed_jobs"
    )
    def test_check_job_status(self, mock_requeue: MagicMock):
        """Tests _check_job_status method"""

        mock_requeue.return_value = False
        job_status = dict()

        job_response = V0040OpenapiJobInfoResp(
            jobs=self.running_jobs,
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        output = self.slurm_job._check_job_status(
            job_response=job_response, job_status=job_status
        )
        self.assertEqual((False, False), output)
        self.assertEqual({1: "RUNNING", 2: "RUNNING"}, job_status)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SubmitSlurmJobArray"
        "._requeue_failed_jobs"
    )
    def test_check_job_status_completed_with_errors(
        self, mock_requeue: MagicMock
    ):
        """Tests _check_job_status method when there was an error"""

        mock_requeue.return_value = False

        # previous job_status that will be updated with new info
        job_status = {4: "RUNNING", 5: "RUNNING"}
        jobs = [self.jobs_to_retry[-1]] + self.completed_jobs

        job_response = V0040OpenapiJobInfoResp(
            jobs=jobs,
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        output = self.slurm_job._check_job_status(
            job_response=job_response, job_status=job_status
        )
        self.assertEqual((True, True), output)
        self.assertEqual({4: "TIMEOUT", 5: "COMPLETED"}, job_status)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SubmitSlurmJobArray"
        "._requeue_failed_jobs"
    )
    def test_check_job_status_when_no_response(self, mock_requeue: MagicMock):
        """Tests _check_job_status method when there was an error"""

        mock_requeue.return_value = False
        job_status = dict()

        job_response = V0040OpenapiJobInfoResp(
            jobs=[],
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        output = self.slurm_job._check_job_status(
            job_response=job_response, job_status=job_status
        )
        self.assertEqual((True, True), output)
        self.assertEqual(dict(), job_status)

    @patch(
        "aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_post_job_submit"
    )
    def test_submit_job_with_errors(self, mock_submit_job: MagicMock):
        """
        Tests that an exception is raised if there are errors in the
        SubmitJobResponse
        """

        mock_submit_job.return_value = V0040OpenapiJobSubmitResponse(
            errors=[V0040OpenapiError(error="An error occurred.")]
        )
        with self.assertRaises(Exception) as e:
            self.slurm_job._submit_job()
        expected_errors = (
            "There were errors submitting the job to slurm:"
            " [V0040OpenapiError(description=None, error_number=None, "
            "error='An error occurred.', source=None)]"
        )
        self.assertEqual(expected_errors, e.exception.args[0])

    @patch(
        "aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_post_job_submit"
    )
    def test_submit_job(self, mock_submit_job: MagicMock):
        """Tests that job is submitted successfully"""

        mock_submit_job.return_value = V0040OpenapiJobSubmitResponse(
            job_id=12345
        )
        response = self.slurm_job._submit_job()
        expected_response = V0040OpenapiJobSubmitResponse(job_id=12345)
        self.assertEqual(expected_response, response)

    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.sleep", return_value=None
    )
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
        end_time = 1693789000

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
                        end_time=V0040Uint64NoVal(set=True, number=end_time),
                    )
                ],
            ),
        ]
        result = self.slurm_job._monitor_job(
            submit_response=submit_job_response
        )

        self.assertEqual((start_time, end_time), result)
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

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SubmitSlurmJobArray"
        "._check_job_status"
    )
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.sleep", return_value=None
    )
    @patch("logging.info")
    @patch("logging.exception")
    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.read_slurm_std_err")
    def test_monitor_job_with_fail_code(
        self,
        mock_read_std_err: MagicMock,
        mock_log_exception: MagicMock,
        mock_log_info: MagicMock,
        mock_sleep: MagicMock,
        mock_get_job: MagicMock,
        mock_check_job_status: MagicMock,
    ):
        """Tests that job is monitored and fails correctly"""

        # side effect to retry job once
        call_count = [0]

        def check_job_status_side_effect(job_response, job_status):
            """Side effect to simulate job status changes on multiple calls"""
            job_status[12345] = "FAILED"
            call_count[0] += 1
            if call_count[0] == 1:
                return False, True
            else:
                return True, True

        mock_check_job_status.side_effect = check_job_status_side_effect

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
                errors=[V0040OpenapiError(error="An error occurred.")],
            ),
        ]
        with self.assertRaises(Exception) as e:
            self.slurm_job._monitor_job(submit_response=submit_job_response)

        expected_error_message = (
            "There were errors with the slurm job. Job: "
            '{"job_id": 12345, "job_name": "job_123",'
            ' "job_status": {"12345": "FAILED"}}.'
            " Errors: [V0040OpenapiError(description=None, error_number=None, "
            "error='An error occurred.', source=None)]"
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

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.SlurmdbApi")
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    def test_monitor_job_slurm_db(
        self,
        mock_get_job: MagicMock,
        mock_slurmdb_api: MagicMock,
    ):
        """Tests that job can be monitored using the database"""

        submit_job_response = V0040OpenapiJobSubmitResponse(job_id=12345)

        start_time = 1693788400
        end_time = 1693789000

        mock_get_job.side_effect = NotFoundException(status=404)
        mock_slurmdb_api.return_value.slurmdb_v0040_get_job.return_value = (
            V0040OpenapiSlurmdbdJobsResp(
                jobs=[
                    V0040Job(
                        job_id=12345,
                        state=V0040JobState(current=[JobState.CD.value]),
                        time=V0040JobTime(start=start_time, end=end_time),
                    )
                ]
            )
        )

        with self.assertLogs(level="WARNING") as captured:
            result = self.slurm_job._monitor_job(
                submit_response=submit_job_response
            )
        self.assertEqual((start_time, end_time), result)
        self.assertEqual(
            ["WARNING:root:Looking for job info in database..."],
            captured.output,
        )

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.SlurmdbApi")
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    def test_monitor_job_slurm_db_error(
        self,
        mock_get_job: MagicMock,
        mock_slurmdb_api: MagicMock,
    ):
        """Tests that a failed job can be monitored using the database"""

        submit_job_response = V0040OpenapiJobSubmitResponse(job_id=12345)

        mock_get_job.side_effect = NotFoundException(status=404)
        mock_slurmdb_api.return_value.slurmdb_v0040_get_job.return_value = (
            V0040OpenapiSlurmdbdJobsResp(
                jobs=[
                    V0040Job(
                        job_id=12345,
                        state=V0040JobState(current=[JobState.F.value]),
                    )
                ]
            )
        )

        with self.assertRaises(Exception) as e:
            with self.assertLogs(level="WARNING") as captured:
                self.slurm_job._monitor_job(
                    submit_response=submit_job_response
                )

        self.assertEqual(
            (
                "There was an issue with the Slurm job: 12345, "
                "current=['FAILED'] reason=None"
            ),
            e.exception.args[0],
        )
        self.assertEqual(
            ["WARNING:root:Looking for job info in database..."],
            captured.output,
        )

    def test_std_err_filepath(self):
        """Tests _std_err_filepath method"""

        output_path = self.slurm_job._std_err_filepath(job_id=12345)
        expected_path = "tests/job_123_12345_error.out"
        self.assertEqual(expected_path, output_path)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SubmitSlurmJobArray"
        "._submit_job"
    )
    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SubmitSlurmJobArray"
        "._monitor_job"
    )
    @patch("logging.info")
    def test_run_job(
        self,
        mock_log: MagicMock,
        mock_monitor: MagicMock,
        mock_submit: MagicMock,
    ):
        """Tests that run_job calls right methods."""

        self.slurm_job.run_job()
        mock_submit.assert_called()
        mock_monitor.assert_called()
        mock_log.assert_called()


class TestSlurmJobSensor(unittest.TestCase):
    """Test methods in SlurmJobSensor class"""

    @classmethod
    def setUpClass(cls) -> None:
        """Sets up objects to be shared across tests."""
        slurm_client_settings = SlurmClientSettings(
            host="http://example.com", username="user", access_token="abc-123"
        )
        slurm = slurm_client_settings.create_api_client()
        slurm_job_sensor = SlurmJobSensor(
            job_id=12345,
            slurm=slurm,
            retry_count=1,
            ssh_conn_id="hpc2/uri",
            std_err_filepath="tests/job_123_12345_error.out",
        )
        running_jobs = [
            V0040JobInfo(
                job_id=1,
                job_state=[JobState.R.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
            ),
            V0040JobInfo(
                job_id=2,
                job_state=[JobState.R.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
                array_job_id=V0040Uint32NoVal(set=True, number=2),
                array_task_id=V0040Uint32NoVal(set=True, number=1),
            ),
        ]
        jobs_to_retry = [
            V0040JobInfo(
                job_id=3,
                job_state=[JobState.F.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
                start_time=V0040Uint64NoVal(set=True, number=1),
                end_time=V0040Uint64NoVal(set=True, number=3),
            ),
            V0040JobInfo(
                job_id=4,
                job_state=[JobState.TO.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
                start_time=V0040Uint64NoVal(set=True, number=2),
                end_time=V0040Uint64NoVal(set=True, number=12),
            ),
        ]
        completed_jobs = [
            V0040JobInfo(
                job_id=5,
                job_state=[JobState.CD.value],
                submit_time=V0040Uint64NoVal(set=True, number=0),
                start_time=V0040Uint64NoVal(set=True, number=1),
                end_time=V0040Uint64NoVal(set=True, number=10),
            ),
        ]

        cls.slurm_job_sensor = slurm_job_sensor
        cls.running_jobs = running_jobs
        cls.jobs_to_retry = jobs_to_retry
        cls.completed_jobs = completed_jobs

    def test_class_construct(self):
        """Tests class constructor."""
        slurm_job_sensor = self.slurm_job_sensor
        self.assertEqual(12345, slurm_job_sensor.job_id)
        self.assertEqual(1, slurm_job_sensor.retry_count)
        self.assertEqual("hpc2/uri", slurm_job_sensor.ssh_conn_id)
        self.assertEqual(
            "tests/job_123_12345_error.out", slurm_job_sensor.std_err_filepath
        )
        self.assertEqual("/allen/aind/", slurm_job_sensor.remote_mnt_dir)
        self.assertEqual("/data/", slurm_job_sensor.local_mnt_dir)

    def test_get_job_array_job_id(self):
        """Tests _get_job_array_job_id method"""

        job_id = SlurmJobSensor._get_job_array_job_id(job=self.running_jobs[0])
        self.assertEqual("1", job_id)

        job_id = SlurmJobSensor._get_job_array_job_id(job=self.running_jobs[1])
        self.assertEqual("2_1", job_id)

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.sleep")
    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.get_hpc_hook")
    def test_requeue_failed_jobs(
        self,
        mock_get_hpc_hook: MagicMock,
        mock_sleep: MagicMock,
    ):
        """Tests _requeue_failed_jobs method"""

        mock_hpc_hook = MagicMock(spec=SSHHook)
        mock_hpc_hook.exec_ssh_client_command.return_value = (
            0,
            "Requeued job 4",
            "",
        )
        mock_ssh_client = MagicMock()
        mock_hpc_hook.get_conn.return_value.__enter__.return_value = (
            mock_ssh_client
        )
        mock_get_hpc_hook.return_value = mock_hpc_hook

        with self.assertLogs(level="WARNING") as captured:
            result = self.slurm_job_sensor._requeue_failed_jobs(
                job_list=self.jobs_to_retry[0:1]
            )

        self.assertTrue(result)
        mock_get_hpc_hook.assert_called_once_with(
            self.slurm_job_sensor.ssh_conn_id
        )
        mock_sleep.assert_called_once_with(1)
        mock_hpc_hook.exec_ssh_client_command.assert_called_once_with(
            ssh_client=mock_ssh_client,
            command="scontrol requeue 3",
            get_pty=False,
            environment=dict(),
            timeout=60,
        )
        self.assertEqual(
            [
                "WARNING:root:Restarting ['FAILED'] job: 3. Restart count: 0",
            ],
            captured.output,
        )

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.sleep")
    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.get_hpc_hook")
    def test_requeue_failed_jobs_error(
        self,
        mock_get_hpc_hook: MagicMock,
        mock_sleep: MagicMock,
    ):
        """Tests _requeue_failed_jobs method when there is an error
        requeuing the job"""

        mock_hpc_hook = MagicMock(spec=SSHHook)
        mock_hpc_hook.exec_ssh_client_command.return_value = (
            4,
            "",
            "Error requeuing job",
        )
        mock_ssh_client = MagicMock()
        mock_hpc_hook.get_conn.return_value.__enter__.return_value = (
            mock_ssh_client
        )
        mock_get_hpc_hook.return_value = mock_hpc_hook

        with self.assertRaises(Exception) as e:
            with self.assertLogs(level="WARNING") as captured:
                self.slurm_job_sensor._requeue_failed_jobs(
                    job_list=self.jobs_to_retry[1:2]
                )

        self.assertEqual(
            "There was an error with job requeue! Error requeuing job",
            e.exception.args[0],
        )
        mock_get_hpc_hook.assert_called_once_with(
            self.slurm_job_sensor.ssh_conn_id
        )
        mock_sleep.assert_called_once_with(1)
        mock_hpc_hook.exec_ssh_client_command.assert_called_once_with(
            ssh_client=mock_ssh_client,
            command="scontrol requeue 4",
            get_pty=False,
            environment=dict(),
            timeout=60,
        )
        self.assertEqual(
            [
                "WARNING:root:Restarting ['TIMEOUT'] job: 4. Restart count: 0",
            ],
            captured.output,
        )

    def test_requeue_failed_jobs_none(self):
        """Tests _requeue_failed_jobs method when there are no jobs to retry"""

        result = self.slurm_job_sensor._requeue_failed_jobs(
            job_list=self.running_jobs
        )
        self.assertFalse(result)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SlurmJobSensor"
        "._requeue_failed_jobs"
    )
    def test_check_job_status(self, mock_requeue: MagicMock):
        """Tests _check_job_status method"""

        mock_requeue.return_value = False

        job_response = V0040OpenapiJobInfoResp(
            jobs=self.completed_jobs,
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        output = self.slurm_job_sensor._check_job_status(
            job_response=job_response
        )
        self.assertEqual((True, False, 1, 10), output)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SlurmJobSensor"
        "._requeue_failed_jobs"
    )
    def test_check_job_status_completed_with_errors(
        self, mock_requeue: MagicMock
    ):
        """Tests _check_job_status method when there was an error"""

        mock_requeue.return_value = False

        jobs = [self.jobs_to_retry[-1]] + self.completed_jobs
        job_response = V0040OpenapiJobInfoResp(
            jobs=jobs,
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        output = self.slurm_job_sensor._check_job_status(
            job_response=job_response
        )
        self.assertEqual((True, True, 1, 12), output)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SlurmJobSensor"
        "._requeue_failed_jobs"
    )
    def test_check_job_status_when_no_response(self, mock_requeue: MagicMock):
        """Tests _check_job_status method when there was an error"""

        mock_requeue.return_value = False

        job_response = V0040OpenapiJobInfoResp(
            jobs=[],
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )

        output = self.slurm_job_sensor._check_job_status(
            job_response=job_response
        )
        self.assertEqual((True, True, None, None), output)

    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SlurmJobSensor"
        "._check_job_status"
    )
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    def test_get_job_status(
        self,
        mock_get_job: MagicMock,
        mock_check_job_status: MagicMock,
    ):
        """Tests get_job_status method when job is completed successfully"""

        mock_get_job.return_value = V0040OpenapiJobInfoResp(
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
            jobs=self.completed_jobs,
        )
        mock_check_job_status.return_value = (True, False, 1, 10)
        result = self.slurm_job_sensor.get_job_status()

        self.assertEqual((True, 1, 10), result)

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.read_slurm_std_err")
    @patch(
        "aind_airflow_jobs.handlers.slurm_v2_handler.SlurmJobSensor"
        "._check_job_status"
    )
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    def test_get_job_status_error(
        self,
        mock_get_job: MagicMock,
        mock_check_job_status: MagicMock,
        mock_read_std_err: MagicMock,
    ):
        """Tests get_job_status method when job has an error"""

        mock_get_job.return_value = V0040OpenapiJobInfoResp(
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
            jobs=self.jobs_to_retry[:1],
            errors=[V0040OpenapiError(error="An error occurred.")],
        )
        mock_check_job_status.return_value = (True, True, 1, 10)
        mock_read_std_err.return_value = "Error"

        with self.assertRaises(Exception) as e:
            with self.assertLogs(level="ERROR") as captured:
                self.slurm_job_sensor.get_job_status()

        expected_error_message = (
            "There were errors with the slurm job. Job: 12345. "
            "Errors: [V0040OpenapiError(description=None, error_number=None, "
            "error='An error occurred.', source=None)]"
        )
        self.assertEqual(expected_error_message, e.exception.args[0])
        self.assertEqual(
            ["ERROR:root:std_err:\nError\nNoneType: None"], captured.output
        )

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.SlurmdbApi")
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    def test_get_job_status_slurm_db(
        self,
        mock_get_job: MagicMock,
        mock_slurmdb_api: MagicMock,
    ):
        """Tests that job status can be retrieved from the slurm database"""

        start_time = 1693788400
        end_time = 1693789000

        mock_get_job.side_effect = NotFoundException(status=404)
        mock_slurmdb_api.return_value.slurmdb_v0040_get_job.return_value = (
            V0040OpenapiSlurmdbdJobsResp(
                jobs=[
                    V0040Job(
                        job_id=12345,
                        state=V0040JobState(current=[JobState.CD.value]),
                        time=V0040JobTime(start=start_time, end=end_time),
                    )
                ]
            )
        )

        with self.assertLogs(level="WARNING") as captured:
            result = self.slurm_job_sensor.get_job_status()
        self.assertEqual((True, start_time, end_time), result)
        self.assertEqual(
            ["WARNING:root:Looking for job info in database..."],
            captured.output,
        )

    @patch("aind_airflow_jobs.handlers.slurm_v2_handler.SlurmdbApi")
    @patch("aind_slurm_rest_v2.api.slurm_api.SlurmApi.slurm_v0040_get_job")
    def test_monitor_job_slurm_db_error(
        self,
        mock_get_job: MagicMock,
        mock_slurmdb_api: MagicMock,
    ):
        """Tests that a failed job can be retrieved from the slurm database"""

        mock_get_job.side_effect = NotFoundException(status=404)
        mock_slurmdb_api.return_value.slurmdb_v0040_get_job.return_value = (
            V0040OpenapiSlurmdbdJobsResp(
                jobs=[
                    V0040Job(
                        job_id=12345,
                        state=V0040JobState(current=[JobState.F.value]),
                    )
                ]
            )
        )

        with self.assertRaises(Exception) as e:
            with self.assertLogs(level="WARNING") as captured:
                self.slurm_job_sensor.get_job_status()

        self.assertEqual(
            "There was an issue with the Slurm job: 12345, ['FAILED']",
            e.exception.args[0],
        )
        self.assertEqual(
            ["WARNING:root:Looking for job info in database..."],
            captured.output,
        )


if __name__ == "__main__":
    unittest.main()
