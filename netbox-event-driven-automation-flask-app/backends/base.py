from __future__ import annotations

from abc import ABC, abstractmethod

from clients import GuestNotFoundError, NetBoxClient, ProxmoxClient, ResolvedGuest
from config import ProxmoxConfig
from models.operations import Operation, OperationResult
from models.webhook import GuestKind, VirtualDisk, VirtualMachine


class UnsupportedOperationError(RuntimeError):
    pass


class VirtualizationBackend(ABC):
    """Common orchestration contract for QEMU and LXC workloads."""

    kind: GuestKind

    def __init__(self, proxmox: ProxmoxClient, netbox: NetBoxClient, config: ProxmoxConfig):
        self.proxmox = proxmox
        self.netbox = netbox
        self.config = config

    def _vmid(self, vm: VirtualMachine) -> int:
        if vm.serial is None:
            raise ValueError(f"VM {vm.name} has no Proxmox VMID in NetBox serial")
        return vm.serial

    def resolve(self, vm: VirtualMachine) -> ResolvedGuest:
        return self.proxmox.resolve_guest(self._vmid(vm), self.kind)

    def target_node(self, vm: VirtualMachine) -> str:
        node = vm.desired_node or self.config.default_node
        if not node:
            raise ValueError(
                f"VM {vm.name} has no assigned NetBox device and no proxmox_api_config.default_node"
            )
        return node

    @abstractmethod
    def provision(self, vm: VirtualMachine) -> OperationResult:
        ...

    def start(self, vm: VirtualMachine) -> OperationResult:
        guest = self.resolve(vm)
        self.proxmox.start(guest)
        return OperationResult(Operation.START, f"{self.kind.value} {guest.vmid} started")

    def stop(self, vm: VirtualMachine) -> OperationResult:
        guest = self.resolve(vm)
        self.proxmox.stop(guest)
        return OperationResult(Operation.STOP, f"{self.kind.value} {guest.vmid} stopped")

    def delete(self, vm: VirtualMachine) -> OperationResult:
        try:
            guest = self.resolve(vm)
        except GuestNotFoundError:
            return OperationResult(
                Operation.DELETE,
                f"{self.kind.value} {self._vmid(vm)} was already absent from Proxmox",
            )
        self.proxmox.delete(guest)
        return OperationResult(Operation.DELETE, f"{self.kind.value} {guest.vmid} deleted")

    def migrate(self, vm: VirtualMachine) -> OperationResult:
        guest = self.resolve(vm)
        target = self.target_node(vm)
        self.proxmox.migrate(guest, target, online=vm.status.value == "active")
        return OperationResult(Operation.MIGRATE, f"{self.kind.value} {guest.vmid} migrated to {target}")

    def update_resources(self, vm: VirtualMachine) -> OperationResult:
        if vm.vcpus is None or vm.memory is None:
            raise ValueError(f"VM {vm.name} requires both vcpus and memory")
        guest = self.resolve(vm)
        self.proxmox.update_resources(guest, vm.vcpus, vm.memory)
        return OperationResult(Operation.UPDATE_RESOURCES, f"Resources updated for {guest.vmid}")

    @abstractmethod
    def configure_network(self, vm: VirtualMachine) -> OperationResult:
        ...

    def configure_ssh_key(self, vm: VirtualMachine) -> OperationResult:
        raise UnsupportedOperationError(f"{self.kind.value} does not support SSH-key reconfiguration")

    @abstractmethod
    def add_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        ...

    @abstractmethod
    def resize_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        ...

    @abstractmethod
    def delete_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        ...
