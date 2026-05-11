# Changelog

All notable changes to orbweaver will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2.dev0] - 2026-05-08

### Development Release

This is a development release. Unreleased changes are tracked here.

### Added
- Development release infrastructure
- CHANGELOG tracking
- End-to-end LLDP cable discovery workflow with confidence tiers (`confirmed`, `partial`, `unresolvable`)
- Cable COM data model (`CableCandidate`, `CableResolutionSummary`, `CableSkipEntry`) and review-session cable storage
- NetBox cable ingestion with create-or-skip idempotency and rollback on write failures
- Review API support for cable status updates and `ingest-cables` endpoint
- Cable summary and skip-reason API endpoints for UI and automation visibility
- Frontend review UI support for cable tab, filtering, accept/reject actions, and cable summary visualization
- Cable user documentation: [docs/cable-resolution.md](docs/cable-resolution.md) and [docs/cable-examples.md](docs/cable-examples.md)

### Changed
- Policy/status API compatibility behavior preserved for upstream legacy tests while keeping orbweaver cable features available
- Review workflow now stores and renders cable candidates alongside devices

### Fixed
- Interface normalization ordering for Cisco abbreviations to avoid incorrect prefix expansions
- Upstream backend compatibility regressions in server endpoint behavior

### Security

---

## [0.4.1] - Previous Release

Earlier release notes would be documented here upon stabilization.
