"""Module to handle connecting to the HPC"""

from airflow.providers.ssh.hooks.ssh import SSHHook


def get_hpc_hook() -> SSHHook:
    """Returns a hook to send ssh commands to the hpc"""
    return SSHHook(ssh_conn_id="hpc/uri")
