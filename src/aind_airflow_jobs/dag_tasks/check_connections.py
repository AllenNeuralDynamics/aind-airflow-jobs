"""CLI module for check_connections DAG tasks."""

import argparse
import os
import sys


def check_param_store_connection():
    """Check AWS parameter store connections."""
    # Airflow Variables and Connections are loaded as env vars
    default_transfer_settings = os.getenv("DEFAULT_TRANSFER_SETTINGS")
    slurm_uri = os.getenv("SLURM_URI")
    ams_uri = os.getenv("AMS_URI")
    co_uri = os.getenv("CO_URI")
    
    print(default_transfer_settings)
    print(ams_uri)

    if not default_transfer_settings:
        raise AssertionError("Unable to retrieve default_transfer_settings!")
    if not slurm_uri:
        raise AssertionError("Unable to retrieve slurm_uri!")
    if not ams_uri:
        raise AssertionError("Unable to retrieve ams_uri!")
    if not co_uri:
        raise AssertionError("Unable to retrieve co_uri!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tasks for check_connections DAG")
    parser.add_argument('task_id', help='Id of the task to run')
    
    args = parser.parse_args()
    
    # Get function by name from current module
    current_module = sys.modules[__name__]
    task_func = getattr(current_module, args.task_id, None)
    
    if task_func is None or not callable(task_func):
        print(f"Task function '{args.task_id}' not found or not callable!")
        sys.exit(1)
    
    try:
        task_func()
        print(f"Task '{args.task_id}' completed successfully!")
    except Exception as e:
        print(f"Task '{args.task_id}' failed: {e}")
        sys.exit(1)