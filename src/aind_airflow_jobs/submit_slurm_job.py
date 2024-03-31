"""Module to submit and monitor slurm jobs via the slurm rest api"""

import binascii
import json
import logging
import sys
from argparse import ArgumentParser
from enum import Enum
from pathlib import Path
from time import sleep
from typing import List

from aind_slurm_rest import ApiClient as Client
from aind_slurm_rest import Configuration as Config
from aind_slurm_rest import V0036JobSubmissionResponse
from aind_slurm_rest.api.slurm_api import SlurmApi
from aind_slurm_rest.models.v0036_job_properties import V0036JobProperties
from aind_slurm_rest.models.v0036_job_submission import V0036JobSubmission
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logging.basicConfig(level="INFO")


class SlurmClientSettings(BaseSettings):
    """Settings required to build slurm api client"""

    model_config = SettingsConfigDict(env_prefix="SLURM_CLIENT_")
    host: str
    username: str
    password: SecretStr
    access_token: SecretStr

    def create_api_client(self) -> SlurmApi:
        """Create an api client using settings"""
        config = Config(
            host=self.host,
            password=self.password.get_secret_value(),
            username=self.username,
            access_token=self.access_token.get_secret_value(),
        )
        slurm = SlurmApi(Client(config))
        slurm.api_client.set_default_header(
            header_name="X-SLURM-USER-NAME",
            header_value=self.username,
        )
        slurm.api_client.set_default_header(
            header_name="X-SLURM-USER-PASSWORD",
            header_value=self.password.get_secret_value(),
        )
        slurm.api_client.set_default_header(
            header_name="X-SLURM-USER-TOKEN",
            header_value=self.access_token.get_secret_value(),
        )
        return slurm


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


class SubmitSlurmJob:
    """Main class to handle submitting and monitoring a slurm job"""

    def __init__(
        self,
        slurm: SlurmApi,
        job_properties: V0036JobProperties,
        script: str,
        poll_job_interval: int = 120,
    ):
        """
        Class constructor
        Parameters
        ----------
        slurm : SlurmApi
        job_properties : V0036JobProperties
        script : str
        poll_job_interval : int
           Number of seconds to wait before checking slurm job status.
           Default is 120.
        """
        self.slurm = slurm
        self.job_properties = job_properties
        self.script = script
        self.polling_request_sleep = poll_job_interval

    def _submit_job(self) -> V0036JobSubmissionResponse:
        """Submit the job to the slurm cluster."""
        job_submission = V0036JobSubmission(
            script=self.script, job=self.job_properties
        )
        submit_response = self.slurm.slurmctld_submit_job_0(
            v0036_job_submission=job_submission
        )
        if submit_response.errors:
            raise Exception(
                f"There were errors submitting the job to slurm: "
                f"{submit_response.errors}"
            )
        return submit_response

    def _monitor_job(
        self, submit_response: V0036JobSubmissionResponse
    ) -> None:
        """
        Monitor a job submitted to the slurm cluster.
        Parameters
        ----------
        submit_response : V0036JobSubmissionResponse
          The initial job submission response. Used to extract the job_id.

        """

        job_id = submit_response.job_id
        job_name = self.job_properties.name
        job_response = self.slurm.slurmctld_get_job_0(job_id=job_id)
        errors = job_response.errors
        start_time = (
            None if not job_response.jobs else job_response.jobs[0].start_time
        )
        job_state = (
            None if not job_response.jobs else job_response.jobs[0].job_state
        )
        message = json.dumps(
            {
                "job_id": job_id,
                "job_name": job_name,
                "job_state": job_state,
                "start_time": start_time,
            }
        )
        logging.info(message)
        while (
            job_state
            and job_state not in JobState.FINISHED_CODES
            and not errors
        ):
            sleep(self.polling_request_sleep)
            job_response = self.slurm.slurmctld_get_job_0(job_id=job_id)
            errors = job_response.errors
            start_time = (
                None
                if not job_response.jobs
                else job_response.jobs[0].start_time
            )
            job_state = (
                None
                if not job_response.jobs
                else job_response.jobs[0].job_state
            )
            message = json.dumps(
                {
                    "job_id": job_id,
                    "job_name": job_name,
                    "job_state": job_state,
                    "start_time": start_time,
                }
            )
            logging.info(message)

        if job_state != JobState.CD or errors:
            message = json.dumps(
                {
                    "job_id": job_id,
                    "job_name": job_name,
                    "job_state": job_state,
                }
            )
            raise Exception(
                f"There were errors with the slurm job. "
                f"Job: {message}. "
                f"Errors: {errors}"
            )
        else:
            logging.info("Job is Finished!")
        return None

    def run_job(self):
        """Submit and monitor a job."""
        submit_response = self._submit_job()
        self._monitor_job(submit_response=submit_response)

    @classmethod
    def from_args(cls, system_args: List[str], slurm: SlurmApi):
        """
        Create job from command line arguments
        Parameters
        ----------
        system_args : List[str]
        slurm : SlurmApi
        """
        parser = ArgumentParser()
        parser.add_argument(
            "--script-path",
            type=str,
            required=False,
            help="Path to bash script for slurm to run",
        )
        parser.add_argument(
            "--script-encoded",
            type=str,
            required=False,
            help="Bash script encoded as a hex string for slurm to run",
        )
        parser.add_argument(
            "--job-properties",
            type=str,
            required=True,
        )
        job_args = parser.parse_args(system_args)
        if job_args.script_path:
            script_path = Path(job_args.script_path)
            with open(script_path, "r") as f:
                script = f.read()
        elif job_args.script_encoded:
            script = binascii.unhexlify(job_args.script_encoded).decode()
        else:
            raise AssertionError(
                "Either script-path or script-encoded is needed"
            )

        job_properties_json = job_args.job_properties
        job_properties = V0036JobProperties.model_validate_json(
            job_properties_json
        )
        return cls(script=script, job_properties=job_properties, slurm=slurm)


if __name__ == "__main__":

    sys_args = sys.argv[1:]
    slurm_client_settings = SlurmClientSettings()
    main_slurm = slurm_client_settings.create_api_client()
    main_slurm_job = SubmitSlurmJob.from_args(
        system_args=sys_args, slurm=main_slurm
    )
    main_slurm_job.run_job()
