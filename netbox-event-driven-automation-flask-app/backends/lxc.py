from __future__ import annotations

from backends.base import UnsupportedOperationError, VirtualizationBackend
from models.operations import Operation, OperationResult
from models.webhook import GuestKind, VirtualDisk, VirtualMachine


class LxcBackend(VirtualizationBackend):
    kind = GuestKind.LXC

    def provision(self, vm: VirtualMachine) -> OperationResult:
        template = vm.custom_fields.proxmox_lxc_template
        storage = vm.custom_fields.proxmox_lxc_storage
        if not template or not storage or vm.vcpus is None or vm.memory is None:
            raise ValueError("LXC provisioning requires template, storage, vcpus and memory")
        vmid = vm.serial or self.proxmox.next_vmid()
        data = {
            "vmid": vmid,
            "hostname": vm.name,
            "ostemplate": template,
            "cores": int(vm.vcpus),
            "memory": vm.memory,
            "storage": storage,
            "onboot": 1,
            "unprivileged": 1,
            "swap": 0,
        }
        ssh_key = vm.custom_fields.proxmox_public_ssh_key
        if ssh_key:
            data["ssh-public-keys"] = ssh_key
        if self.config.lxc_default_password:
            data["password"] = self.config.lxc_default_password
        if not ssh_key and not self.config.lxc_default_password:
            raise ValueError("LXC provisioning requires an SSH key or configured lxc_default_password")
        guest = self.proxmox.create_lxc(self.target_node(vm), data)
        self.netbox.set_vm_vmid(vm.id, guest.vmid)
        vm.serial = guest.vmid
        config = self.proxmox.get_config(guest)
        if "rootfs" in config:
            self.netbox.create_root_disk(vm.id, "rootfs", config["rootfs"])
        return OperationResult(Operation.PROVISION, f"LXC {vm.name} ({guest.vmid}) provisioned")

    def configure_network(self, vm: VirtualMachine) -> OperationResult:
        if not vm.primary_ip:
            raise ValueError(f"LXC {vm.name} has no primary IP")
        interface = vm.primary_ip.address
        if interface.version != 4:
            raise ValueError("Automatic gateway calculation currently supports IPv4 only")
        gateway = interface.network.network_address + 1
        guest = self.resolve(vm)
        self.proxmox.set_config(
            guest,
            net0=f"name=net0,bridge=vmbr0,ip={interface},gw={gateway},firewall=1",
        )
        return OperationResult(Operation.CONFIGURE_NETWORK, f"Network configured for LXC {guest.vmid}")

    def configure_ssh_key(self, vm: VirtualMachine) -> OperationResult:
        raise UnsupportedOperationError("Changing the SSH key of an existing LXC is not supported")

    def add_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        raise UnsupportedOperationError("Adding additional LXC disks is not supported")

    def resize_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        if disk.name != "rootfs":
            raise UnsupportedOperationError("Only the LXC rootfs disk can be resized")
        guest = self.resolve(vm)
        self.proxmox.resize_disk(guest, "rootfs", disk.size / 1024)
        return OperationResult(Operation.RESIZE_DISK, f"LXC rootfs resized for {guest.vmid}")

    def delete_disk(self, vm: VirtualMachine, disk: VirtualDisk) -> OperationResult:
        raise UnsupportedOperationError("Deleting LXC rootfs is not supported")
