# Upstream Issues / Workarounds

Issues that originate in upstream dependencies and are worked around inside orbweaver.
Each entry describes the root cause, the workaround, and where to file or track the upstream fix.

---

## [DIODE] Rack lookup fails without location — new rack created every run

**Status:** Worked around in orbweaver  
**Upstream:** `netboxlabs/diode-netbox-plugin`  
**File an issue at:** https://github.com/netboxlabs/diode-netbox-plugin/issues

### Root cause

The Diode reconciler's rack matchers (`matcher.py`) resolve existing racks using:

1. `asset_tag` (unique)
2. `location + name` (unique constraint)
3. `location + facility_id`

There is **no matcher for `site + name`**, even though NetBox permits racks to exist at the site level with no location (the most common deployment). When orbweaver passes `Rack(name="RACK-01", site="DC1")` to a Device entity, the reconciler finds no matching rack and creates a new one on every run.

### Workaround (orbweaver)

Rack is not passed to Diode at all. After the Diode ingest completes, orbweaver
uses pynetbox to assign the rack directly via the NetBox REST API, which supports
lookup by `name` + `site` without requiring `location`.

See: `orbweaver/netbox_ops.py` → `assign_device_rack()`

### What the upstream fix should be

Add a `dcim_rack_unique_site_name` matcher to `diode-netbox-plugin`:

```python
Matcher(
    name="dcim_rack_unique_site_name",
    fields=["site", "name"],
)
```

This would let Diode resolve site-level racks (no location) by name+site, consistent
with NetBox's own API behavior. Once merged upstream, the pynetbox workaround in
orbweaver can be removed and rack can be passed directly in the Device entity.
