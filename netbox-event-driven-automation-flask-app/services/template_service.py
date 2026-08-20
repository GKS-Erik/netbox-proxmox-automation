from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.templates import TemplateSyncResult

if TYPE_CHECKING:
    from clients import NetBoxClient, ProxmoxClient


class NoTemplatesFoundError(RuntimeError):
    pass


class TemplateSyncService:
    def __init__(self, proxmox: ProxmoxClient, netbox: NetBoxClient):
        self.proxmox = proxmox
        self.netbox = netbox

    def sync(self, choice_set_name: str) -> TemplateSyncResult:
        templates = self.proxmox.list_qemu_templates()
        if not templates:
            raise NoTemplatesFoundError("Proxmox returned no QEMU templates; NetBox was not changed")
        choices = [[str(template.vmid), template.name] for template in templates]
        created = self.netbox.sync_custom_field_choice_set(choice_set_name, choices)
        return TemplateSyncResult(
            choice_set_name=choice_set_name,
            template_count=len(templates),
            created=created,
        )

    def sync_on_startup(self, choice_set_name: str, logger: logging.Logger) -> None:
        logger.info("Synchronizing Proxmox templates during service startup")
        try:
            result = self.sync(choice_set_name)
        except NoTemplatesFoundError as exc:
            logger.warning("Startup template synchronization skipped: %s", exc)
        except Exception:
            logger.exception("Startup template synchronization failed")
        else:
            action = "created" if result.created else "updated"
            logger.info(
                "Choice set %s %s with %d Proxmox templates during service startup",
                result.choice_set_name,
                action,
                result.template_count,
            )
