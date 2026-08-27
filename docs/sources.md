---
layout: default
title: Sources and attribution
---

# Sources and attribution

The benchmark builds scaffolding around existing public research; it does not
claim authorship of those datasets or methods.

## Small starting point

- Renan Artur Lopes Eccel, *instances-DDARP-DPDPTW*, v1.2.
  [Dataset DOI](https://doi.org/10.5281/zenodo.4107192)
- Renan Artur Lopes Eccel and Rodrigo Castelan Carlson, “Análise de problemas
  dinâmicos de coleta e entrega e dial-a-ride: métodos de dinamização e
  instâncias de benchmark.”
  [Article DOI](https://doi.org/10.14295/transportes.v28i4.2412)
- Gerardo Berbeglia, Jean-François Cordeau, and Gilbert Laporte, “A Hybrid Tabu
  Search and Constraint Programming Algorithm for the Dynamic Dial-a-Ride
  Problem.” [Article DOI](https://doi.org/10.1287/ijoc.1110.0454)

The source already includes dynamic reveal times. The benchmark's work is to pin
lineage, add standardized lookahead variants where useful, integrate exact
references, and validate cross-source semantics.

## Large starting point

- Elahe Amiri, Antoine Legrain, and Issmail El Hallaoui, *Manhattan Dial-a-Ride
  Benchmark Dataset with NYC TLC Taxi Trips, 2015–2016*, v1.0.
  [Dataset DOI](https://doi.org/10.5281/zenodo.20452171)
- Laboratory for Combinatorial Optimization in Real-time Environment,
  [dynamic-ips](https://github.com/lab-core/dynamic-ips).

NYC-DARP incorporates NYC TLC trip records and travel information derived from
OpenStreetMap and OSRM. Every upstream notice must survive normalization.

## Current import status

| Source | Suite role | Redistribution status |
|---|---|---|
| Eccel v1.2 | Small | Confirmed; DDARP release pinned and normalized |
| NYC-DARP v1.0 | Large | Confirmed CC BY 4.0; archive and warm-start commit pinned |

Complete Parquet packages are published outside Git under the project's
[data-storage policy](data.html). The Eccel collection contains all 68 paired
DDARP instances. The NYC collection contains all 96 demand windows, all 62
compatible fleet deployments, and explicit onboard state for warm-start fleets.

The [complete notice and import gate](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/THIRD_PARTY_NOTICES.md)
is authoritative.
