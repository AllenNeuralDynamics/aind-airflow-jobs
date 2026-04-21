"""Module to handle sending requests to HPC"""

import json
import logging
import re
from collections import deque
from enum import Enum
from functools import reduce
from os.path import isfile
from time import sleep
from typing import Dict, List, Optional, Tuple, Union

from aind_slurm_rest_v2 import (
    V0040JobDescMsg,
    V0040JobInfo,
    V0040JobSubmitReq,
    V0040OpenapiJobInfoResp,
    V0040OpenapiJobSubmitResponse,
    V0040Uint32NoVal,
    V0040Uint64NoVal,
)
from aind_slurm_rest_v2.api.slurm_api import SlurmApi
from aind_slurm_rest_v2.api.slurmdb_api import SlurmdbApi
from aind_slurm_rest_v2.exceptions import NotFoundException
from airflow.hooks.base import BaseHook
from airflow.models import Connection

from aind_airflow_jobs.handlers.hpc_handler import get_hpc_hook
from aind_airflow_jobs.models import SlurmClientSettings


def read_slurm_std_err(
    filepath: str,
    remote_mnt_dir: str,
    local_mnt_dir: str,
    max_length: int = 200,
) -> str:
    """Reads the last lines of a std_err file"""

    d = deque(maxlen=max_length)
    mounted_path = filepath.replace(remote_mnt_dir, local_mnt_dir, 1)
    traceback_regex = (
        r"Traceback \(most recent call last\):\n(.*?)(?=\n\w+:|$)"
    )
    if not isfile(mounted_path):
        return f"Unable to open std_err: {filepath}"
    else:
        with open(mounted_path, "r") as f:
            for line in f:
                d.appendleft(line)
        trace_back = []
        for line in d:
            trace_back.insert(0, line)
            if re.match(traceback_regex, line):
                break

        if len(trace_back) == max_length:
            trace_back.insert(0, "...")
        msg = "".join(trace_back)
        return msg


def check_cache_job_submit_req(
    command_script: str,
    job_properties: V0040JobDescMsg,
    image: Optional[str] = None,
    image_version: Optional[str] = None,
) -> Optional[V0040JobSubmitReq]:
    """
    Generate a simple command script that can be used to cache an image to
    avoid parallel jobs from caching the same docker image and raising
    errors.
    """
    if (
        job_properties.array is None
        or image is None
        or image_version is None
        or (
            "docker://" not in command_script
            and "oras://" not in command_script
            and "shub://" not in command_script
        )
    ):
        return None
    updated_settings = {
        "memory_per_cpu": V0040Uint64NoVal(set=True, number=2000),
        "minimum_cpus_per_node": 1,
        "tasks": 1,
        "time_limit": V0040Uint32NoVal(set=True, number=10),
        "maximum_nodes": 1,
        "minimum_nodes": 1,
        "array": None,
    }
    new_job_props = job_properties.model_copy(
        deep=True, update=updated_settings
    )
    if "docker://" in command_script:
        new_command_script = (
            f"#!/bin/bash \nsingularity exec "
            f"docker://{image}:{image_version} echo 'Hello'"
        )
    elif "oras://" in command_script:
        new_command_script = (
            f"#!/bin/bash \nsingularity exec "
            f"oras://{image}:{image_version} echo 'Hello'"
        )
    else:
        new_command_script = (
            f"#!/bin/bash \nsingularity exec "
            f"shub://{image}:{image_version} echo 'Hello'"
        )
    new_job_submit_request = V0040JobSubmitReq(
        script=new_command_script, job=new_job_props
    )
    return new_job_submit_request


class JobState(str, Enum):
    """
    The possible job_state values in the V0040OpenapiJobInfoResp class. The
    enums don't appear to be importable from the aind-slurm-rest api.
    """

    # Job terminated due to launch failure, typically due to a hardware failure
    # (e.g. unable to boot the node or block and the job can not be
    # requeued).
    BF = "BOOT_FAIL"

    # Job was explicitly cancelled by the user or system administrator. The job
    # may or may not have been initiated.
    CA = "CANCELLED"

    # Job has terminated all processes on all nodes with an exit code of zero.
    CD = "COMPLETED"

    # Job has been allocated resources, but are waiting for them to become
    # ready for use (e.g. booting).
    CF = "CONFIGURING"

    # Job is in the process of completing. Some processes on some nodes may
    # still be active.
    CG = "COMPLETING"

    # Job terminated on deadline.
    DL = "DEADLINE"

    # Job terminated with non-zero exit code or other failure condition.
    F = "FAILED"

    # Failed to launch on the chosen node(s); includes prolog failure and
    # other failure conditions
    LF = "LAUNCH_FAILED"

    # Job terminated due to failure of one or more allocated nodes.
    NF = "NODE_FAIL"

    # Job experienced out of memory error.
    OOM = "OUT_OF_MEMORY"

    # Job is awaiting resource allocation.
    PD = "PENDING"

    # Job has been allocated powered down nodes and is waiting for them to boot
    PO = "POWER_UP_NODE"

    # Job terminated due to preemption.
    PR = "PREEMPTED"

    # Job currently has an allocation.
    R = "RUNNING"

    # Job is being held after requested reservation was deleted.
    RD = "RESV_DEL_HOLD"

    # Node configuration for job failed
    RE = "RECONFIG_FAIL"

    # Job is being requeued by a federation.
    RF = "REQUEUE_FED"

    # Held job is being requeued.
    RH = "REQUEUE_HOLD"

    # Completing job is being requeued.
    RQ = "REQUEUED"

    # Job is about to change size.
    RS = "RESIZING"

    # Sibling was removed from cluster due to other cluster starting the job.
    RV = "REVOKED"

    # Job is being signaled.
    SI = "SIGNALING"

    # The job was requeued in a special state. This state can be set by users,
    # typically in EpilogSlurmctld, if the job has terminated with a particular
    # exit value.
    SE = "SPECIAL_EXIT"

    # Staging out data
    SO = "STAGE_OUT"

    # Job has an allocation, but execution has been stopped with SIGSTOP
    # signal. CPUS have been retained by this job.
    ST = "STOPPED"

    # Job has an allocation, but execution has been suspended and CPUs have
    # been released for other jobs.
    S = "SUSPENDED"

    # Job terminated upon reaching its time limit.
    TO = "TIMEOUT"

    # Update db
    UD = "UPDATE_DB"

    FINISHED_CODES = [
        BF,
        CA,
        CD,
        DL,
        F,
        NF,
        OOM,
        PR,
        RE,
        RV,
        SE,
        ST,
        S,
        TO,
    ]

    ERROR_CODES = [BF, CA, DL, F, NF, OOM, PR, RE, RV, SE, ST, S, TO]
    STATES_TO_RETRY = [F, TO]


class SlurmHook(BaseHook):
    """Hook to interface with Slurm REST API."""

    def __init__(
        self, conn_id: str = "slurm2/uri", host: Optional[str] = None
    ):
        """Class constructor"""
        super().__init__()
        self.conn_id = conn_id
        self.host = host
        self.conn = self.get_conn()

    def get_conn(self) -> SlurmApi:
        """
        Get connection to Slurm.

        Returns
        -------
        SlurmApi

        """
        slurm_conn = Connection.get_connection_from_secrets(self.conn_id)
        if self.host is None:
            slurm_host = f"{slurm_conn.conn_type}://{slurm_conn.host}"
        else:
            slurm_host = self.host
        slurm_client_settings = SlurmClientSettings(
            host=slurm_host,
            username=slurm_conn.login,
            access_token=slurm_conn.extra_dejson["token"],
        )
        return slurm_client_settings.create_api_client()


class SubmitSlurmJobArray:
    """Main class to handle submitting and monitoring a slurm job"""

    def __init__(
        self,
        slurm: SlurmApi,
        job_properties: V0040JobDescMsg,
        script: str,
        remote_mnt_dir: str = "/allen/aind/",
        local_mnt_dir: str = "/data/",
        poll_job_interval: int = 120,
        retry_count: int = 0,
        ssh_conn_id: Optional[str] = None,
    ):
        """
        Class constructor
        Parameters
        ----------
        slurm : SlurmApi
        job_properties : V0040JobDescMsg
        script : str
        remote_mnt_dir: str
           Location of logging directory mount. Default is /allen/aind/.
        local_mnt_dir: str
           Local location of logging directory. Default is /data/.
        poll_job_interval : int
           Number of seconds to wait before checking slurm job status.
           Default is 120.
        retry_count : int
           Number of times to requeue a job marked as FAILED or TIMEOUT.
           Default is 0.
        ssh_conn_id : str | None
           If retries are requested, then this needs to be set to send request
           over ssh.
        """
        self.slurm = slurm
        self.job_properties = job_properties
        self.script = script
        self.remote_mnt_dir = remote_mnt_dir
        self.local_mnt_dir = local_mnt_dir
        self.polling_request_sleep = poll_job_interval
        self.retry_count = retry_count
        self.ssh_conn_id = ssh_conn_id

    @staticmethod
    def _get_job_array_job_id(job: V0040JobInfo) -> str:
        """Get job_id to requeue"""
        if job.array_task_id is not None:
            return f"{job.array_job_id.number}_{job.array_task_id.number}"
        else:
            return f"{job.job_id}"

    def _requeue_failed_jobs(self, job_list: List[V0040JobInfo]) -> bool:
        """If retries are set, retry failed jobs"""
        jobs_to_retry = []
        for job in job_list:
            if (
                self.retry_count > 0
                and job.job_state[0] in JobState.STATES_TO_RETRY
                and (
                    job.restart_cnt is None
                    or self.retry_count > job.restart_cnt
                )
            ):
                jobs_to_retry.append(job)
        if jobs_to_retry and self.ssh_conn_id:
            # There doesn't seem to be a way to retry a job via the REST API
            # Will use an ssh client to requeue a job.
            ssh_hook = get_hpc_hook(self.ssh_conn_id)
            with ssh_hook.get_conn() as ssh_client:
                for job in jobs_to_retry:
                    job_id_to_retry = self._get_job_array_job_id(job)
                    restart_count = (
                        0 if job.restart_cnt is None else job.restart_cnt + 1
                    )
                    logging.warning(
                        f"Restarting {job.job_state} job: {job_id_to_retry}. "
                        f"Restart count: {restart_count}",
                        extra={
                            "process_name": "submit_slurm_job_array",
                            "pipeline_name": "airflow DAG",
                            "job_id": job_id_to_retry,
                            "job_state": job.job_state,
                        },
                    )
                    sleep(1)
                    command = f"scontrol requeue {job_id_to_retry}"
                    exit_status, agg_stdout, agg_stderr = (
                        ssh_hook.exec_ssh_client_command(
                            ssh_client=ssh_client,
                            command=command,
                            get_pty=False,
                            environment=dict(),
                            timeout=60,
                        )
                    )
                    if exit_status != 0:
                        raise Exception(
                            f"There was an error with job requeue! "
                            f"{agg_stderr}"
                        )
            return True
        else:
            return False

    def _check_job_status(
        self, job_response: V0040OpenapiJobInfoResp, job_status: dict
    ) -> (bool, bool):
        """
        Scans list of jobs for their status codes. Restarts failed jobs if
        retry_count is set.
        Parameters
        ----------
        job_response :  V0040OpenapiJobInfoResp
        job_status : dict
          Dictionary to hold job_states for each individual job.

        Returns
        -------
        (bool, bool)
          First part of return value will be True if all jobs are finished.
          Second part of return value will be True if any jobs had errors.

        """
        most_recent_job_status: Dict[int, str] = dict()
        for job in job_response.jobs:
            job_id = job.job_id
            job_state = job.job_state
            if job_id and job_state:
                most_recent_job_status[job_id] = job_state[0]
        is_finished_list = [
            s in JobState.FINISHED_CODES
            for s in most_recent_job_status.values()
        ]
        if not is_finished_list:
            is_finished = True
        else:
            is_finished = reduce(lambda x, y: x and y, is_finished_list)
        job_status.update(most_recent_job_status)
        check_for_errors_list = [
            s in JobState.ERROR_CODES for s in job_status.values()
        ]
        if not check_for_errors_list:
            is_error = True
        else:
            is_error = reduce(lambda x, y: x or y, check_for_errors_list)
        are_jobs_requeued = self._requeue_failed_jobs(job_response.jobs)
        is_finished = False if are_jobs_requeued else is_finished
        return is_finished, is_error

    def _submit_job(self) -> V0040OpenapiJobSubmitResponse:
        """
        Submit the job to the slurm cluster.
        Returns
        -------
        V0040OpenapiJobSubmitResponse

        """

        job_submission = V0040JobSubmitReq(
            script=self.script, job=self.job_properties
        )
        submit_response = self.slurm.slurm_v0040_post_job_submit(
            v0040_job_submit_req=job_submission
        )
        if submit_response.errors:
            raise Exception(
                f"There were errors submitting the job to slurm: "
                f"{submit_response.errors}"
            )
        return submit_response

    def _monitor_job(
        self, submit_response: V0040OpenapiJobSubmitResponse
    ) -> Tuple[int, int]:
        """
        Monitor a job submitted to the slurm cluster.

        Parameters
        ----------
        submit_response : V0040OpenapiJobSubmitResponse
          The initial job submission response. Used to extract the job_id.

        Returns
        -------
        Tuple[int, int]
          Start time and end time of the job.
        """

        job_id = submit_response.job_id
        job_name = self.job_properties.name
        # Slurm has two endpoints to get job information. For running jobs,
        # there is a quick one. For jobs that have completed, we have to
        # check a database. We try the quick one first.
        job_response = V0040OpenapiJobInfoResp(
            jobs=[],
            last_backfill=V0040Uint64NoVal(),
            last_update=V0040Uint64NoVal(),
        )
        logging.debug(
            f"Initialized placeholder: {job_response}",
            extra={
                "process_name": "monitor_slurm_job",
                "pipeline_name": "airflow DAG",
                "acquisition_name": job_name,
                "job_id": job_id,
            },
        )
        try:
            job_response = self.slurm.slurm_v0040_get_job(job_id=str(job_id))
        except NotFoundException:
            logging.warning(
                "Looking for job info in database...",
                extra={
                    "process_name": "monitor_slurm_job",
                    "pipeline_name": "airflow DAG",
                    "acquisition_name": job_name,
                    "job_id": job_id,
                },
            )
            slurm_db_api = SlurmdbApi(api_client=self.slurm.api_client)
            slurm_db_response = slurm_db_api.slurmdb_v0040_get_job(
                job_id=str(job_id)
            )
            job_start_times = []
            job_end_times = []
            for job in slurm_db_response.jobs:
                if job.state.current[0] != JobState.CD:
                    raise Exception(
                        f"There was an issue with the Slurm job:"
                        f" {job_id}, {job.state}"
                    )
                else:
                    job_start_times.append(job.time.start)
                    job_end_times.append(job.time.end)
            return min(job_start_times), max(job_end_times)

        errors = job_response.errors
        start_time = (
            None
            if not job_response.jobs or job_response.jobs[0].start_time is None
            else job_response.jobs[0].start_time.number
        )
        end_time = (
            None
            if not job_response.jobs or job_response.jobs[0].end_time is None
            else job_response.jobs[0].end_time.number
        )
        job_states = (
            None
            if not job_response.jobs
            else [j.job_state[0] for j in job_response.jobs]
        )
        message = json.dumps(
            {
                "job_id": job_id,
                "job_name": job_name,
                "job_states": job_states,
                "start_time": start_time,
            }
        )
        logging.info(
            message,
            extra={
                "process_name": "monitor_slurm_job",
                "pipeline_name": "airflow DAG",
                "acquisition_name": job_name,
                "job_id": job_id,
            },
        )
        job_status = dict()
        is_finished, is_error = self._check_job_status(
            job_response, job_status
        )
        while not is_finished and not errors:
            sleep(self.polling_request_sleep)
            job_response = self.slurm.slurm_v0040_get_job(job_id=str(job_id))
            errors = job_response.errors
            start_time = (
                None
                if not job_response.jobs
                or job_response.jobs[0].start_time is None
                else job_response.jobs[0].start_time.number
            )
            end_time = (
                None
                if not job_response.jobs
                or job_response.jobs[0].end_time is None
                else job_response.jobs[0].end_time.number
            )
            job_states = (
                None
                if not job_response.jobs
                else [j.job_state[0] for j in job_response.jobs]
            )
            message = json.dumps(
                {
                    "job_id": job_id,
                    "job_name": job_name,
                    "job_states": job_states,
                    "start_time": start_time,
                }
            )
            logging.info(
                message,
                extra={
                    "process_name": "monitor_slurm_job",
                    "pipeline_name": "airflow DAG",
                    "acquisition_name": job_name,
                    "job_id": job_id,
                },
            )
            is_finished, is_error = self._check_job_status(
                job_response, job_status
            )

        if is_error or errors:
            message = json.dumps(
                {
                    "job_id": job_id,
                    "job_name": job_name,
                    "job_status": job_status,
                }
            )
            std_err_filepath = self._std_err_filepath(job_id=job_id)
            std_err_msg = read_slurm_std_err(
                filepath=std_err_filepath,
                remote_mnt_dir=self.remote_mnt_dir,
                local_mnt_dir=self.local_mnt_dir,
            )
            logging.exception(
                f"std_err:\n{std_err_msg}",
                extra={
                    "process_name": "monitor_slurm_job",
                    "pipeline_name": "airflow DAG",
                    "acquisition_name": job_name,
                    "job_id": job_id,
                },
            )
            raise Exception(
                f"There were errors with the slurm job. "
                f"Job: {message}. "
                f"Errors: {errors}"
            )
        else:
            logging.info(
                "Job is Finished!",
                extra={
                    "process_name": "monitor_slurm_job",
                    "pipeline_name": "airflow DAG",
                    "acquisition_name": job_name,
                    "job_id": job_id,
                },
            )
        return start_time, end_time

    def _std_err_filepath(self, job_id: Union[int, str]) -> str:
        """
        Resolves standard out and standard error locations.
        Parameters
        ----------
        job_id : Union[int, str]

        Returns
        -------
        str
          Actual location of log files.

        """
        job_name = self.job_properties.name
        return self.job_properties.standard_error.replace(
            "%x", job_name
        ).replace("%j", str(job_id))

    def run_job(self):
        """Submit and monitor a job."""
        submit_response = self._submit_job()
        job_id = submit_response.job_id
        job_name = self.job_properties.name
        logging.info(
            f"Job Name: {job_name}",
            extra={
                "process_name": "run_slurm_job",
                "pipeline_name": "airflow DAG",
                "acquisition_name": job_name,
                "job_id": job_id,
                "event_type": "stage_start",
            },
        )
        logging.info(
            f"Job ID: {job_id}",
            extra={
                "process_name": "run_slurm_job",
                "pipeline_name": "airflow DAG",
                "acquisition_name": job_name,
                "job_id": job_id,
            },
        )
        std_err = self._std_err_filepath(job_id=job_id)
        logging.info(
            f"Please check {std_err} for additional logs.",
            extra={
                "process_name": "run_slurm_job",
                "pipeline_name": "airflow DAG",
                "acquisition_name": job_name,
                "job_id": job_id,
            },
        )
        self._monitor_job(submit_response=submit_response)
        logging.info(
            f"Job '{job_name}' completed successfully!",
            extra={
                "process_name": "run_slurm_job",
                "pipeline_name": "airflow DAG",
                "acquisition_name": job_name,
                "job_id": job_id,
                "event_type": "stage_complete",
            },
        )


class SlurmJobSensor:
    """Checks if Slurm is finished or not."""

    def __init__(
        self,
        job_id: int,
        slurm: SlurmApi,
        retry_count: int,
        ssh_conn_id: str,
        std_err_filepath: str,
        remote_mnt_dir: str = "/allen/aind/",
        local_mnt_dir: str = "/data/",
    ):
        """Class constructor"""
        self.job_id = job_id
        self.slurm = slurm
        self.retry_count = retry_count
        self.ssh_conn_id = ssh_conn_id
        self.std_err_filepath = std_err_filepath
        self.remote_mnt_dir = remote_mnt_dir
        self.local_mnt_dir = local_mnt_dir

    @staticmethod
    def _get_job_array_job_id(job: V0040JobInfo) -> str:
        """Get job_id to requeue"""
        if job.array_task_id is not None:
            return f"{job.array_job_id.number}_{job.array_task_id.number}"
        else:
            return f"{job.job_id}"

    def _requeue_failed_jobs(self, job_list: List[V0040JobInfo]) -> bool:
        """If retries are set, retry failed jobs"""
        jobs_to_retry = []
        for job in job_list:
            if (
                self.retry_count > 0
                and job.job_state[0] in JobState.STATES_TO_RETRY
                and (
                    job.restart_cnt is None
                    or self.retry_count > job.restart_cnt
                )
            ):
                jobs_to_retry.append(job)
        if jobs_to_retry and self.ssh_conn_id:
            # There doesn't seem to be a way to retry a job via the REST API
            # Will use an ssh client to requeue a job.
            ssh_hook = get_hpc_hook(self.ssh_conn_id)
            with ssh_hook.get_conn() as ssh_client:
                for job in jobs_to_retry:
                    job_id_to_retry = self._get_job_array_job_id(job)
                    restart_count = (
                        0 if job.restart_cnt is None else job.restart_cnt + 1
                    )
                    logging.warning(
                        f"Restarting {job.job_state} job: {job_id_to_retry}. "
                        f"Restart count: {restart_count}",
                        extra={
                            "process_name": "slurm_job_sensor",
                            "pipeline_name": "airflow DAG",
                            "job_id": job_id_to_retry,
                            "job_state": job.job_state,
                        },
                    )
                    sleep(1)
                    command = f"scontrol requeue {job_id_to_retry}"
                    exit_status, agg_stdout, agg_stderr = (
                        ssh_hook.exec_ssh_client_command(
                            ssh_client=ssh_client,
                            command=command,
                            get_pty=False,
                            environment=dict(),
                            timeout=60,
                        )
                    )
                    if exit_status != 0:
                        raise Exception(
                            f"There was an error with job requeue! "
                            f"{agg_stderr}"
                        )
            return True
        else:
            return False

    def _check_job_status(
        self, job_response: V0040OpenapiJobInfoResp
    ) -> Tuple[bool, bool, Optional[int], Optional[int]]:
        """
        Scans list of jobs for their status codes. Restarts failed jobs if
        retry_count is set.

        Parameters
        ----------
        job_response :  V0040OpenapiJobInfoResp

        Returns
        -------
        Tuple[bool, bool, int, int]
          First part of return value will be True if all jobs are finished.
          Second part of return value will be True if any jobs had errors.
          Third part of return value is the earliest start time among the jobs.
          Fourth part of return value is the latest end time among the jobs.

        """
        job_status: Dict[int, str] = dict()
        job_start_times = []
        job_end_times = []
        for job in job_response.jobs:
            job_start_times.append(job.start_time.number)
            job_end_times.append(job.end_time.number)
            job_id = job.job_id
            job_state = job.job_state
            if job_id and job_state:
                job_status[job_id] = job_state[0]
        is_finished_list = [
            s in JobState.FINISHED_CODES for s in job_status.values()
        ]
        if not is_finished_list:
            is_finished = True
        else:
            is_finished = reduce(lambda x, y: x and y, is_finished_list)
        check_for_errors_list = [
            s in JobState.ERROR_CODES for s in job_status.values()
        ]
        if not check_for_errors_list:
            is_error = True
        else:
            is_error = reduce(lambda x, y: x or y, check_for_errors_list)
        are_jobs_requeued = self._requeue_failed_jobs(job_response.jobs)
        is_finished = False if are_jobs_requeued else is_finished
        start_time = min(job_start_times) if job_start_times else None
        end_time = max(job_end_times) if job_end_times else None
        return is_finished, is_error, start_time, end_time

    def get_job_status(self) -> Tuple[bool, int, int]:
        """
        Checks job is finished. Raise an error if job failed.
        """

        job_id = self.job_id
        # Slurm has two endpoints to get job information. For running jobs,
        # there is a quick one. For jobs that have completed, we have to
        # check a database. We try the quick one first.
        try:
            job_response = self.slurm.slurm_v0040_get_job(job_id=str(job_id))
            errors = job_response.errors
            is_finished, is_error, start_time, end_time = (
                self._check_job_status(job_response)
            )

            if is_error or errors:
                std_err_msg = read_slurm_std_err(
                    filepath=self.std_err_filepath,
                    remote_mnt_dir=self.remote_mnt_dir,
                    local_mnt_dir=self.local_mnt_dir,
                )
                logging.exception(
                    f"std_err:\n{std_err_msg}",
                    extra={
                        "process_name": "slurm_job_sensor",
                        "pipeline_name": "airflow DAG",
                        "job_id": self.job_id,
                    },
                )
                raise Exception(
                    f"There were errors with the slurm job. "
                    f"Job: {self.job_id}. "
                    f"Errors: {errors}"
                )
            return is_finished, start_time, end_time
        except NotFoundException:
            logging.warning(
                "Looking for job info in database...",
                extra={
                    "process_name": "slurm_job_sensor",
                    "pipeline_name": "airflow DAG",
                    "job_id": job_id,
                },
            )
            slurm_db_api = SlurmdbApi(api_client=self.slurm.api_client)
            slurm_db_response = slurm_db_api.slurmdb_v0040_get_job(
                job_id=str(job_id)
            )
            job_start_times = []
            job_end_times = []
            job_id_to_states_map = {
                job.job_id: {"states": [], "start_times": [], "end_times": []}
                for job in slurm_db_response.jobs
            }
            for job in slurm_db_response.jobs:
                job_id_to_states_map[job.job_id]["states"].extend(
                    job.state.current
                )
                if JobState.CD in job.state.current:
                    job_id_to_states_map[job.job_id]["start_times"].append(
                        job.time.start
                    )
                    job_id_to_states_map[job.job_id]["end_times"].append(
                        job.time.end
                    )
            for job_id, job_info in job_id_to_states_map.items():
                if JobState.CD not in job_info["states"]:
                    raise Exception(
                        f"There was an issue with the Slurm job:"
                        f" {job_id}, {job_info['states']}"
                    )
                else:
                    job_start_times.extend(job_info["start_times"])
                    job_end_times.extend(job_info["end_times"])
            return True, min(job_start_times), max(job_end_times)
