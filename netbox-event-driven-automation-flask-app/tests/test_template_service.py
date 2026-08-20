import unittest
import logging

from models.templates import ProxmoxTemplate
from services.template_service import NoTemplatesFoundError, TemplateSyncService


class FakeProxmox:
    def list_qemu_templates(self):
        return [
            ProxmoxTemplate(vmid=9000, name="Ubuntu 24.04", node="pve-01"),
            ProxmoxTemplate(vmid=9001, name="Debian 13", node="pve-02"),
        ]


class FakeNetBox:
    def __init__(self, created=False):
        self.created = created
        self.calls = []

    def sync_custom_field_choice_set(self, name, choices):
        self.calls.append((name, choices))
        return self.created


class TemplateSyncServiceTests(unittest.TestCase):
    def test_syncs_vmid_as_value_and_name_as_label(self):
        netbox = FakeNetBox(created=True)
        service = TemplateSyncService(FakeProxmox(), netbox)

        result = service.sync("Proxmox templates")

        self.assertEqual(
            netbox.calls,
            [
                (
                    "Proxmox templates",
                    [["9000", "Ubuntu 24.04"], ["9001", "Debian 13"]],
                )
            ],
        )
        self.assertTrue(result.created)
        self.assertEqual(result.template_count, 2)

    def test_empty_inventory_does_not_change_netbox(self):
        proxmox = FakeProxmox()
        proxmox.list_qemu_templates = lambda: []
        netbox = FakeNetBox(created=False)
        service = TemplateSyncService(proxmox, netbox)

        with self.assertRaises(NoTemplatesFoundError):
            service.sync("My templates")

        self.assertEqual(netbox.calls, [])

    def test_startup_sync_runs_without_propagating_empty_inventory(self):
        proxmox = FakeProxmox()
        proxmox.list_qemu_templates = lambda: []
        netbox = FakeNetBox()
        service = TemplateSyncService(proxmox, netbox)

        service.sync_on_startup("Proxmox templates", logging.getLogger("test"))

        self.assertEqual(netbox.calls, [])

    def test_startup_sync_calls_regular_synchronization(self):
        netbox = FakeNetBox()
        service = TemplateSyncService(FakeProxmox(), netbox)

        service.sync_on_startup("Proxmox templates", logging.getLogger("test"))

        self.assertEqual(len(netbox.calls), 1)


if __name__ == "__main__":
    unittest.main()
