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

## Ontra Manhattan TLC public instances

- New York City Taxi and Limousine Commission,
  [*TLC Trip Record Data: January 2025*](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
- Mobility Solutions Inc,
  [Ontra Manhattan TLC generator](https://github.com/mobility-solutions-inc/ontra/tree/6d4f168a0724a0f0bc7795b57f75fac8cf3010dd/dispatching/scripts).
- Geofabrik and OpenStreetMap contributors,
  [US Northeast snapshot](https://download.geofabrik.de/north-america/us-northeast.html)
  with replication timestamp 2026-08-05T20:21:23Z.
- Mobility Solutions Inc,
  [GraphHopper fork](https://github.com/mobility-solutions-inc/graphhopper/tree/80ed17c5fa3f71175949ee0ad44732391172e03a).

This new collection preserves the 24,325-request Manhattan hour originally used
to test Ontra's Rust dispatcher. TLC supplies zones and times, not door-to-door
coordinates; the generator sampled synthetic points inside those zones and
remapped them to a frozen routable point pool. The benchmark adds three official,
zone-balanced fleets with 1,000, 2,000, and 4,000 vehicles. The surviving
historical 2,000-vehicle fleet is supplemental because a later pilot generation
overwrote the full-hour fleet artifact. The complete directed road matrix uses
GraphHopper's `car` profile and a 1.4 time multiplier; no Haversine fallback is
present.

## Current import status

| Source | Suite role | Redistribution status |
|---|---|---|
| Eccel v1.2 | Small | Confirmed; DDARP release pinned and normalized |
| NYC-DARP v1.0 | Large | Confirmed CC BY 4.0; archive and warm-start commit pinned |
| Ontra Manhattan TLC v1.0.0 | Large | Confirmed CC BY 4.0 and ODbL 1.0 notices; source and normalized archives pinned |

Complete Parquet packages are published outside Git under the project's
[data-storage policy](data.html). The Eccel collection contains all 68 paired
DDARP instances. The NYC collection contains all 96 demand windows, all 62
compatible fleet deployments, and explicit onboard state for warm-start fleets.
The Ontra collection contains one complete 24,325-request hour, three official
fleet deployments, and one supplemental regression deployment.

The [complete notice and import gate](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/THIRD_PARTY_NOTICES.md)
is authoritative.
