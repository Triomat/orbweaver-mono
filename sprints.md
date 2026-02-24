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

### E. Comparison summary after ingest (est. 2 days)
After ingesting, show a summary card:
> "Orbweaver found X devices, Y interfaces, Z VLANs — vs orb's basic device+interface record."

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
