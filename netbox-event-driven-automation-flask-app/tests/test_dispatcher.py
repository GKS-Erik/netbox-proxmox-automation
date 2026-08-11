import unittest

from models.operations import Operation
from models.webhook import parse_webhook
from services.dispatcher import EventDispatcher

from tests.test_webhook import vm_payload


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.dispatcher = EventDispatcher()

    def test_status_change_to_offline_stops_vm(self):
        event = parse_webhook(vm_payload())

        self.assertEqual(self.dispatcher.operations_for_vm(event), [Operation.STOP])

    def test_node_change_uses_single_shared_migration_decision(self):
        payload = vm_payload(
            status={"value": "active"},
            device={"id": 8, "name": "pve-02"},
        )
        payload["snapshots"]["prechange"] = {"status": "active", "device": 7}
        event = parse_webhook(payload)

        self.assertEqual(self.dispatcher.operations_for_vm(event), [Operation.MIGRATE])

    def test_simultaneous_start_and_node_change_starts_before_migration(self):
        payload = vm_payload(
            status={"value": "active"},
            device={"id": 8, "name": "pve-02"},
        )
        payload["snapshots"]["prechange"] = {"status": "offline", "device": 7}
        event = parse_webhook(payload)

        self.assertEqual(
            self.dispatcher.operations_for_vm(event),
            [Operation.START, Operation.MIGRATE],
        )

    def test_staged_qemu_configuration_is_composed(self):
        payload = vm_payload(
            status={"value": "staged"},
            primary_ip={"address": "192.0.2.10/24"},
            custom_fields={
                "proxmox_vm_type": "vm",
                "proxmox_public_ssh_key": "ssh-ed25519 AAAA",
            },
        )
        event = parse_webhook(payload)

        self.assertEqual(
            self.dispatcher.operations_for_vm(event),
            [
                Operation.UPDATE_RESOURCES,
                Operation.CONFIGURE_NETWORK,
                Operation.CONFIGURE_SSH_KEY,
            ],
        )


if __name__ == "__main__":
    unittest.main()
