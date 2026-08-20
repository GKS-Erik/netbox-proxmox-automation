from dataclasses import dataclass


@dataclass(frozen=True)
class ProxmoxTemplate:
    vmid: int
    name: str
    node: str


@dataclass(frozen=True)
class TemplateSyncResult:
    choice_set_name: str
    template_count: int
    created: bool
