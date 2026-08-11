from models.operations import Operation
from models.webhook import DiskEvent, EventType, GuestKind, VirtualMachineEvent


class EventDispatcher:
    """Maps desired NetBox state to backend-neutral operations."""

    def operations_for_vm(self, event: VirtualMachineEvent) -> list[Operation]:
        vm = event.data

        if event.event is EventType.DELETED:
            return [Operation.DELETE]

        if event.event is EventType.CREATED:
            if vm.status.value != "staged":
                return []
            operations = [Operation.PROVISION]
            if vm.vcpus is not None and vm.memory is not None:
                operations.append(Operation.UPDATE_RESOURCES)
            return operations

        if event.event is not EventType.UPDATED:
            return []

        if vm.status.value == "staged":
            operations = []
            if vm.vcpus is not None and vm.memory is not None:
                operations.append(Operation.UPDATE_RESOURCES)
            if vm.primary_ip:
                operations.append(Operation.CONFIGURE_NETWORK)
            if vm.kind is GuestKind.QEMU and vm.custom_fields.proxmox_public_ssh_key:
                operations.append(Operation.CONFIGURE_SSH_KEY)
            return operations

        status_changed = bool(
            event.snapshots and event.snapshots.prechange.status != vm.status.value
        )
        node_changed = bool(
            event.snapshots
            and vm.device
            and event.snapshots.prechange.device != vm.device.id
        )

        if vm.status.value == "active":
            if node_changed:
                operations = [Operation.START] if status_changed else []
                operations.append(Operation.MIGRATE)
                return operations
            return [Operation.START] if status_changed else []

        if vm.status.value == "offline":
            operations = [Operation.STOP] if status_changed else []
            if node_changed:
                operations.append(Operation.MIGRATE)
            return operations

        return []

    def operations_for_disk(self, event: DiskEvent) -> list[Operation]:
        if event.event is EventType.CREATED:
            return [Operation.ADD_DISK]
        if event.event is EventType.DELETED:
            return [Operation.DELETE_DISK]
        if event.event is EventType.UPDATED:
            if not event.snapshots or event.snapshots.prechange.size != event.snapshots.postchange.size:
                return [Operation.RESIZE_DISK]
        return []
