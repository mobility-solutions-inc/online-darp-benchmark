# Changelog

All notable benchmark and tooling changes are recorded here.

## [Unreleased]

### Added

- Ontra Manhattan TLC 2025-01-22 public passenger-DARP source and normalized
  Parquet releases, with three official balanced fleet deployments and one
  supplemental historical Rust-regression deployment.
- Deterministic GraphHopper matrix conversion with a documented 1.4 time
  multiplier and validation tests.
- Required result fields for public-code availability and a validated direct
  source link when code is available.
- Proposed confidential hidden-instance intake, isolated staging, access-ledger,
  and public opaque-registry contracts.
- Result standing classifications for official, contributor-reference, and
  unofficial submissions, including disclosed algorithm teams and standing
  hidden-access conflict checks.
- A permanent machine-readable restriction making code authored or controlled
  by Connor Riley ineligible for official hidden-instance results.

### Fixed

- Geographic node files now store the GeoParquet 1.1 CRS as an OGC:CRS84
  PROJJSON object. NYC-DARP and Ontra Manhattan collections are republished as
  1.0.0-draft.2; their other tables are unchanged.

## [0.1.0] - 2026-08-27

### Added

- Incubation benchmark card and public source registry.
- Instance, result, and event-log schemas with valid examples.
- Local validator and continuous-integration checks.
- Contribution, governance, conduct, security, and maintainer policies.
- Initial GitHub Pages documentation.

[0.1.0]: https://github.com/mobility-solutions-inc/online-darp-benchmark/releases/tag/v0.1.0
