from pathlib import Path
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ProxmoxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_host: str
    api_port: int = 8006
    api_user: str
    api_token_id: str
    api_token_secret: str
    verify_ssl: bool = True
    default_node: str | None = Field(
        default=None,
        validation_alias=AliasChoices("default_node", "node"),
    )
    task_timeout_seconds: int = Field(default=600, gt=0)
    lxc_default_password: str | None = None


class NetBoxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_proto: str = "https"
    api_host: str
    api_port: int = 443
    api_token: str
    verify_ssl: bool = True

    @property
    def url(self) -> str:
        return f"{self.api_proto}://{self.api_host}:{self.api_port}"


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    netbox_webhook_name: str = "netbox-proxmox-webhook"
    proxmox_api_config: ProxmoxConfig
    netbox_api_config: NetBoxConfig


def load_config(path: str | Path) -> AppConfig:
    import yaml

    with Path(path).open(encoding="utf-8") as config_file:
        return AppConfig.model_validate(yaml.safe_load(config_file))
