from clients import NetBoxClient, ProxmoxClient
from config import ProxmoxConfig
from models.webhook import GuestKind

from .base import VirtualizationBackend
from .lxc import LxcBackend
from .qemu import QemuBackend


class BackendFactory:
    def __init__(self, proxmox: ProxmoxClient, netbox: NetBoxClient, config: ProxmoxConfig):
        self._backends: dict[GuestKind, VirtualizationBackend] = {
            GuestKind.QEMU: QemuBackend(proxmox, netbox, config),
            GuestKind.LXC: LxcBackend(proxmox, netbox, config),
        }

    def for_kind(self, kind: GuestKind) -> VirtualizationBackend:
        return self._backends[kind]
