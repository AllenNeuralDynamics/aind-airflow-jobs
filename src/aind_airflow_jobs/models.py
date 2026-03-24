from typing import Any, Dict, Optional

from aind_slurm_rest_v2 import ApiClient as Client
from aind_slurm_rest_v2 import Configuration as Config
from aind_slurm_rest_v2.api.slurm_api import SlurmApi
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AirflowTaskSettings(BaseSettings):
    """Settings from Airflow Task runtime passed via env vars"""

    model_config = SettingsConfigDict(env_prefix="AIRFLOW_")

    # Context
    ctx_task_id: str
    ctx_dag_id: Optional[str] = None
    ctx_dag_run_id: Optional[str] = None
    ctx_dag_run_conf: Optional[Dict[str, Any]] = None

    # Variables (from AWS Parameter Store)
    var_param_default: Dict[str, Any] = dict()

    # Input from xcom or other
    task_input_str: Optional[str] = None

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
