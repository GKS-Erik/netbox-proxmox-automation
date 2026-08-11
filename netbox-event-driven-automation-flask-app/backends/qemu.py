from __future__ import annotations

import urllib.parse

from backends.base import VirtualizationBackend
from models.operations import Operation, OperationResult
from models.webhook import GuestKind, VirtualDisk, VirtualMachine


class QemuBackend(VirtualizationBackend):
    kind = GuestKind.QEMU

    def provision(self, vm: VirtualMachine) -> OperationResult:
        template = vm.custom_fields.proxmox_vm_templates
        storage = vm.custom_fields.proxmox_vm_storage
        if template is None or not storage:
            raise ValueError("QEMU provisioning requires proxmox_vm_templates and proxmox_vm_storage")
        vmid = vm.serial or self.proxmox.next_vmid()
        guest = self.proxmox.clone_qemu(
            template_vmid=template,
            new_vmid=vmid,
            name=vm.name,
            target_node=self.target_node(vm),
            storage=storage,
        )
        self.netbox.set_vm_vmid(vm.id, guest.vmid)
        vm.serial = guest.vmid
        config = self.proxmox.get_config(guest)
        boot_disk = config.get("bootdisk")
        if boot_disk and boot_disk in config:
            self.netbox.create_root_disk(vm.id, boot_disk, config[boot_disk])
        return OperationResult(Operation.PROVISION, f"QEMU VM {vm.name} ({guest.vmid}) provisioned")

    def configure_network(self, vm: VirtualMachine) -> OperationResult:
        if not vm.primary_ip:
            raise ValueError(f"VM {vm.name} has no primary IP")
        interface = vm.primary_ip.address
        if interface.version != 4:
            raise ValueError("Automatic gateway calculation currently supports IPv4 only")
        gateway = interface.network.network_address + 1
        guest = self.resolve(vm)
        self.proxmox.set_config(guest, ipconfig0=f"ip={interface},gw={gateway}")
        return OperationResult(Operation.CONFIGURE_NETWORK, f"Cloud-init network configured for {guest.vmid}")

    def configure_ssh_key(self, vm: VirtualMachine) -> OperationResult:
        key = vm.custom_fields.proxmox_public_ssh_key
        if not key:
            raise ValueError(f"VM {vm.name} has no proxmox_public_ssh_key")
        guest = self.resolve(vm)
        encoded_key = urllib.parse.quote(key.rstrip(), safe="")
        self.proxmox.set_config(guest, sshkeys=encoded_key)
        return OperationResult(Operation.CONFIGURE_SSH_KEY, f"SSH key configured for {guest.vmid}")

    def add_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        if disk.name == "scsi0":
            return self.resize_disk(vm, disk)
        storage = disk.custom_fields.get("proxmox_disk_storage_volume")
        if not storage:
            raise ValueError(f"Disk {disk.name} has no proxmox_disk_storage_volume")
        guest = self.resolve(vm)
        self.proxmox.add_qemu_disk(guest, disk.name, storage, disk.size / 1024)
        return OperationResult(Operation.ADD_DISK, f"Disk {disk.name} added to {guest.vmid}")

    def resize_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        guest = self.resolve(vm)
        self.proxmox.resize_disk(guest, disk.name, disk.size / 1024)
        return OperationResult(Operation.RESIZE_DISK, f"Disk {disk.name} resized for {guest.vmid}")

    def delete_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        if disk.name == "scsi0":
            raise ValueError("The QEMU OS disk cannot be deleted")
        guest = self.resolve(vm)
        self.proxmox.delete_qemu_disk(guest, disk.name)
        return OperationResult(Operation.DELETE_DISK, f"Disk {disk.name} deleted from {guest.vmid}")
