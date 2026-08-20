from .operations import Operation, OperationResult
from .templates import ProxmoxTemplate, TemplateSyncResult
from .webhook import (
    DiskEvent,
    GuestKind,
    VirtualMachine,
    VirtualMachineEvent,
    parse_webhook,
)

__all__ = [
    "DiskEvent",
    "GuestKind",
    "Operation",
    "OperationResult",
    "ProxmoxTemplate",
    "TemplateSyncResult",
    "VirtualMachine",
    "VirtualMachineEvent",
    "parse_webhook",
]
