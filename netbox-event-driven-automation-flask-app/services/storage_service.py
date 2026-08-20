from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.storage import StorageSyncResult

if TYPE_CHECKING:
    from clients import NetBoxClient, ProxmoxClient


class NoStorageFoundError(RuntimeError):
    pass


class StorageSyncService:
    def __init__(self, proxmox: ProxmoxClient, netbox: NetBoxClient):
        self.proxmox = proxmox
        self.netbox = netbox

    def sync(self, vm_choice_set_name: str, lxc_choice_set_name: str) -> StorageSyncResult:
        storages = self.proxmox.list_storages()
        vm_storage = sorted(storage.name for storage in storages if "images" in storage.content)
        lxc_storage = sorted(storage.name for storage in storages if "rootdir" in storage.content)
        if not vm_storage and not lxc_storage:
            raise NoStorageFoundError(
                "Proxmox returned no storage supporting images or rootdir; NetBox was not changed"
            )

        vm_created = None
        if vm_storage:
            vm_created = self.netbox.sync_custom_field_choice_set(
                vm_choice_set_name,
                [[name, name] for name in vm_storage],
            )

        lxc_created = None
        if lxc_storage:
            lxc_created = self.netbox.sync_custom_field_choice_set(
                lxc_choice_set_name,
                [[name, name] for name in lxc_storage],
            )

        return StorageSyncResult(
            vm_choice_set_name=vm_choice_set_name,
            lxc_choice_set_name=lxc_choice_set_name,
            vm_storage_count=len(vm_storage),
            lxc_storage_count=len(lxc_storage),
            vm_created=vm_created,
            lxc_created=lxc_created,
        )

    def sync_on_startup(
        self,
        vm_choice_set_name: str,
        lxc_choice_set_name: str,
        logger: logging.Logger,
    ) -> None:
        logger.info("Synchronizing Proxmox storage during service startup")
        try:
            result = self.sync(vm_choice_set_name, lxc_choice_set_name)
        except NoStorageFoundError as exc:
            logger.warning("Startup storage synchronization skipped: %s", exc)
        except Exception:
            logger.exception("Startup storage synchronization failed")
        else:
            self._log_result(result, logger)

    @staticmethod
    def _log_result(result: StorageSyncResult, logger: logging.Logger) -> None:
        for name, count, created, content_type in (
            (result.vm_choice_set_name, result.vm_storage_count, result.vm_created, "images"),
            (result.lxc_choice_set_name, result.lxc_storage_count, result.lxc_created, "rootdir"),
        ):
            if created is None:
                logger.warning(
                    "Choice set %s was not changed: Proxmox returned no %s storage",
                    name,
                    content_type,
                )
                continue
            action = "created" if created else "updated"
            logger.info(
                "Choice set %s %s with %d Proxmox storage entries during service startup",
                name,
                action,
                count,
            )
