import unittest

from models.operations import Operation, OperationResult
from models.webhook import GuestKind, parse_webhook
from services.vm_service import AutomationService

from tests.test_webhook import vm_payload


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def stop(self, vm):
        self.calls.append(("stop", vm.name))
        return OperationResult(Operation.STOP, "stopped")

    def provision(self, vm):
        self.calls.append(("provision", vm.name))
        vm.serial = 101
        return OperationResult(Operation.PROVISION, "provisioned")

    def update_resources(self, vm):
        self.calls.append(("update_resources", vm.name))
        return OperationResult(Operation.UPDATE_RESOURCES, "resources updated")


class RecordingNetBox:
    def __init__(self):
        self.status_updates = []

    def set_vm_status(self, vm_id, status):
        self.status_updates.append((vm_id, status))


class FakeFactory:
    def __init__(self):
        self.qemu = RecordingBackend()
        self.lxc = RecordingBackend()
        self.requested_kinds = []

    def for_kind(self, kind):
        self.requested_kinds.append(kind)
        return self.qemu if kind is GuestKind.QEMU else self.lxc


class AutomationServiceTests(unittest.TestCase):
    def test_selects_backend_once_then_uses_common_operation(self):
        factory = FakeFactory()
        service = AutomationService(factory, netbox=None)
        event = parse_webhook(vm_payload())

        result = service.handle(event)

        self.assertEqual(factory.requested_kinds, [GuestKind.QEMU])
        self.assertEqual(factory.qemu.calls, [("stop", "example-vm")])
        self.assertEqual(result[0].operation, Operation.STOP)

    def test_same_decision_tree_selects_lxc_backend(self):
        factory = FakeFactory()
        service = AutomationService(factory, netbox=None)
        payload = vm_payload(custom_fields={"proxmox_vm_type": "lxc"})
        event = parse_webhook(payload)

        service.handle(event)

        self.assertEqual(factory.requested_kinds, [GuestKind.LXC])
        self.assertEqual(factory.lxc.calls, [("stop", "example-vm")])

    def test_successful_provisioning_sets_netbox_status_offline_last(self):
        factory = FakeFactory()
        netbox = RecordingNetBox()
        service = AutomationService(factory, netbox=netbox)
        payload = vm_payload(
            status={"value": "staged"},
            serial=None,
            custom_fields={
                "proxmox_vm_type": "vm",
                "proxmox_vm_templates": 9000,
                "proxmox_vm_storage": "local-lvm",
            },
        )
        payload["event"] = "created"
        payload["snapshots"] = {
            "prechange": None,
            "postchange": {"status": "staged", "device": 7},
        }
        event = parse_webhook(payload)

        results = service.handle(event)

        self.assertEqual(
            factory.qemu.calls,
            [("provision", "example-vm"), ("update_resources", "example-vm")],
        )
        self.assertEqual(netbox.status_updates, [(42, "offline")])
        self.assertEqual(event.data.status.value, "offline")
        self.assertEqual(
            [result.operation for result in results],
            [Operation.PROVISION, Operation.UPDATE_RESOURCES],
        )


if __name__ == "__main__":
    unittest.main()
