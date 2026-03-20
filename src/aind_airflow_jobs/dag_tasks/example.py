"""CLI module for example DAG tasks."""

import argparse
import logging
import sys

def hello_world():
    """Example task function"""
    logging.info("Hello, World!")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tasks for example DAG")
    parser.add_argument('task_id', help='Id of the task to run')
    
    args = parser.parse_args()
    
    # Get function by name from current module
    current_module = sys.modules[__name__]
    task_func = getattr(current_module, args.task_id, None)
    
    if task_func is None or not callable(task_func):
        raise ValueError(f"Task function '{args.task_id}' not found or not callable!")

    task_func()
    logging.info(f"Task '{args.task_id}' completed successfully!")