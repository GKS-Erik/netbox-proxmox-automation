from __future__ import annotations

from typing import Any

import pynetbox

from config import NetBoxConfig
from models.webhook import VirtualMachine


class NetBoxClient:
    def __init__(self, config: NetBoxConfig, api: Any | None = None):
        self.config = config
        self.api = api or pynetbox.api(config.url, token=config.api_token)
        self.api.http_session.verify = config.verify_ssl

    def get_vm(self, vm_id: int) -> VirtualMachine:
        record = self.api.virtualization.virtual_machines.get(id=vm_id)
        if not record:
            raise LookupError(f"Virtual machine {vm_id} was not found in NetBox")
        payload = dict(record)
        for field in ("device", "status"):
            value = payload.get(field)
            if value is not None and not isinstance(value, (dict, str, int)):
                payload[field] = dict(value)
        if isinstance(payload.get("status"), str):
            payload["status"] = {"value": payload["status"]}
        return VirtualMachine.model_validate(payload)

    def set_vm_vmid(self, vm_id: int, vmid: int) -> None:
        record = self.api.virtualization.virtual_machines.get(id=vm_id)
        if not record:
            raise LookupError(f"Virtual machine {vm_id} was not found in NetBox")
        record.serial = str(vmid)
        record.save()

    def create_root_disk(self, vm_id: int, name: str, config: str) -> None:
        disk_info, *options = config.split(",")
        storage = disk_info.split(":", 1)[0]
        size_option = next((option for option in options if option.startswith("size=")), None)
        if not size_option:
            raise ValueError(f"Proxmox disk configuration contains no size: {config}")
        size_value = size_option.removeprefix("size=")
        if size_value.endswith("G"):
            size_mb = int(size_value[:-1]) * 1024
        elif size_value.endswith("M"):
            size_mb = int(size_value[:-1])
        else:
            raise ValueError(f"Unsupported Proxmox disk size: {size_value}")
        self.api.virtualization.virtual_disks.create(
            virtual_machine=vm_id,
            name=name,
            size=size_mb,
            custom_fields={"proxmox_disk_storage_volume": storage},
        )
