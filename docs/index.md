---
layout: default
title: Online DARP Benchmark
---

# Online DARP Benchmark

Measure the value of future information—not just who wins one online run.

The Online DARP Benchmark combines small instances with certified,
objective-specific offline references and large instances that test real-world
scale. Each algorithm is evaluated across a curve of advance notice while its
service, passenger, vehicle, stability, feasibility, and compute outcomes stay
visible as separate values.

> **Status: v0.1 incubation.** The public contract and contribution
> infrastructure are live. Draft normalized public collections now pass the
> reference validator; exact small-instance reference production is the next
> scientific milestone.

## Evaluation shape

| Dimension | Public protocol |
|---|---|
| Scale | Exact small, bounded medium, and large online tiers |
| Advance notice | 0, 15, 30, 60, 240 minutes, and full where meaningful |
| Offline comparison | Objective-specific certified references on small instances |
| Reporting | Multidimensional scorecard; no official aggregate score |
| Algorithm objective | Unrestricted and disclosed |
| Prediction | Allowed and labeled by training-data track |
| Relocation | Allowed and separately measured as empty movement |

An algorithm may report full-information execution as unsupported when loading an
entire large day would test formulation size rather than useful online behavior.
Unsupported is distinct from infeasible.

## Public sources

The intended v1 suite is exhaustive over the applicable passenger DARP instances
in [Eccel DDARP v1.2](https://doi.org/10.5281/zenodo.4107192),
[NYC-DARP v1.0](https://doi.org/10.5281/zenodo.20452171), and the new
[Ontra Manhattan TLC 2025-01-22 collection](https://github.com/mobility-solutions-inc/online-darp-benchmark/releases/tag/ontra-manhattan-tlc-2025-01-22-v1.0.0-draft.1).
Redistribution is confirmed and draft Parquet collections are distributed as
immutable archives, not committed to Git or Git LFS.
[Read the source and attribution status](sources.html).

## Participate

- [Read the full benchmark contract on GitHub](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/BENCHMARK_CARD.md)
- [Read the data storage and download policy](data.html)
- [Submit a public instance or benchmark result](submit.html)
- [Browse the schemas](https://github.com/mobility-solutions-inc/online-darp-benchmark/tree/main/schemas)
- [Review RFC-0001: Parquet instance packages](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/proposal/parquet-instance-format/proposals/0001-parquet-instance-format.md)
- [Follow the roadmap](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/ROADMAP.md)
