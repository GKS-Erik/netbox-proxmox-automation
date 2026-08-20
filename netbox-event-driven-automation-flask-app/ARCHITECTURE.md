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

## Logging

`log_level` controls application logging outside Flask debug mode. Flask debug
mode always overrides this to `DEBUG`. Each API config has a separate
`debug_payloads` switch; request and response payloads are logged only when
that switch and Flask debug mode are both enabled. Sensitive values are
redacted before logging.

## Template synchronization

`POST /<netbox_webhook_name>/templates/sync/` retrieves all QEMU templates
from the Proxmox cluster inventory and fully synchronizes the configured
NetBox Custom Field Choice Set. The choice value is the VMID and its label is
the Proxmox template name. The Choice Set is created when it does not exist.
The same synchronization is attempted once during application startup. A
startup synchronization failure is logged but does not prevent the webhook
service from starting, so a later endpoint call can recover it.

## Storage synchronization

During application startup, the service also reads the Proxmox storage
inventory and synchronizes two configured NetBox Custom Field Choice Sets.
Storage supporting `images` is added to the VM Storage set, while storage
supporting `rootdir` is added to the LXC Storage set. The Proxmox storage name
is used as both the choice value and label. If one category is empty, its
existing Choice Set is left unchanged and a warning is logged.
