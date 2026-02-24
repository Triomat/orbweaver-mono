# orbweaver Showcase Roadmap

Ordered by impact for a live demo. Tier 1 items are quick wins; Tier 3 is longer-term.

---

## Completed

- [x] **Trigger orb-agent from UI** — `/orb-agent` page: edit agent.yml, Apply & Restart, Trigger now
- [x] **Trigger standard orb from UI** — was on `/config`, now consolidated into `/orb-agent`
- [x] **Cron disabled** — `orb-agent` schedule set to `0 0 1 1 *`; manual-only for showcase
- [x] **CORS proxy** — Nuxt server route `/api/orb/*` → orb-agent status check without CORS
- [x] **docker exec trigger** — orbweaver backend POSTs to orb-agent internal API via `docker exec python3`

---

## Tier 1 — High impact, quick wins

### A. Orb vs Orbweaver status panel (est. 1 day)
Side-by-side card on the home page (`/`) showing both services:
- Last run time, device count ingested, status (running/idle)
- Makes the parallel execution visible at a glance without navigating away
- Data sources: orbweaver `/api/v1/status`, orb-agent `/api/orb/status`

### B. Data richness comparison on review page (est. 1–2 days)
For each discovered device on the review page, show a "richer than orb" badge listing extra
fields orbweaver found that standard NAPALM alone wouldn't:
- LLDP neighbors, OS version parsed, exact interface type, VLAN assignments
- Visual proof of orbweaver's value at the review step

### C. NetBox tag differentiation (est. 30 min — config only, no code)
Tag orb-ingested objects `orb-discovery` and orbweaver-ingested objects `orbweaver` in the
policy defaults. Filter in NetBox UI to show what each system found separately.

---

## Tier 2 — Medium effort, strong demo value

### D. Review workflow walkthrough overlay (est. 1 day)
Guided tour overlay on the review page explaining each step:
discover → review → accept/reject → ingest.
Useful for walking stakeholders through the orbweaver differentiator live.

### E. Comparison summary after ingest (est. 0.5 day)
After ingesting, extend the response with summary stats:
> "Orbweaver found X devices, Y interfaces, Z VLANs, W LLDP neighbors"

Pull counts from the review session data already stored on disk.

### F. LLDP topology preview (est. 2–3 days)
On the review page, render a simple ASCII or SVG graph of LLDP neighbor relationships
from the discovered data. Visceral visual differentiator — standard orb has no equivalent.

---

## Tier 3 — Longer term

### G. Scheduled orbweaver runs (est. 3 days)
Add a cron/interval option to the orbweaver UI so it can match the standard orb's automated
behaviour while still routing through the review step.

### H. Side-by-side NetBox diff (est. 1 week)
After both systems have run, call the NetBox API and diff what each tagged set of objects
contains — show the delta in device fields, IP addresses, VLANs.
Requires NetBox API token in UI config.

### I. Juniper JunOS collector (est. 2 days)
Write in netbox-discovery first using `_template.py`, then port to orbweaver.
- NAPALM `junos` driver (NETCONF-based)
- Version parsing already exists (`parse_juniper_junos_version`)
- Role heuristics: EX=switch, MX=router, SRX=firewall, QFX=dc-switch
- Interface type mapping: ge-/xe-/et-/ae/irb./vlan.
- Register in both repos' `registry.py`

---

## Ports from netbox-discovery

Reusable modules from `/home/cheddar/projects/netbox-discovery/` to adapt and port.

### P1. compare.py (est. 0.5 day)
Port `netbox_discovery/ui/compare.py` → `device_discovery/review/compare.py`.
Per-field diff of discovered data vs live NetBox state (devices, VLANs, prefixes).
Uses pynetbox (read-only). Wire up as `POST /api/v1/reviews/{id}/compare`.
Accelerates Roadmap Item H backend.

### P2. cleanup/orchestrator.py (est. 0.5 day)
Port `netbox_discovery/cleanup/orchestrator.py` → `device_discovery/cleanup.py`.
Tag-based removal of discovered objects from NetBox in reverse dependency order.
Gives "undo ingest" capability. Add `POST /api/v1/cleanup` endpoint (dry-run + confirm).

---

## Sprint: Feb 24 – Mar 7 (2 weeks)

### Week 1: Housekeeping + Showcase Polish

| Day | Items | Effort |
|-----|-------|--------|
| 1 | Commit 4 pending bug fixes (LLDP field, datetime parsing, Diode auth, Justfile). Merge upstream into develop. `pytest tests/` | 0.5 day |
| 2 | **C**: Tag differentiation (config only). **A** backend: `GET /api/v1/orb-agent/status`, expose review count | 1 day |
| 3 | **A** frontend: side-by-side status cards on home page (auto-poll). **B** planning: inventory richness fields | 1 day |
| 4 | **B**: Data richness badges on review page (client-side, pill badges) | 1 day |
| 5 | **P1**: Port compare.py, add compare endpoint. **E**: Extend ingest response with summary stats | 1 day |

### Week 2: More Polish + New Capabilities

| Day | Items | Effort |
|-----|-------|--------|
| 6 | **D**: Walkthrough overlay (Vue composable + Tailwind guided tour) | 1 day |
| 7 | **P2**: Port cleanup module, add cleanup endpoint | 0.5 day |
| 8–9 | **I**: Juniper JunOS collector — write in netbox-discovery, test, port to orbweaver | 2 days |
| 10 | Integration testing (both repos). Manual E2E. Update sprints.md + CLAUDE.md. Push | 1 day |

### Deferred

- **F**: LLDP topology preview — needs graph rendering library
- **G**: Scheduled orbweaver runs — needs review-gate design
- **H** frontend: side-by-side diff UI — backend ready via P1, frontend later
