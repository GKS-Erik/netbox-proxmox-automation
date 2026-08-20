import logging
import unittest

from models.storage import ProxmoxStorage
from services.storage_service import NoStorageFoundError, StorageSyncService


class FakeProxmox:
    def list_storages(self):
        return [
            ProxmoxStorage("local", frozenset({"iso", "vztmpl"})),
            ProxmoxStorage("local-lvm", frozenset({"images", "rootdir"})),
            ProxmoxStorage("vm-only", frozenset({"images"})),
            ProxmoxStorage("lxc-only", frozenset({"rootdir"})),
        ]


class FakeNetBox:
    def __init__(self):
        self.calls = []

    def sync_custom_field_choice_set(self, name, choices):
        self.calls.append((name, choices))
        return False


class StorageSyncServiceTests(unittest.TestCase):
    def test_syncs_storage_name_as_value_and_label_by_content_type(self):
        netbox = FakeNetBox()
        service = StorageSyncService(FakeProxmox(), netbox)

        result = service.sync("VM Storage", "LXC Storage")

        self.assertEqual(
            netbox.calls,
            [
                ("VM Storage", [["local-lvm", "local-lvm"], ["vm-only", "vm-only"]]),
                ("LXC Storage", [["local-lvm", "local-lvm"], ["lxc-only", "lxc-only"]]),
            ],
        )
        self.assertEqual(result.vm_storage_count, 2)
        self.assertEqual(result.lxc_storage_count, 2)

    def test_missing_category_does_not_clear_its_choice_set(self):
        proxmox = FakeProxmox()
        proxmox.list_storages = lambda: [
            ProxmoxStorage("vm-only", frozenset({"images"}))
        ]
        netbox = FakeNetBox()
        service = StorageSyncService(proxmox, netbox)

        result = service.sync("VM Storage", "LXC Storage")

        self.assertEqual(netbox.calls, [("VM Storage", [["vm-only", "vm-only"]])])
        self.assertIsNone(result.lxc_created)

    def test_empty_inventory_does_not_change_netbox(self):
        proxmox = FakeProxmox()
        proxmox.list_storages = lambda: []
        netbox = FakeNetBox()
        service = StorageSyncService(proxmox, netbox)

        with self.assertRaises(NoStorageFoundError):
            service.sync("VM Storage", "LXC Storage")

        self.assertEqual(netbox.calls, [])

    def test_startup_sync_calls_regular_synchronization(self):
        netbox = FakeNetBox()
        service = StorageSyncService(FakeProxmox(), netbox)

        service.sync_on_startup("VM Storage", "LXC Storage", logging.getLogger("test"))

        self.assertEqual(len(netbox.calls), 2)


if __name__ == "__main__":
    unittest.main()
