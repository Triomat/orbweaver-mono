<!--
SYNC IMPACT REPORT
==================
Version change: 1.1.0 → 1.2.0
Bump rationale: New principle added (VII. Feature Branch Workflow) — MINOR bump per versioning policy.

Modified principles: None

Added principles:
  VII. Feature Branch Workflow

Added sections: None
Removed sections: None

Templates reviewed:
  ✅ .specify/templates/plan-template.md — Constitution Check gate is generic; no update required.
  ✅ .specify/templates/spec-template.md — No direct constitution references; no update required.
  ✅ .specify/templates/tasks-template.md — No updates required; task execution will follow branch discipline per Principle VII.

Deferred TODOs: None — all placeholders resolved.
-->

# orbweaver Constitution

## Core Principles

### I. Upstream Immutability (NON-NEGOTIABLE)

`backend/` contains the upstream `netboxlabs/orb-discovery` device-discovery codebase verbatim.
No file under `backend/` MUST ever be edited by hand. Upstream changes MUST be applied via
`git show upstream/<ref>:<path> > backend/<path>` (patch-based workflow, never `git merge`).
This rule has zero exceptions — all orbweaver behavior MUST be implemented elsewhere.

**Rationale**: Preserving upstream verbatim makes future upstream merges deterministic and
auditable. Hand-edits would create hidden divergence that accumulates silently.

### II. Extension Over Modification

All orbweaver logic MUST live under `orbweaver/`. The upstream FastAPI app, Pydantic models,
and policy runner MUST be extended via runtime monkey-patching at process startup
(`orbweaver/patches.py`), CORS middleware injection, and route replacement — never by touching
upstream source files. The extension layer MUST remain as thin as possible.

**Rationale**: This pattern allows orbweaver to track upstream releases with minimal friction,
since there are no merge conflicts to resolve in modified upstream files.

### III. Common Object Model (COM) as the Canonical Data Layer

All vendor collectors MUST normalize device data into COM types defined in
`orbweaver/models/common.py` (`NormalizedDevice`, `NormalizedInterface`, `NormalizedIPAddress`,
`NormalizedVLAN`, `NormalizedPrefix`). No collector MAY emit raw NAPALM or vendor-specific
structures directly to the Diode translation layer. The COM is the only stable contract between
collectors and `orbweaver/diode_translate.py`.

**Rationale**: Decoupling vendor quirks from the Diode bridge means adding a new vendor only
requires implementing `BaseCollector` + COM normalization, with no changes to the translate layer.

### IV. Pluggable Collector Registry

New vendor collectors MUST subclass `BaseCollector` from `orbweaver/collectors/base.py` and
register in `orbweaver/collectors/registry.py`. Collector selection is driven by the `collector`
field on a policy scope entry. Absence of this field MUST fall through to the original NAPALM-only
upstream path, unchanged. No collector SHOULD be hardcoded outside the registry.

**Rationale**: The registry keeps the collector surface area explicit and auditable, and ensures
the legacy path remains available for devices without a dedicated collector.

### V. Simplicity & YAGNI

Features MUST NOT be added speculatively. Every new module, endpoint, or abstraction requires a
concrete current use-case. Over-engineering, premature abstraction, and gold-plating are prohibited.
Complexity MUST be justified in the feature spec before implementation begins.

**Rationale**: The extension layer exists to augment upstream, not replace it. Keeping orbweaver
lean reduces maintenance burden and lowers the risk of diverging from upstream in ways that are
hard to untangle.

### VI. Test-Driven Development (TDD)

All new orbweaver functionality MUST be covered by automated tests written before or alongside
the implementation (test-first or test-parallel). Every new module under `orbweaver/` MUST have
a corresponding test file in `orbweaver/tests/`. A feature implementation MUST NOT be considered
complete until `just test` passes with no failures. The upstream test suite (`just test-legacy`)
MUST continue to pass at all times — orbweaver changes MUST NOT regress upstream behavior.
Tests MUST cover the public contract of each unit (inputs, outputs, raised exceptions).
Integration tests requiring live devices MAY be skipped in CI but MUST be documented.

**Rationale**: TDD drives better-designed interfaces, surfaces regressions early, and provides
a living specification of expected behavior. Given that orbweaver monkey-patches upstream code,
a strong test suite is essential to detect subtle breakage introduced by upstream version bumps.

### VII. Feature Branch Workflow

All feature development MUST occur on dedicated feature branches created from `develop`. No commits
MUST ever be made directly to `develop`, `qas`, or `main` — these branches exist for merging only.
Feature branches follow the naming convention `feature/*` or `bugfix/*` per speckit conventions
(e.g., `feature/001-vendor-collector` or `bugfix/002-interface-speed`). Once a feature is complete,
tested, and reviewed, it MUST be merged back to `develop` via a pull request. Promotion from `develop`
to `qas` and `qas` to `main` is controlled and occurs only via human decision — no automation MAY
trigger these promotions without explicit approval.

**Rationale**: Feature branches enforce code review discipline, preserve `main` as a deployable
artifact, and ensure `develop` serves as a stable integration point. This workflow makes it easy to
work in parallel, revert mistakes, and trace the history of decisions through merge commits.

## Technology Constraints

- **Backend runtime**: Python 3.11+, FastAPI (via upstream uvicorn entrypoint), NAPALM, pynetbox,
  Diode SDK. Entry point: `orbweaver` CLI → `orbweaver.main`.
- **Frontend**: Nuxt 4, shadcn-nuxt, Tailwind CSS, VueUse. API base configured via
  `NUXT_PUBLIC_API_BASE` (default: `http://localhost:8073`).
- **Dependency management**: Backend uses `pyproject.toml` + `.venv`; UI uses `pnpm`.
- **Runtime artifacts**: `/tmp/orbweaver-{backend,ui}.{pid,log}`, `/tmp/orbweaver-reviews/`.
- **Privacy**: This repository MUST remain private. It MUST NOT be pushed to any public remote
  under any circumstance.
- **Security**: All code MUST be free of OWASP Top 10 vulnerabilities. Credentials and secrets
  MUST NOT appear in source files, committed config, or application logs.

## Development Workflow

- **Branch discipline**: All work MUST happen on feature branches per Principle VII. `develop`, `qas`,
  and `main` are merge-only. Feature branches are created from `develop` via `speckit.git.feature`.
- All dev commands MUST be invoked via `justfile` from the monorepo root. Shell scripts in
  `scripts/` are service wrappers only — they MUST NOT contain business logic.
- Feature work follows the speckit workflow: branch → specify → clarify → plan → tasks → implement.
- Tests run via `just test` (orbweaver suite) and `just test-legacy` (upstream suite). Both MUST
  pass before any commit. New functionality MUST include tests per Principle VI (TDD).
- `just lint` and `just check-imports` MUST pass before any commit.
- The Docker Compose stack (`just docker-up`) is the canonical integration reference environment.

## Governance

This constitution supersedes all other coding conventions for orbweaver. All feature implementation
plans MUST include a Constitution Check gate (verifying compliance with Principles I–VI) before
any Phase 1 design work begins and again before implementation.

Amendments MUST:
1. Update the Sync Impact Report HTML comment at the top of this file.
2. Bump `CONSTITUTION_VERSION` per semantic rules:
   - MAJOR: Backward-incompatible principle removal or redefinition.
   - MINOR: New principle or section added / materially expanded.
   - PATCH: Clarification, wording fix, or non-semantic refinement.
3. Set `LAST_AMENDED_DATE` to the amendment date (ISO 8601).
4. Preserve the original `RATIFICATION_DATE`.

**Version**: 1.2.0 | **Ratified**: 2026-05-07 | **Last Amended**: 2026-05-11
