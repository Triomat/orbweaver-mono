# Rack Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow policy YAML (and the UI config form) to assign a NetBox rack to imported devices, at both the defaults level and per-device override level.

**Architecture:** `rack` is added to `NormalizedDevice` (COM), injected from `scope.rack` or `defaults.rack` in the patched policy runner, then translated to a Diode `Rack(name, site)` object embedded in the `Device` entity. Three `Device(...)` constructions in `diode_translate.py` all receive rack to prevent reconciler clobbering. The frontend adds a Rack field to the Defaults section and to each device card.

**Tech Stack:** Python 3.12, Pydantic v2, Diode SDK (`netboxlabs.diode.sdk.ingester.Rack`), Nuxt 4, TypeScript

---

### Task 1: Add `rack` to the COM

**Files:**
- Modify: `orbweaver/models/common.py`

- [ ] **Step 1: Add the field to `NormalizedDevice`**

Open `orbweaver/models/common.py`. Find the `NormalizedDevice` dataclass (around line 304). Add `rack` after `primary_ip6`:

```python
primary_ip4: str = ""  # CIDR notation
primary_ip6: str = ""
rack: str = ""
```

- [ ] **Step 2: Verify the import still works**

```bash
cd /path/to/orbweaver-mono
.venv/bin/python -c "from orbweaver.models.common import NormalizedDevice; d = NormalizedDevice.__dataclass_fields__; print('rack' in d)"
```
Expected output: `True`

- [ ] **Step 3: Commit**

```bash
git add orbweaver/models/common.py
git commit -m "feat: add rack field to NormalizedDevice COM"
```

---

### Task 2: Monkey-patch `Defaults` and `Napalm` for rack; inject into COM

**Files:**
- Modify: `orbweaver/patches.py`

- [ ] **Step 1: Add `rack` to `Napalm` scope model**

In `orbweaver/patches.py`, in the section marked `── 1a. Add collector field to Napalm ──`, add these two lines directly after the existing `Napalm` field additions (before the `Config` block):

```python
# ── 1c. Add rack field to Napalm (per-device rack override) ─────────────────
Napalm.__annotations__["rack"] = str | None
Napalm.model_fields["rack"] = FieldInfo(
    default=None,
    annotation=str | None,
    description="Rack name to assign this device to in NetBox. Overrides defaults.rack.",
)
```

- [ ] **Step 2: Add `rack` to `Defaults` model**

In the same section, add after the `Napalm` rack block (and before the `Config` auto_ingest block):

```python
# ── 1d. Add rack field to Defaults (policy-level rack default) ──────────────
from device_discovery.policy.models import Defaults  # noqa: E402 (already imported below, hoist here)
Defaults.__annotations__["rack"] = str | None
Defaults.model_fields["rack"] = FieldInfo(
    default=None,
    annotation=str | None,
    description="Rack name to assign all devices in this policy to in NetBox.",
)
Defaults.model_rebuild(force=True)
```

> **Note:** `Defaults` is already imported further down in `patches.py` for the runner section. Move or duplicate the import to the top of section 1 so it's available here. The existing `from device_discovery.policy.models import Defaults` line at line ~66 can stay; just add another import line in section 1 (Python deduplicates it at runtime).

- [ ] **Step 3: Inject rack into `NormalizedDevice` after collector runs**

In `_collect_device_data_via_collector`, find line 133:
```python
normalized_device = collector.discover_single(sanitized_hostname)
```
Add immediately after it:
```python
normalized_device.rack = getattr(scope, "rack", None) or getattr(_defaults, "rack", None) or ""
```

> `_defaults` is assigned two lines later (`_defaults = config.defaults or Defaults()`). Move the `_defaults` assignment to just before this injection so it's available:

The block should read:
```python
normalized_device = collector.discover_single(sanitized_hostname)
_defaults = config.defaults or Defaults()
normalized_device.rack = getattr(scope, "rack", None) or getattr(_defaults, "rack", None) or ""
entities = translate_single_device(normalized_device, _defaults)
primary_ip_ents = translate_primary_ip_entities(normalized_device, _defaults)
```

(Remove the old `_defaults = config.defaults or Defaults()` line that comes after, since it's now above.)

- [ ] **Step 4: Verify patches apply cleanly**

```bash
.venv/bin/python -c "
import orbweaver.patches
from device_discovery.policy.models import Napalm, Defaults
print('Napalm.rack:', Napalm.model_fields.get('rack'))
print('Defaults.rack:', Defaults.model_fields.get('rack'))
"
```
Expected: both print a `FieldInfo` with `default=None`, not `None`.

- [ ] **Step 5: Commit**

```bash
git add orbweaver/patches.py
git commit -m "feat: patch Defaults and Napalm with rack field; inject into COM"
```

---

### Task 3: Translate rack through all three `Device(...)` constructions

**Files:**
- Modify: `orbweaver/diode_translate.py`

- [ ] **Step 1: Import `Rack` from the Diode SDK**

In `orbweaver/diode_translate.py`, find the existing import block:
```python
from netboxlabs.diode.sdk.ingester import (
    VLAN,
    Device,
    DeviceType,
    Entity,
    Interface,
    IPAddress,
    Platform,
    Prefix,
)
```
Add `Rack` to it:
```python
from netboxlabs.diode.sdk.ingester import (
    VLAN,
    Device,
    DeviceType,
    Entity,
    Interface,
    IPAddress,
    Platform,
    Prefix,
    Rack,
)
```

- [ ] **Step 2: Build rack object in `_translate_device()`**

In `_translate_device()`, after the tenant block and before the `return Device(...)`:
```python
# Rack: name-only reference; device appears as non-racked in NetBox
rack_obj = Rack(name=device.rack, site=site_name) if device.rack else None
```

Add `rack=rack_obj` to the `Device(...)` call:
```python
return Device(
    name=device.name,
    device_type=DeviceType(
        model=model,
        manufacturer=manufacturer_name,
    ),
    platform=platform,
    role=role_name,
    serial=device.serial or None,
    status=device.status.value if device.status else "active",
    site=site_name,
    tags=tags,
    comments=device.comments or None,
    tenant=tenant,
    rack=rack_obj,
)
```

- [ ] **Step 3: Add rack to `device_ref` in `_translate_interface()`**

Find the `device_ref = Device(...)` block (around line 226). Add `rack=diode_device.rack` after `tenant=diode_device.tenant`:
```python
device_ref = Device(
    name=diode_device.name,
    site=diode_device.site,
    device_type=diode_device.device_type,
    role=diode_device.role,
    platform=diode_device.platform,
    serial=diode_device.serial,
    status=diode_device.status,
    tags=diode_device.tags,
    comments=diode_device.comments,
    tenant=diode_device.tenant,
    rack=diode_device.rack,
)
```

- [ ] **Step 4: Add rack to `translate_primary_ip_entities()`**

Find the `Entity(device=Device(...))` in `translate_primary_ip_entities()`. Add `rack=diode_device.rack`:
```python
return [Entity(device=Device(
    name=diode_device.name,
    site=diode_device.site,
    device_type=diode_device.device_type,
    role=diode_device.role,
    tenant=diode_device.tenant,
    rack=diode_device.rack,
    primary_ip4=device.primary_ip4 or None,
    primary_ip6=device.primary_ip6 or None,
))]
```

- [ ] **Step 5: Verify import and translation work**

```bash
.venv/bin/python -c "
from orbweaver.diode_translate import translate_single_device
from orbweaver.models.common import NormalizedDevice, NormalizedDeviceType, NormalizedDeviceRole, NormalizedSite
from device_discovery.policy.models import Defaults

device = NormalizedDevice(
    name='test-sw',
    device_type=NormalizedDeviceType(model='C9300', manufacturer=None),
    role=NormalizedDeviceRole(name='switch'),
    site=NormalizedSite(name='DC1'),
    rack='Rack-A1',
)
defaults = Defaults(site='DC1', role='switch')
entities = translate_single_device(device, defaults)
device_entity = next(e for e in entities if e.HasField('device'))
print('rack name:', device_entity.device.rack.name)
"
```
Expected: `rack name: Rack-A1`

- [ ] **Step 6: Commit**

```bash
git add orbweaver/diode_translate.py
git commit -m "feat: translate rack field from COM to Diode Device entity"
```

---

### Task 4: Frontend composable — add rack to types and serialization

**Files:**
- Modify: `frontend/app/composables/useConfig.ts`

- [ ] **Step 1: Add `rack` to `DeviceEntry` interface**

Find:
```typescript
export interface DeviceEntry {
  hostname: string
  username: string
  password: string
  collector: string
  driver: string
  timeout: number
}
```
Replace with:
```typescript
export interface DeviceEntry {
  hostname: string
  username: string
  password: string
  collector: string
  driver: string
  timeout: number
  rack: string
}
```

- [ ] **Step 2: Add `rack` to `PolicyForm.defaults`**

Find:
```typescript
export interface PolicyForm {
  name: string
  defaults: { site: string; role: string; tags: string; tenant: string }
  autoIngest: boolean
  devices: DeviceEntry[]
}
```
Replace with:
```typescript
export interface PolicyForm {
  name: string
  defaults: { site: string; role: string; tags: string; tenant: string; rack: string }
  autoIngest: boolean
  devices: DeviceEntry[]
}
```

- [ ] **Step 3: Update `defaultDevice()` and `defaultPolicy()`**

Find:
```typescript
function defaultDevice(): DeviceEntry {
  return { hostname: '', username: '', password: '', collector: 'cisco_ios', driver: '', timeout: 60 }
}

function defaultPolicy(): PolicyForm {
  return {
    name: 'my-discovery',
    defaults: { site: '', role: '', tags: '', tenant: '' },
    autoIngest: false,
    devices: [defaultDevice()],
  }
}
```
Replace with:
```typescript
function defaultDevice(): DeviceEntry {
  return { hostname: '', username: '', password: '', collector: 'cisco_ios', driver: '', timeout: 60, rack: '' }
}

function defaultPolicy(): PolicyForm {
  return {
    name: 'my-discovery',
    defaults: { site: '', role: '', tags: '', tenant: '', rack: '' },
    autoIngest: false,
    devices: [defaultDevice()],
  }
}
```

- [ ] **Step 4: Emit rack in `_buildPolicyObject()`**

In `_buildPolicyObject`, find the scope map:
```typescript
const scope = policy.devices.map((d) => {
  const entry: Record<string, unknown> = {
    hostname: d.hostname,
    username: d.username,
    password: d.password,
    timeout: d.timeout,
  }
  if (d.collector) {
    entry.collector = d.collector
  } else if (d.driver) {
    entry.driver = d.driver
  }
  return entry
})
```
Replace with:
```typescript
const scope = policy.devices.map((d) => {
  const entry: Record<string, unknown> = {
    hostname: d.hostname,
    username: d.username,
    password: d.password,
    timeout: d.timeout,
  }
  if (d.collector) {
    entry.collector = d.collector
  } else if (d.driver) {
    entry.driver = d.driver
  }
  if (d.rack) entry.rack = d.rack
  return entry
})
```

And in the defaults block:
```typescript
const defaults: Record<string, unknown> = {}
if (policy.defaults.site)   defaults.site   = policy.defaults.site
if (policy.defaults.role)   defaults.role   = policy.defaults.role
if (policy.defaults.tenant) defaults.tenant = policy.defaults.tenant
if (policy.defaults.rack)   defaults.rack   = policy.defaults.rack
if (policy.defaults.tags) {
  defaults.tags = policy.defaults.tags.split(',').map((t) => t.trim()).filter(Boolean)
}
```

- [ ] **Step 5: Parse rack in `yamlToForm()`**

Find the return block inside `yamlToForm`:
```typescript
return {
  name,
  defaults: {
    site: String(defaults.site ?? ''),
    role: String(defaults.role ?? ''),
    tags,
    tenant: String(defaults.tenant ?? ''),
  },
  autoIngest: config?.auto_ingest === true,
  devices: devices.length > 0 ? devices : [defaultDevice()],
}
```
Replace with:
```typescript
return {
  name,
  defaults: {
    site: String(defaults.site ?? ''),
    role: String(defaults.role ?? ''),
    tags,
    tenant: String(defaults.tenant ?? ''),
    rack: String(defaults.rack ?? ''),
  },
  autoIngest: config?.auto_ingest === true,
  devices: devices.length > 0 ? devices : [defaultDevice()],
}
```

Also update the device mapping in `yamlToForm` to include `rack`:
```typescript
const devices: DeviceEntry[] = (scope ?? []).map((d) => ({
  hostname: String(d.hostname ?? ''),
  username: String(d.username ?? ''),
  password: String(d.password ?? ''),
  collector: String(d.collector ?? ''),
  driver: String(d.driver ?? ''),
  timeout: typeof d.timeout === 'number' ? d.timeout : 60,
  rack: String(d.rack ?? ''),
}))
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/composables/useConfig.ts
git commit -m "feat: add rack to PolicyForm, DeviceEntry, and YAML serialization"
```

---

### Task 5: Frontend UI — add rack fields to config form

**Files:**
- Modify: `frontend/app/pages/config.vue`

- [ ] **Step 1: Add Rack to the Defaults section**

Find the Tenant/Role grid in the Defaults section:
```html
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Tenant</label>
              <input
                v-model="policy.defaults.tenant"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="acme-corp"
              />
            </div>
          </div>
```
Replace with:
```html
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Tenant</label>
              <input
                v-model="policy.defaults.tenant"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="acme-corp"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Rack</label>
              <input
                v-model="policy.defaults.rack"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="Rack-A1"
              />
            </div>
          </div>
```

- [ ] **Step 2: Add Rack override to each device card**

Find the end of the per-device collector/timeout grid (around line 227, just before the closing `</div>` of the device card's `space-y-3`):
```html
            <div class="grid grid-cols-2 gap-3">
              ...timeout field...
            </div>
          </div>   ← closing tag of the device card's space-y-3 div
```
Insert a Rack row between the collector/timeout grid and that closing div:
```html
            <div>
              <label class="mb-1 block text-xs text-muted-foreground">Rack (override)</label>
              <input
                v-model="device.rack"
                type="text"
                class="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="leave blank to use default"
              />
            </div>
```

- [ ] **Step 3: Start the dev server and verify visually**

```bash
just ui-restart
```
Open `http://localhost:3000/config` in a browser. Confirm:
- "Rack" input appears in the Defaults section next to Tenant
- "Rack (override)" input appears in each device card below Collector/Timeout
- Switching to YAML tab shows `rack:` under `defaults:` when Rack is filled in
- Typing a rack name in a device's override field emits `rack:` on that scope entry in YAML

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pages/config.vue
git commit -m "feat: add rack fields to config form (defaults and per-device override)"
```

---

### Task 6: End-to-end smoke test and release

**Files:** none new

- [ ] **Step 1: Run backend syntax and import checks**

```bash
just check-syntax
just check-imports
```
Expected: no errors.

- [ ] **Step 2: Run the full test suite**

```bash
just test
```
Expected: all tests pass.

- [ ] **Step 3: Smoke test with a policy YAML**

With the backend running (`just start`), POST a policy that includes a rack:
```bash
curl -s -X POST http://localhost:8073/api/v1/discover \
  -H "Content-Type: application/x-yaml" \
  --data-binary '
policies:
  rack-test:
    config:
      defaults:
        site: DC1
        rack: Rack-A1
    scope:
      - hostname: 192.0.2.1
        username: admin
        password: secret
        collector: cisco_ios
'
```
Check backend logs (`just backend-logs`) for a line like:
```
Policy rack-test, Hostname 192.0.2.1: Collecting via cisco_ios collector
```
After discovery completes, verify in NetBox that the device appears under Rack-A1 → Non-racked Devices.

- [ ] **Step 4: Bump version and tag**

In `orbweaver/pyproject.toml`, update:
```toml
version = "0.3.3"
```

Commit and tag:
```bash
git add orbweaver/pyproject.toml
git commit -m "chore: bump version to 0.3.3 for rack assignment feature"
git tag -a v0.3.3 -m "v0.3.3 — rack assignment for imported devices"
git push origin main v0.3.3
```
