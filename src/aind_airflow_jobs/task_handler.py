"""Module to handle configuring settings for tasks."""

import collections.abc
import json
import logging
from typing import Any, Dict, Optional

from airflow.models import Variable


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

    logging.info(f"Job type settings: {preset_task}")
    logging.info(f"User settings: {user_task}")
    nested_update(preset_task, user_task)
    logging.info(f"Merged settings: {preset_task}")
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
    return script
