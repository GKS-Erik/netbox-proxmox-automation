from __future__ import annotations

from typing import TYPE_CHECKING

from models.operations import Operation, OperationResult
from models.webhook import DiskEvent, EventType, VirtualMachine, VirtualMachineEvent, WebhookEvent

from .dispatcher import EventDispatcher

if TYPE_CHECKING:
    from backends import BackendFactory, VirtualizationBackend
    from clients import NetBoxClient


class AutomationService:
    def __init__(
        self,
        backends: BackendFactory,
        netbox: NetBoxClient,
        dispatcher: EventDispatcher | None = None,
    ):
        self.backends = backends
        self.netbox = netbox
        self.dispatcher = dispatcher or EventDispatcher()

    def handle(self, event: WebhookEvent) -> list[OperationResult]:
        if isinstance(event, VirtualMachineEvent):
            return self._handle_vm(event)
        return self._handle_disk(event)

    def mark_failed(self, event: WebhookEvent) -> None:
        if isinstance(event, VirtualMachineEvent):
            # A deleted-event is emitted after the NetBox record has gone. It
            # cannot be marked failed, and an absent Proxmox guest is the
            # desired end state for this operation.
            if event.event is EventType.DELETED:
                return
            vm_id = event.data.id
            event.data.status.value = "failed"
        else:
            vm_id = event.data.virtual_machine.id
        self.netbox.set_vm_status(vm_id, "failed")

    def _handle_vm(self, event: VirtualMachineEvent) -> list[OperationResult]:
        backend = self.backends.for_kind(event.data.kind)
        operations = self.dispatcher.operations_for_vm(event)
        results = [self._execute(backend, operation, event.data) for operation in operations]
        if event.event is EventType.CREATED and Operation.PROVISION in operations:
            self.netbox.set_vm_status(event.data.id, "offline")
            event.data.status.value = "offline"
        return results

    def _handle_disk(self, event: DiskEvent) -> list[OperationResult]:
        vm = self.netbox.get_vm(event.data.virtual_machine.id)
        backend = self.backends.for_kind(vm.kind)
        operations = self.dispatcher.operations_for_disk(event)
        return [self._execute(backend, operation, vm, event) for operation in operations]

    @staticmethod
    def _execute(
        backend: VirtualizationBackend,
        operation: Operation,
        vm: VirtualMachine,
        disk_event: DiskEvent | None = None,
    ) -> OperationResult:
        if operation is Operation.PROVISION:
            return backend.provision(vm)
        if operation is Operation.UPDATE_RESOURCES:
            return backend.update_resources(vm)
        if operation is Operation.CONFIGURE_NETWORK:
            return backend.configure_network(vm)
        if operation is Operation.CONFIGURE_SSH_KEY:
            return backend.configure_ssh_key(vm)
        if operation is Operation.START:
            return backend.start(vm)
        if operation is Operation.STOP:
            return backend.stop(vm)
        if operation is Operation.MIGRATE:
            return backend.migrate(vm)
        if operation is Operation.DELETE:
            return backend.delete(vm)
        if disk_event is None:
            raise ValueError(f"Operation {operation} requires a disk event")
        if operation is Operation.ADD_DISK:
            return backend.add_disk(vm, disk_event.data)
        if operation is Operation.RESIZE_DISK:
            return backend.resize_disk(vm, disk_event.data)
        if operation is Operation.DELETE_DISK:
            return backend.delete_disk(vm, disk_event.data)
        raise ValueError(f"Unsupported operation: {operation}")
