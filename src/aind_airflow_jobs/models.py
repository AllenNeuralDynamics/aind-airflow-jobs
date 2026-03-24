from typing import Any, Dict, Optional

from aind_slurm_rest_v2 import ApiClient as Client
from aind_slurm_rest_v2 import Configuration as Config
from aind_slurm_rest_v2.api.slurm_api import SlurmApi
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AirflowContextSettings(BaseSettings):
    """Settings from Airflow Context passed via env vars"""

    model_config = SettingsConfigDict(env_prefix="AIRFLOW_CTX_")

    task_id: str
    dag_id: Optional[str] = None
    dag_run_id: Optional[str] = None
    dag_run_conf: Optional[Dict[str, Any]] = None


class SlurmClientSettings(BaseSettings):
    """Settings required to build slurm api client"""

    model_config = SettingsConfigDict(env_prefix="SLURM_V2_CLIENT_")
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
