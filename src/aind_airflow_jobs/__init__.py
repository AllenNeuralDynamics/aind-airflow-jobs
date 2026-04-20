"""Package to manage airflow jobs."""

import logging
import logging.config
import os
from datetime import datetime, timezone
from logging import LogRecord

import log_json
import yaml

__version__ = "0.4.2"


# We want to standardize the timestamp format to UTC and ISO-8601, which
# requires a custom formatter and cannot be done through configuration only.
class CustomJsonFormatter(log_json.JsonFormatter):
    """Custom class to format log timestamps as ISO-8601 UTC."""

    def formatTime(self, record: LogRecord, datefmt=None) -> str:
        """
        Format timestamp as ISO-8601 UTC.

        Parameters
        ----------
        record : LogRecord
        datefmt : str, optional
            Unused parameter, kept for signature compatibility.

        Returns
        -------
        str

        """
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


if os.path.isfile(os.getenv("LOGGING_CONFIG_FILE", "log_config.yaml")):
    config_path = os.getenv("LOGGING_CONFIG_FILE", "log_config.yaml")
    with open(config_path, "rt", encoding="utf-8") as f:
        config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
    logging.info("Found logging file at: %s", config_path)
