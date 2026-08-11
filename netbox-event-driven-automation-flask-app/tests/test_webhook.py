import unittest

from pydantic import ValidationError

from models.webhook import GuestKind, VirtualMachineEvent, parse_webhook


def vm_payload(**overrides):
    data = {
        "id": 42,
        "name": "example-vm",
        "status": {"value": "offline"},
        "serial": "101",
        "device": {"id": 7, "name": "pve-01"},
        "vcpus": 2,
        "memory": 2048,
        "custom_fields": {"proxmox_vm_type": "vm"},
    }
    data.update(overrides)
    return {
        "object_type": "virtualization.virtualmachine",
        "event": "updated",
        "data": data,
        "snapshots": {
            "prechange": {"status": "active", "device": 7},
            "postchange": {"status": "offline", "device": 7},
        },
    }


class WebhookParsingTests(unittest.TestCase):
    def test_normalizes_object_type_and_serial(self):
        event = parse_webhook(vm_payload())

        self.assertIsInstance(event, VirtualMachineEvent)
        self.assertEqual(event.data.serial, 101)
        self.assertEqual(event.data.kind, GuestKind.QEMU)
        self.assertEqual(event.data.desired_node, "pve-01")

    def test_accepts_legacy_model_field(self):
        payload = vm_payload()
        payload["model"] = "virtualmachine"
        del payload["object_type"]

        event = parse_webhook(payload)

        self.assertIsInstance(event, VirtualMachineEvent)

    def test_rejects_missing_vmid_shape(self):
        payload = vm_payload(status="offline")

        with self.assertRaises(ValidationError):
            parse_webhook(payload)


if __name__ == "__main__":
    unittest.main()
