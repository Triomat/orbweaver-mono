#!/usr/bin/env python3
"""
Removes all objects ingested by orbweaver from NetBox.

Targets objects carrying the tag defined by CLEANUP_TAG (default: "discovered").

Deletion order:
  1. IP addresses assigned to interfaces on tagged devices  (they'd go
     unassigned — not deleted — if the device is removed first)
  2. Devices tagged CLEANUP_TAG  (cascades: interfaces, primary IPs)
  3. VLANs tagged CLEANUP_TAG

Prefixes are intentionally skipped — they are shared network inventory and
not safe to delete automatically.

Usage:
    python3 netbox-cleanup.py [--dry-run]

Required env vars (or set in docker/.env):
    NETBOX_HOST   e.g. 192.168.11.90
    NETBOX_PORT   e.g. 8000
    NETBOX_TOKEN  NetBox API token
    CLEANUP_TAG   tag to filter on (default: discovered)
"""

import argparse
import os
import sys

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HOST  = os.environ.get("NETBOX_HOST", "192.168.11.90")
PORT  = os.environ.get("NETBOX_PORT", "8000")
TOKEN = os.environ.get("NETBOX_TOKEN", "")
TAG   = os.environ.get("CLEANUP_TAG", "discovered")

BASE  = f"http://{HOST}:{PORT}/api"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"})
    return s


def get_all(s: requests.Session, path: str, params: dict) -> list[dict]:
    """Paginate through all results and return them."""
    objects, url = [], f"{BASE}{path}"
    params = {**params, "limit": 200}
    while url:
        r = s.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        objects.extend(data["results"])
        url = data.get("next")
        params = {}          # next URL already contains query params
    return objects


def bulk_delete(s: requests.Session, path: str, ids: list[int], label: str, dry_run: bool) -> None:
    if not ids:
        print(f"  {label}: nothing to delete")
        return
    print(f"  {label}: deleting {len(ids)} object(s) — ids {ids[:5]}{'…' if len(ids) > 5 else ''}")
    if dry_run:
        return
    payload = [{"id": i} for i in ids]
    r = s.delete(f"{BASE}{path}", json=payload)
    if r.status_code == 204:
        print(f"  {label}: done")
    else:
        print(f"  {label}: ERROR {r.status_code} — {r.text}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: NETBOX_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    s = session()
    dry = args.dry_run

    if dry:
        print("=== DRY RUN — no changes will be made ===\n")

    print(f"NetBox: {BASE}")
    print(f"Tag:    {TAG}\n")

    # 1. Find devices with the tag
    print(f"[1/3] Fetching devices tagged '{TAG}'…")
    devices = get_all(s, "/dcim/devices/", {"tag": TAG})
    print(f"      found {len(devices)}: {[d['name'] for d in devices]}")

    # 2. Collect IP addresses assigned to those devices' interfaces
    print(f"\n[2/3] Fetching IP addresses on those devices…")
    ip_ids: list[int] = []
    for dev in devices:
        ips = get_all(s, "/ipam/ip-addresses/", {"device_id": dev["id"]})
        ip_ids.extend(ip["id"] for ip in ips)
    bulk_delete(s, "/ipam/ip-addresses/", ip_ids, "IP addresses", dry)

    # 3. Delete devices (cascades interfaces)
    device_ids = [d["id"] for d in devices]
    bulk_delete(s, "/dcim/devices/", device_ids, "Devices", dry)

    # 4. VLANs with the tag
    print(f"\n[3/3] Fetching VLANs tagged '{TAG}'…")
    vlans = get_all(s, "/ipam/vlans/", {"tag": TAG})
    print(f"      found {len(vlans)}")
    bulk_delete(s, "/ipam/vlans/", [v["id"] for v in vlans], "VLANs", dry)

    print("\nDone." if not dry else "\nDry run complete — nothing was deleted.")


if __name__ == "__main__":
    main()
