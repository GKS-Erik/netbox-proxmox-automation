# Flask automation application architecture

The application treats NetBox as the desired-state source and Proxmox as the
authoritative source for the current location of an existing guest.

## Request flow

1. `app.py` receives JSON and converts validation failures to HTTP responses.
2. `models/webhook.py` normalizes old (`model`) and new (`object_type`) NetBox
   webhook envelopes into typed VM or disk events.
3. `services/dispatcher.py` maps an event and state transition to generic
   operations such as `start`, `stop`, `migrate`, or `resize_disk`.
4. `services/vm_service.py` selects one backend based on `GuestKind` and
   executes the generic operations.
5. `backends/qemu.py` and `backends/lxc.py` translate the common contract to
   guest-specific operations.
6. `clients/` contains the only direct use of `proxmoxer` and `pynetbox`.

## Node semantics

- `api_host` is the Proxmox API endpoint and is always required.
- The VM's assigned NetBox device is the desired target node.
- `default_node` is used only for provisioning when no NetBox device is
  assigned. The legacy configuration key `node` is accepted as an alias.
- For an existing guest, `ProxmoxClient.resolve_guest()` obtains its current
  node from `cluster/resources`; callers do not assume that NetBox is current.

## Extension rule

QEMU and LXC backends expose the same orchestration methods. Differences that
are real Proxmox capabilities remain inside the backend and raise
`UnsupportedOperationError` when the common operation is not available.
Raw webhook dictionaries must not be passed beyond `models/webhook.py`.
