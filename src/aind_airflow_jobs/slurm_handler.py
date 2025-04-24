"""Module to handle sending requests to HPC"""

import json
import logging
import re
from collections import deque
from datetime import datetime
from enum import Enum
from functools import reduce
from os.path import isfile
from time import sleep
from typing import Any, Dict, Optional, Union
from uuid import uuid4

from aind_slurm_rest import ApiClient as Client
from aind_slurm_rest import Configuration as Config
from aind_slurm_rest.api.slurm_api import SlurmApi
from aind_slurm_rest.models.v0040_job_desc_msg import V0040JobDescMsg
from aind_slurm_rest.models.v0040_job_submit_req import V0040JobSubmitReq
from aind_slurm_rest.models.v0040_openapi_job_info_resp import (
    V0040OpenapiJobInfoResp,
)
from aind_slurm_rest.models.v0040_openapi_job_submit_response import (
    V0040OpenapiJobSubmitResponse,
)
from airflow.hooks.base import BaseHook
from airflow.models import Connection
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def create_slurm_environment_for_task(
    job: Dict[str, Any],
    task_settings: Dict[str, Any],
    name_suffix: Optional[str] = None,
):
    """Parses the context to set slurm job settings for a task"""
    slurm_settings = task_settings.get("job_properties", {})
    logs_directory = task_settings["logs_directory"]
    s3_prefix = job.get("s3_prefix", "")
    s3_prefix_parts = s3_prefix.split("_")
    if len(s3_prefix_parts) > 1:
        job_name = (
            f"{s3_prefix_parts[0]}"
            f"_{s3_prefix_parts[1]}"
            f"_job_{str(int(datetime.utcnow().timestamp()))}"
            f"_{str(uuid4())[0:5]}"
        )
    else:
        job_name = (
            f"job_{str(int(datetime.utcnow().timestamp()))}"
            f"_{str(uuid4())[0:5]}"
        )
    if name_suffix:
        job_name = f"{job_name}_{name_suffix}"
    # create job properties from task settings and job_name
    slurm_settings["name"] = job_name
    slurm_settings["standard_error"] = f"{logs_directory}/{job_name}_error.out"
    slurm_settings["standard_output"] = f"{logs_directory}/{job_name}.out"
    slurm_settings["current_working_directory"] = "."
    job_properties = V0040JobDescMsg.model_validate(slurm_settings)
    return job_properties


def read_json_file(
    filepath: str, remote_mnt_dir: str, local_mnt_dir: str
) -> dict:
    """Reads a file located on a shared location."""
    # Change to mount path
    mounted_path = filepath.replace(remote_mnt_dir, local_mnt_dir, 1)
    with open(mounted_path, "r") as f:
        contents = json.load(f)
    return contents


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


class SlurmClientSettings(BaseSettings):
    """Settings required to build slurm api client"""

    model_config = SettingsConfigDict(env_prefix="SLURM_CLIENT_")
    host: str
    username: str
    access_token: SecretStr

    def create_api_client(self) -> SlurmApi:
        """Create an api client using settings"""
        config = Config(
            host=self.host,
            username=self.username,
            access_token=self.access_token.get_secret_value(),
        )
        slurm = SlurmApi(Client(config))
        return slurm


class SlurmHook(BaseHook):
    """Hook to interface with Slurm over REST."""

    def __init__(self, conn_id="slurm/uri"):
        """Class constructor"""
        super().__init__()
        self.conn_id = conn_id
        self.conn = self.get_conn()

    def get_conn(self) -> SlurmApi:
        """
        Get connection to Slurm.
        Returns
        -------
        SlurmApi

        """
        slurm_conn = Connection.get_connection_from_secrets(self.conn_id)
        slurm_host = f"{slurm_conn.conn_type}://{slurm_conn.host}"
        slurm_client_settings = SlurmClientSettings(
            host=slurm_host,
            username=slurm_conn.login,
            access_token=slurm_conn.extra_dejson["token"],
        )
        return slurm_client_settings.create_api_client()


class JobState(str, Enum):
    """The possible job_state values in the V0036JobsResponse class. The enums
    don't appear to be importable from the aind-slurm-rest api."""

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

    # Job terminated due to failure of one or more allocated nodes.
    NF = "NODE_FAIL"

    # Job experienced out of memory error.
    OOM = "OUT_OF_MEMORY"

    # Job is awaiting resource allocation.
    PD = "PENDING"

    # Job terminated due to preemption.
    PR = "PREEMPTED"

    # Job currently has an allocation.
    R = "RUNNING"

    # Job is being held after requested reservation was deleted.
    RD = "RESV_DEL_HOLD"

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

    # Job is staging out files.
    SO = "STAGE_OUT"

    # Job has an allocation, but execution has been stopped with SIGSTOP
    # signal. CPUS have been retained by this job.
    ST = "STOPPED"

    # Job has an allocation, but execution has been suspended and CPUs have
    # been released for other jobs.
    S = "SUSPENDED"

    # Job terminated upon reaching its time limit.
    TO = "TIMEOUT"

    FINISHED_CODES = [BF, CA, CD, DL, F, NF, OOM, PR, RS, RV, SE, ST, S, TO]


class SubmitSlurmJobArray:
    """Main class to handle submitting and monitoring a slurm job"""

    def __init__(
        self,
        slurm: SlurmApi,
        job_properties: V0040JobDescMsg,
        script: str,
        remote_mnt_dir: str,
        local_mnt_dir: str,
        poll_job_interval: int = 120,
    ):
        """
        Class constructor
        Parameters
        ----------
        slurm : SlurmApi
        job_properties : V0040JobDescMsg
        script : str
        remote_mnt_dir: str
           Location of logging directory mount
        local_mnt_dir: str
           Local location of logging directory
        poll_job_interval : int
           Number of seconds to wait before checking slurm job status.
           Default is 120.
        """
        self.slurm = slurm
        self.job_properties = job_properties
        self.script = script
        self.remote_mnt_dir = remote_mnt_dir
        self.local_mnt_dir = local_mnt_dir
        self.polling_request_sleep = poll_job_interval

    @staticmethod
    def _check_job_status(
        job_response: V0040OpenapiJobInfoResp, job_status: dict
    ) -> (bool, bool):
        """
        Scans list of jobs for their status codes.
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
            s not in [JobState.CD, JobState.CG] for s in job_status.values()
        ]
        if not check_for_errors_list:
            is_error = True
        else:
            is_error = reduce(lambda x, y: x or y, check_for_errors_list)
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
    ) -> None:
        """
        Monitor a job submitted to the slurm cluster.
        Parameters
        ----------
        submit_response : V0040OpenapiJobSubmitResponse
          The initial job submission response. Used to extract the job_id.

        """

        job_id = submit_response.job_id
        job_name = self.job_properties.name
        job_response = self.slurm.slurm_v0040_get_job(job_id=job_id)
        errors = job_response.errors
        start_time = (
            None if not job_response.jobs else job_response.jobs[0].start_time
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
        logging.info(message)
        job_status = dict()
        (is_finished, is_error) = self._check_job_status(
            job_response, job_status
        )
        while not is_finished and not errors:
            sleep(self.polling_request_sleep)
            job_response = self.slurm.slurm_v0040_get_job(job_id=job_id)
            errors = job_response.errors
            start_time = (
                None
                if not job_response.jobs
                else job_response.jobs[0].start_time
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
                    "start_time": start_time.number,
                }
            )
            logging.info(message)
            (is_finished, is_error) = self._check_job_status(
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
            logging.exception(f"std_err:\n{std_err_msg}")
            raise Exception(
                f"There were errors with the slurm job. "
                f"Job: {message}. "
                f"Errors: {errors}"
            )
        else:
            logging.info("Job is Finished!")
        return None

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
        logging.info(f"Job Name: {job_name}")
        logging.info(f"Job ID: {job_id}")
        std_err = self._std_err_filepath(job_id=job_id)
        logging.info(f"Please check {std_err} for additional logs.")
        self._monitor_job(submit_response=submit_response)
