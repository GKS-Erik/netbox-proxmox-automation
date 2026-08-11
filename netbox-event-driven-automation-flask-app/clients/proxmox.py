from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Any, Callable

from proxmoxer import ProxmoxAPI

from config import ProxmoxConfig
from logging_utils import log_payload
from models.webhook import GuestKind


class GuestNotFoundError(RuntimeError):
    pass


class ProxmoxTaskError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedGuest:
    vmid: int
    name: str
    kind: GuestKind
    node: str
    status: str | None = None


class ProxmoxClient:
    """Small typed facade around proxmoxer and its dynamic endpoint objects."""

    def __init__(
        self,
        config: ProxmoxConfig,
        api: Any | None = None,
        debug: bool | Callable[[], bool] = False,
    ):
        self.config = config
        self._debug = debug
        self._logger = logging.getLogger("netbox-proxmox-webhook-listener.proxmox")
        self.api = api or ProxmoxAPI(
            config.api_host,
            port=config.api_port,
            user=config.api_user,
            token_name=config.api_token_id,
            token_value=config.api_token_secret,
            verify_ssl=config.verify_ssl,
            timeout=30,
        )

    @property
    def payload_logging_enabled(self) -> bool:
        debug = self._debug() if callable(self._debug) else self._debug
        return bool(debug and self.config.debug_payloads)

    def _log(self, message: str, payload: Any) -> None:
        log_payload(self._logger, self.payload_logging_enabled, message, payload)

    def resolve_guest(self, vmid: int, kind: GuestKind | None = None) -> ResolvedGuest:
        self._log("Proxmox request cluster/resources", {"type": "vm", "vmid": vmid})
        resources = self.api.cluster.resources.get(type="vm")
        self._log("Proxmox response cluster/resources", resources)
        for resource in resources:
            if resource.get("type") not in ("qemu", "lxc"):
                continue
            resource_kind = GuestKind.QEMU if resource["type"] == "qemu" else GuestKind.LXC
            if int(resource["vmid"]) == int(vmid) and (kind is None or resource_kind is kind):
                return ResolvedGuest(
                    vmid=int(resource["vmid"]),
                    name=resource.get("name", str(vmid)),
                    kind=resource_kind,
                    node=resource["node"],
                    status=resource.get("status"),
                )
        raise GuestNotFoundError(f"{kind or 'guest'} {vmid} was not found in Proxmox")

    def next_vmid(self) -> int:
        self._log("Proxmox request cluster/nextid", {})
        vmid = int(self.api.cluster.get("nextid"))
        self._log("Proxmox response cluster/nextid", {"vmid": vmid})
        return vmid

    def wait_for_task(self, node: str, upid: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.task_timeout_seconds
        while time.monotonic() < deadline:
            status = self.api.nodes(node).tasks(upid).status.get()
            self._log("Proxmox response task status", status)
            if status.get("status") == "stopped":
                if status.get("exitstatus") != "OK":
                    raise ProxmoxTaskError(
                        f"Proxmox task {upid} failed: {status.get('exitstatus', 'unknown exit status')}"
                    )
                return status
            time.sleep(1)
        raise TimeoutError(
            f"Proxmox task {upid} did not finish within {self.config.task_timeout_seconds} seconds"
        )

    def _endpoint(self, guest: ResolvedGuest) -> Any:
        node = self.api.nodes(guest.node)
        return node.qemu(guest.vmid) if guest.kind is GuestKind.QEMU else node.lxc(guest.vmid)

    def start(self, guest: ResolvedGuest) -> None:
        if guest.status == "running":
            return
        self._log("Proxmox request start", guest)
        upid = self._endpoint(guest).status.start.post()
        self._log("Proxmox response start", {"upid": upid})
        self.wait_for_task(guest.node, upid)

    def stop(self, guest: ResolvedGuest) -> None:
        if guest.status == "stopped":
            return
        self._log("Proxmox request stop", guest)
        upid = self._endpoint(guest).status.stop.post()
        self._log("Proxmox response stop", {"upid": upid})
        self.wait_for_task(guest.node, upid)

    def delete(self, guest: ResolvedGuest) -> None:
        if guest.status == "running":
            self.stop(guest)
        self._log("Proxmox request delete", guest)
        upid = self._endpoint(guest).delete()
        self._log("Proxmox response delete", {"upid": upid})
        self.wait_for_task(guest.node, upid)

    def update_resources(self, guest: ResolvedGuest, vcpus: float, memory_mb: int) -> None:
        self._log(
            "Proxmox request update resources",
            {"guest": guest, "cores": int(vcpus), "memory": int(memory_mb)},
        )
        method = self._endpoint(guest).config.post if guest.kind is GuestKind.QEMU else self._endpoint(guest).config.put
        upid = method(cores=int(vcpus), memory=int(memory_mb))
        self._log("Proxmox response update resources", {"upid": upid})
        if upid:
            self.wait_for_task(guest.node, upid)

    def migrate(self, guest: ResolvedGuest, target_node: str, online: bool) -> None:
        if guest.node == target_node:
            return
        payload = {"guest": guest, "target": target_node, "online": int(online)}
        self._log("Proxmox request migrate", payload)
        upid = self._endpoint(guest).migrate.post(target=target_node, online=int(online))
        self._log("Proxmox response migrate", {"upid": upid})
        self.wait_for_task(guest.node, upid)

    def clone_qemu(
        self,
        template_vmid: int,
        new_vmid: int,
        name: str,
        target_node: str,
        storage: str,
    ) -> ResolvedGuest:
        template = self.resolve_guest(template_vmid, GuestKind.QEMU)
        payload = {
            "newid": new_vmid,
            "full": 1,
            "name": name,
            "storage": storage,
            "target": target_node,
        }
        self._log("Proxmox request clone QEMU", {"template": template, **payload})
        upid = self.api.nodes(template.node).qemu(template.vmid).clone.post(
            **payload,
        )
        self._log("Proxmox response clone QEMU", {"upid": upid})
        self.wait_for_task(template.node, upid)
        return self.resolve_guest(new_vmid, GuestKind.QEMU)

    def create_lxc(self, node: str, data: dict[str, Any]) -> ResolvedGuest:
        self._log("Proxmox request create LXC", {"node": node, **data})
        upid = self.api.nodes(node).lxc.create(**data)
        self._log("Proxmox response create LXC", {"upid": upid})
        self.wait_for_task(node, upid)
        return self.resolve_guest(int(data["vmid"]), GuestKind.LXC)

    def get_config(self, guest: ResolvedGuest) -> dict[str, Any]:
        self._log("Proxmox request guest config", guest)
        config = self._endpoint(guest).config.get()
        self._log("Proxmox response guest config", config)
        return config

    def set_config(self, guest: ResolvedGuest, **data: Any) -> None:
        self._log("Proxmox request set guest config", {"guest": guest, "data": data})
        method = self._endpoint(guest).config.post if guest.kind is GuestKind.QEMU else self._endpoint(guest).config.put
        upid = method(**data)
        self._log("Proxmox response set guest config", {"upid": upid})
        if upid:
            self.wait_for_task(guest.node, upid)

    def resize_disk(self, guest: ResolvedGuest, disk: str, size_gb: float) -> None:
        self._log(
            "Proxmox request resize disk",
            {"guest": guest, "disk": disk, "size": f"{size_gb}G"},
        )
        upid = self._endpoint(guest).resize.put(disk=disk, size=f"{size_gb}G")
        self._log("Proxmox response resize disk", {"upid": upid})
        if upid:
            self.wait_for_task(guest.node, upid)

    def add_qemu_disk(self, guest: ResolvedGuest, disk: str, storage: str, size_gb: float) -> None:
        self.set_config(guest, **{disk: f"{storage}:{size_gb},backup=0,ssd=0"})

    def delete_qemu_disk(self, guest: ResolvedGuest, disk: str) -> None:
        payload = {"guest": guest, "idlist": disk, "force": 1}
        self._log("Proxmox request delete QEMU disk", payload)
        response = self.api.nodes(guest.node).qemu(guest.vmid).unlink.put(idlist=disk, force=1)
        self._log("Proxmox response delete QEMU disk", response)
