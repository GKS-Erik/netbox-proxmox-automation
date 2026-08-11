from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from proxmoxer import ProxmoxAPI

from config import ProxmoxConfig
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

    def __init__(self, config: ProxmoxConfig, api: Any | None = None):
        self.config = config
        self.api = api or ProxmoxAPI(
            config.api_host,
            port=config.api_port,
            user=config.api_user,
            token_name=config.api_token_id,
            token_value=config.api_token_secret,
            verify_ssl=config.verify_ssl,
            timeout=30,
        )

    def resolve_guest(self, vmid: int, kind: GuestKind | None = None) -> ResolvedGuest:
        for resource in self.api.cluster.resources.get(type="vm"):
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
        return int(self.api.cluster.get("nextid"))

    def wait_for_task(self, node: str, upid: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.task_timeout_seconds
        while time.monotonic() < deadline:
            status = self.api.nodes(node).tasks(upid).status.get()
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
        upid = self._endpoint(guest).status.start.post()
        self.wait_for_task(guest.node, upid)

    def stop(self, guest: ResolvedGuest) -> None:
        if guest.status == "stopped":
            return
        upid = self._endpoint(guest).status.stop.post()
        self.wait_for_task(guest.node, upid)

    def delete(self, guest: ResolvedGuest) -> None:
        if guest.status == "running":
            self.stop(guest)
        upid = self._endpoint(guest).delete()
        self.wait_for_task(guest.node, upid)

    def update_resources(self, guest: ResolvedGuest, vcpus: float, memory_mb: int) -> None:
        method = self._endpoint(guest).config.post if guest.kind is GuestKind.QEMU else self._endpoint(guest).config.put
        upid = method(cores=int(vcpus), memory=int(memory_mb))
        if upid:
            self.wait_for_task(guest.node, upid)

    def migrate(self, guest: ResolvedGuest, target_node: str, online: bool) -> None:
        if guest.node == target_node:
            return
        upid = self._endpoint(guest).migrate.post(target=target_node, online=int(online))
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
        upid = self.api.nodes(template.node).qemu(template.vmid).clone.post(
            newid=new_vmid,
            full=1,
            name=name,
            storage=storage,
            target=target_node,
        )
        self.wait_for_task(template.node, upid)
        return self.resolve_guest(new_vmid, GuestKind.QEMU)

    def create_lxc(self, node: str, data: dict[str, Any]) -> ResolvedGuest:
        upid = self.api.nodes(node).lxc.create(**data)
        self.wait_for_task(node, upid)
        return self.resolve_guest(int(data["vmid"]), GuestKind.LXC)

    def get_config(self, guest: ResolvedGuest) -> dict[str, Any]:
        return self._endpoint(guest).config.get()

    def set_config(self, guest: ResolvedGuest, **data: Any) -> None:
        method = self._endpoint(guest).config.post if guest.kind is GuestKind.QEMU else self._endpoint(guest).config.put
        upid = method(**data)
        if upid:
            self.wait_for_task(guest.node, upid)

    def resize_disk(self, guest: ResolvedGuest, disk: str, size_gb: float) -> None:
        upid = self._endpoint(guest).resize.put(disk=disk, size=f"{size_gb}G")
        if upid:
            self.wait_for_task(guest.node, upid)

    def add_qemu_disk(self, guest: ResolvedGuest, disk: str, storage: str, size_gb: float) -> None:
        self.set_config(guest, **{disk: f"{storage}:{size_gb},backup=0,ssd=0"})

    def delete_qemu_disk(self, guest: ResolvedGuest, disk: str) -> None:
        self.api.nodes(guest.node).qemu(guest.vmid).unlink.put(idlist=disk, force=1)
