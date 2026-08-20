from __future__ import annotations

from enum import Enum
from typing import Any, Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, IPvAnyInterface, field_validator, model_validator


def _empty_to_none(value: Any) -> Any:
    return None if value in ("", None) else value


OptionalInt = Annotated[int | None, BeforeValidator(_empty_to_none)]


class GuestKind(str, Enum):
    QEMU = "vm"
    LXC = "lxc"

    @property
    def proxmox_type(self) -> str:
        return "qemu" if self is GuestKind.QEMU else "lxc"


class EventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class DeviceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None
    display: str | None = None

    @property
    def proxmox_name(self) -> str:
        name = self.name or self.display
        if not name:
            raise ValueError("NetBox device has no name usable as a Proxmox node")
        return name


class StatusRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str
    label: str | None = None


class IpRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address: IPvAnyInterface


class VmCustomFields(BaseModel):
    model_config = ConfigDict(extra="allow")

    proxmox_vm_type: GuestKind = GuestKind.QEMU
    proxmox_vm_template: OptionalInt = None
    proxmox_lxc_template: str | None = None
    proxmox_vm_storage: str | None = None
    proxmox_lxc_storage: str | None = None
    proxmox_public_ssh_key: str | None = None

    @field_validator("proxmox_vm_type", mode="before")
    @classmethod
    def default_empty_type_to_qemu(cls, value: Any) -> Any:
        return GuestKind.QEMU if value in (None, "") else value


class VirtualMachine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    status: StatusRef
    serial: OptionalInt = None
    device: DeviceRef | None = None
    vcpus: float | None = None
    memory: int | None = None
    primary_ip: IpRef | None = None
    tenant: Any = None
    custom_fields: VmCustomFields = Field(default_factory=VmCustomFields)

    @property
    def kind(self) -> GuestKind:
        return self.custom_fields.proxmox_vm_type

    @property
    def desired_node(self) -> str | None:
        return self.device.proxmox_name if self.device else None


class VmSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = None
    device: int | None = None
    vcpus: float | None = None
    memory: int | None = None


class Snapshots(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prechange: VmSnapshot | None = None
    postchange: VmSnapshot | None = None


class VirtualMachineEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object_type: Literal["virtualmachine"] = "virtualmachine"
    event: EventType
    data: VirtualMachine
    snapshots: Snapshots | None = None

    @model_validator(mode="after")
    def updated_event_requires_prechange(self) -> "VirtualMachineEvent":
        if self.event is EventType.UPDATED and (
            self.snapshots is None or self.snapshots.prechange is None
        ):
            raise ValueError("Updated VM event requires a prechange snapshot")
        return self


class VirtualMachineRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None


class VirtualDisk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str
    size: int
    virtual_machine: VirtualMachineRef
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class DiskSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    size: int | None = None


class DiskSnapshots(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prechange: DiskSnapshot | None = None
    postchange: DiskSnapshot | None = None


class DiskEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object_type: Literal["virtualdisk"] = "virtualdisk"
    event: EventType
    data: VirtualDisk
    snapshots: DiskSnapshots | None = None

    @model_validator(mode="after")
    def updated_event_requires_snapshots(self) -> "DiskEvent":
        if self.event is EventType.UPDATED and (
            self.snapshots is None
            or self.snapshots.prechange is None
            or self.snapshots.postchange is None
        ):
            raise ValueError("Updated disk event requires prechange and postchange snapshots")
        return self


WebhookEvent = VirtualMachineEvent | DiskEvent


class WebhookEnvelope(BaseModel):
    """Normalizes NetBox's old `model` and new `object_type` webhook formats."""

    model_config = ConfigDict(extra="allow")

    event: EventType
    data: dict[str, Any]
    snapshots: dict[str, Any] | None = None
    model: str | None = None
    object_type: str | None = None

    @model_validator(mode="after")
    def determine_object_type(self) -> "WebhookEnvelope":
        value = self.model or self.object_type
        if not value:
            raise ValueError("Webhook contains neither model nor object_type")
        self.object_type = value.rsplit(".", 1)[-1].lower()
        return self


def parse_webhook(payload: Any) -> WebhookEvent:
    envelope = WebhookEnvelope.model_validate(payload)
    normalized = {
        "object_type": envelope.object_type,
        "event": envelope.event,
        "data": envelope.data,
        "snapshots": envelope.snapshots,
    }
    if envelope.object_type == "virtualmachine":
        return VirtualMachineEvent.model_validate(normalized)
    if envelope.object_type == "virtualdisk":
        return DiskEvent.model_validate(normalized)
    raise ValueError(f"Unsupported NetBox object type: {envelope.object_type}")
