from dataclasses import dataclass


@dataclass(frozen=True)
class ProxmoxStorage:
    name: str
    content: frozenset[str]


@dataclass(frozen=True)
class StorageSyncResult:
    vm_choice_set_name: str
    lxc_choice_set_name: str
    vm_storage_count: int
    lxc_storage_count: int
    vm_created: bool | None
    lxc_created: bool | None
