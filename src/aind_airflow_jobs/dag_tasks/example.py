"""CLI module for example DAG tasks."""

import argparse
import sys


def hello_world():
    """Example task function"""
    print("Hello, World!")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tasks for example DAG")
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