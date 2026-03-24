from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Optional, Dict, Any

class AirflowContextSettings(BaseSettings):
    """Settings from Airflow Context passed via env vars"""

    model_config = SettingsConfigDict(env_prefix="AIRFLOW_CTX_")

    dag_id: Optional[str] = None
    dag_run_id: Optional[str] = None
    dag_run_conf: Optional[Dict[str, Any]] = None
    task_id: Optional[str] = None