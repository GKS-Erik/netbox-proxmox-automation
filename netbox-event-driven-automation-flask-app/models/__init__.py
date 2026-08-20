from .operations import Operation, OperationResult
from .templates import ProxmoxTemplate, TemplateSyncResult
from .storage import ProxmoxStorage, StorageSyncResult
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
    "ProxmoxStorage",
    "StorageSyncResult",
    "TemplateSyncResult",
    "VirtualMachine",
    "VirtualMachineEvent",
    "parse_webhook",
]
