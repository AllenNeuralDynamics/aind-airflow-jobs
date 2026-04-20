"""Module to handle configuring settings for tasks."""

import collections.abc
import json
import logging
from copy import deepcopy
from hashlib import sha256
from typing import Any, Dict, List, Optional

from airflow.models import Variable


def create_slurm_job_name(s3_prefix: str, run_id: str) -> str:
    """Create a unique job name"""
    hashed_dag_run_id = sha256(run_id.encode("utf-8")).hexdigest()[0:10]
    return f"{s3_prefix}_{hashed_dag_run_id}"


def nested_update(
    d: Dict[str, Any], u: collections.abc.Mapping
) -> Dict[str, Any]:
    """Update a nested dictionary."""
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = nested_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def get_merged_task_settings(
    job_type: str,
    task_id: str,
    user_task: Dict[str, Any],
    modality_abbreviation: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates merged task settings from preset and user-defined settings.

    - Presets are fetched from aws based on job_type, task_id, and modality
    - User task is pulled from the job configuration
    - When merging, user-defined settings take precedence over presets
    """

    # Compute the param store key
    if modality_abbreviation is None:
        param_store_key = f"job_types/v2/{job_type}/tasks/{task_id}"
        default_key = f"job_types/v2/default/tasks/{task_id}"
    else:
        param_store_key = (
            f"job_types/v2/{job_type}/tasks/{task_id}/{modality_abbreviation}"
        )
        default_key = (
            f"job_types/v2/default/tasks/{task_id}/{modality_abbreviation}"
        )
    # If custom is used, then we'll skip downloading presets
    if job_type.strip().lower() == "custom":
        preset_task = dict()
    else:
        preset_task = Variable.get(
            key=param_store_key,
            default_var=None,
            deserialize_json=True,
        )
        # Get the default if not found for job_type
        if preset_task is None:
            preset_task = Variable.get(
                key=default_key,
                default_var=dict(),
                deserialize_json=True,
            )

    logging.info(
        f"Job type settings keys: {sorted(list(preset_task.keys()))}",
        extra={
            "process_name": task_id,
            "pipeline_name": "airflow DAG",
            "job_type": job_type,
            "modality_abbreviation": modality_abbreviation,
        },
    )
    logging.info(
        f"User settings keys: {sorted(list(user_task.keys()))}",
        extra={
            "process_name": task_id,
            "pipeline_name": "airflow DAG",
            "job_type": job_type,
            "modality_abbreviation": modality_abbreviation,
        },
    )
    nested_update(preset_task, user_task)
    logging.info(
        f"Merged settings keys: {sorted(list(preset_task.keys()))}",
        extra={
            "process_name": task_id,
            "pipeline_name": "airflow DAG",
            "job_type": job_type,
            "modality_abbreviation": modality_abbreviation,
        },
    )
    return preset_task


def update_command_script(
    command_script: str,
    job_settings: Optional[dict] = None,
    image: Optional[str] = None,
    image_version: Optional[str] = None,
    input_source: Optional[str] = None,
    output_location: Optional[str] = None,
    env_file: Optional[str] = None,
    s3_location: Optional[str] = None,
) -> str:
    """
    There are special placeholder values users can set in the job_settings
    and command scripts. This will replace these placeholders with values
    computed by the service at runtime.
    """
    script = command_script
    if job_settings is not None:
        script = script.replace("%JOB_SETTINGS", json.dumps(job_settings))
    if image_version is not None:
        script = script.replace("%IMAGE_VERSION", image_version)
    if image is not None:
        script = script.replace("%IMAGE", image)
    if input_source is not None:
        script = script.replace("%INPUT_SOURCE", input_source)
    if output_location is not None:
        script = script.replace("%OUTPUT_LOCATION", output_location)
    if s3_location is not None:
        script = script.replace("%S3_LOCATION", s3_location)
    if env_file is not None:
        script = script.replace("%ENV_FILE", env_file)
    if any(
        ext in script
        for ext in [
            "%JOB_SETTINGS",
            "%IMAGE_VERSION",
            "%IMAGE",
            "%INPUT_SOURCE",
            "%OUTPUT_LOCATION",
            "%S3_LOCATION",
            "%ENV_FILE",
        ]
    ):
        raise ValueError(f"{script} contains variable that needs replacement.")
    return script


def get_gather_preliminary_metadata_settings(
    image: str,
    image_version: str,
    staging_folder: str,
    merged_job_settings: dict,
    subject_id: str,
    s3_prefix: str,
    acq_datetime: str,
    project_name: str,
    modalities: list,
    metadata_service_domain: str,
) -> dict:
    """
    Convert info that can be passed into gather_preliminary_metadata job.
    """
    job_settings = deepcopy(merged_job_settings)
    # Not ideal, but we can get rid of this check once people are fully on
    # aind-data-schema v2
    if (
        "aind-metadata-mapper" in image
        and not image_version.startswith("v1-")
        and not image_version.startswith("1.")
    ):
        # metadata mapper v0
        subject_settings = job_settings.get("subject_settings", dict())
        data_description_settings = job_settings.get(
            "raw_data_description_settings", dict()
        )
        procedures_settings = job_settings.get("procedures_settings", dict())
        rig_settings = job_settings.get("rig_settings", dict())
        instrument_settings = job_settings.get("instrument_settings", dict())
        if subject_settings.get("subject_id", "") == "":
            subject_settings["subject_id"] = subject_id
        if data_description_settings.get("name", "") == "":
            data_description_settings["name"] = s3_prefix
        if data_description_settings.get("project_name", "") == "":
            data_description_settings["project_name"] = project_name
        if data_description_settings.get("modality", "") == "":
            data_description_settings["modality"] = modalities
        if procedures_settings.get("subject_id", "") == "":
            procedures_settings["subject_id"] = subject_id
        if rig_settings.get("rig_id") is None:
            rig_settings["rig_id"] = ""
        if instrument_settings.get("instrument_id") is None:
            instrument_settings["instrument_id"] = ""
        job_settings["raw_data_description_settings"] = (
            data_description_settings
        )
        job_settings["subject_settings"] = subject_settings
        job_settings["procedures_settings"] = procedures_settings
        job_settings["rig_settings"] = rig_settings
        job_settings["instrument_settings"] = instrument_settings
        job_settings["directory_to_write_to"] = staging_folder
        job_settings["metadata_service_domain"] = metadata_service_domain
    else:
        # metadata mapper v1
        job_settings.update(
            {
                "output_dir": staging_folder,
                "acquisition_start_time": acq_datetime,
                "subject_id": subject_id,
                "metadata_service_url": metadata_service_domain,
            }
        )
        data_description_settings = job_settings.get(
            "data_description_settings", dict()
        )
        data_description_settings.update(
            {
                "project_name": project_name,
                "modalities": modalities,
            }
        )
        job_settings["data_description_settings"] = data_description_settings
    return job_settings


def get_gather_final_metadata_settings(
    image: str,
    image_version: str,
    job_settings: dict,
    data_processes: List[str],
    pipeline: dict,
    s3_prefix: str,
    staging_folder: str,
    location: str,
) -> dict:
    """Convert information that can be passed into aind-metadata-mapper."""

    # Not ideal, but we can get rid of this check once people are fully on
    # aind-data-schema v2
    if (
        "aind-metadata-mapper" in image
        and not image_version.startswith("v1-")
        and not image_version.startswith("1.")
    ):
        processor_full_name = (
            job_settings.get("processing_settings", dict())
            .get("pipeline_process", dict())
            .get("processor_full_name", "AIND Scientific Computing")
        )
        processing_settings = {
            "pipeline_process": {
                "processor_full_name": processor_full_name,
                "data_processes": [
                    json.loads(dp)
                    for dp in data_processes
                    if json.loads(dp).get("name") is not None
                ],
            }
        }
        metadata_settings = {
            "name": s3_prefix,
            "location": location,
            "subject_filepath": f"{staging_folder}/subject.json",
            "data_description_filepath": (
                f"{staging_folder}/data_description.json"
            ),
            "processing_filepath": f"{staging_folder}/processing.json",
            "procedures_filepath": f"{staging_folder}/procedures.json",
            "session_filepath": f"{staging_folder}/session.json",
            "rig_filepath": f"{staging_folder}/rig.json",
            "acquisition_filepath": f"{staging_folder}/acquisition.json",
            "instrument_filepath": f"{staging_folder}/instrument.json",
            "quality_control_filepath": (
                f"{staging_folder}/quality_control.json"
            ),
        }
        job_settings = {
            "directory_to_write_to": staging_folder,
            "processing_settings": processing_settings,
            "metadata_settings": metadata_settings,
        }
    else:
        v2_data_processes = []
        for data_process in data_processes:
            data_process_json = json.loads(data_process)
            code_url = data_process_json["code_url"]
            version = data_process_json["software_version"]
            if code_url is None or code_url == "":
                process_type = "Other"
            else:
                process_type = "Compression"
            start_date_time = data_process_json["start_date_time"]
            end_date_time = data_process_json.get("end_date_time")
            parameters = data_process_json.get("parameters")
            notes = data_process_json.get("notes")
            experimenters = ["AIND Scientific Computing"]
            v2_data_process = {
                "object_type": "Data process",
                "process_type": process_type,
                "name": process_type,
                "pipeline_name": pipeline.get("name"),
                "stage": "Processing",
                "code": {
                    "object_type": "Code",
                    "url": code_url,
                    "version": version,
                    "parameters": parameters,
                },
                "experimenters": experimenters,
                "start_date_time": start_date_time,
                "end_date_time": end_date_time,
                "notes": notes,
            }
            v2_data_processes.append(v2_data_process)
        processing_settings = {
            "object_type": "Processing",
            "data_processes": v2_data_processes,
            "pipelines": [pipeline],
        }
        job_settings = {
            "output_directory": staging_folder,
            "processing": processing_settings,
        }
    return job_settings
