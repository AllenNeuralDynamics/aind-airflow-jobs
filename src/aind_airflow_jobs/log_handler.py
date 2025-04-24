"""Module to handle logging to Loki."""

from airflow.hooks.base import BaseHook
from airflow.models import Connection, Variable
from logging_loki import LokiHandler


class LokiLoggerHook(BaseHook):
    """Hook to log to loki"""

    def __init__(self, conn_id="loki/uri", app_name="aind-airflow-service"):
        """Class constructor"""
        super().__init__()
        self.conn_id = conn_id
        self.app_name = app_name
        self.conn = self.get_conn()

    def get_conn(self) -> LokiHandler:
        """Return a Logger that can log to Loki Server"""
        loki_conn = Connection.get_connection_from_secrets(self.conn_id)
        uri = loki_conn.get_uri()
        url = f"{uri}/loki/api/v1/push"
        env_name = Variable.get("ENV_NAME", default_var="")
        app_name = (
            self.app_name if env_name == "" else f"{self.app_name}-{env_name}"
        )
        handler = LokiHandler(
            url=url,
            version="1",
            tags={"application": app_name},
        )
        return handler
