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


if __name__ == "__main__":
    unittest.main()
