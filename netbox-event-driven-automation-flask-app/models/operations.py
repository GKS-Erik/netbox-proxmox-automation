from dataclasses import dataclass
from enum import Enum


class Operation(str, Enum):
    PROVISION = "provision"
    UPDATE_RESOURCES = "update_resources"
    CONFIGURE_NETWORK = "configure_network"
    CONFIGURE_SSH_KEY = "configure_ssh_key"
    START = "start"
    STOP = "stop"
    MIGRATE = "migrate"
    DELETE = "delete"
    ADD_DISK = "add_disk"
    RESIZE_DISK = "resize_disk"
    DELETE_DISK = "delete_disk"


@dataclass(frozen=True)
class OperationResult:
    operation: Operation
    message: str
