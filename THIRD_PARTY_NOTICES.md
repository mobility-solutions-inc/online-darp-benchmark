# Third-Party Notices and Data Provenance

The Git repository contains benchmark-owned code, schemas, documentation,
registries, and synthetic examples. Bulk normalized data is distributed as
immutable external collection archives rather than through Git or Git LFS.
Source archives remain at their canonical records unless a collection notice
explicitly says otherwise.

The repository's MIT license applies only to benchmark-owned material. It does
not override a dataset, article, road network, or upstream software license.

## Eccel DDARP/DPDPTW

- Dataset: Renan Artur Lopes Eccel, *instances-DDARP-DPDPTW*, version 1.2
  (2020), Zenodo. <https://doi.org/10.5281/zenodo.4107192>
- Source repository: <https://github.com/renan-eccel/instances-DDARP-DPDPTW>
- Methods article: Renan Artur Lopes Eccel and Rodrigo Castelan Carlson,
  “Análise de problemas dinâmicos de coleta e entrega e dial-a-ride: métodos de
  dinamização e instâncias de benchmark,” *Transportes* 28(4), 103–116 (2021).
  <https://doi.org/10.14295/transportes.v28i4.2412>
- Dynamic construction: Gerardo Berbeglia, Jean-François Cordeau, and Gilbert
  Laporte, “A Hybrid Tabu Search and Constraint Programming Algorithm for the
  Dynamic Dial-a-Ride Problem,” *INFORMS Journal on Computing* 24(3), 343–355
  (2012). <https://doi.org/10.1287/ijoc.1110.0454>

Redistribution has been confirmed. The source repository declares the MIT
license and the normalized collection preserves its notice. The imported DDARP
release is pinned to commit
`77c301eab45f735734f114fdfefd4da02f19c8b1`; all 68 static/dynamic DDARP pairs
carry file-level source checksums and transitive citations. DPDPTW remains a
named part of the upstream repository, but is outside this passenger DARP
benchmark's scope and is not normalized or scored.

## NYC-DARP and dynamic-ips

- Dataset: Elahe Amiri, Antoine Legrain, and Issmail El Hallaoui, *Manhattan
  Dial-a-Ride Benchmark Dataset with NYC TLC Taxi Trips, 2015–2016*, version 1.0
  (2026), Zenodo. <https://doi.org/10.5281/zenodo.20452171>
- Software: Laboratory for Combinatorial Optimization in Real-time Environment,
  *dynamic-ips*. <https://github.com/lab-core/dynamic-ips>

The NYC-DARP v1.0 Zenodo record declares CC BY 4.0 and redistribution has been
confirmed. The source archive is pinned by SHA-256
`2e52d138260951d29b4a0b084a86a7122a24cfe40c357a7252739add51db2401`.
Warm-start vehicle and onboard files referenced by the dataset software are
absent from that ZIP, so those files are separately pinned to dynamic-ips commit
`c7ba9948501f58babf4d8112e00f821a5b8185b6`, whose software license is MIT.
The normalized collection preserves the following upstream notices:

- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page);
- [OpenStreetMap copyright and license](https://www.openstreetmap.org/copyright);
  and
- [OSRM](https://github.com/Project-OSRM/osrm-backend).

The initial suite includes NYC-DARP only. Other collections present in
dynamic-ips, including Riley_Benchmark, are not implicitly part of v1. The
normalizer records the deterministic exclusion of 23 source rows with
nonpositive passenger counts; it does not silently coerce them into requests.

## Ontra Manhattan TLC 2025-01-22

- Data source: New York City Taxi and Limousine Commission, *TLC Trip Record
  Data: January 2025*.
  <https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page>
- Public-data policies and disclaimers: New York City Open Data.
  <https://cityofnewyork.github.io/opendatatsm/publicpolicies.html>
- Road data: Geofabrik and OpenStreetMap contributors, *US Northeast snapshot,
  replication timestamp 2026-08-05T20:21:23Z*.
  <https://download.geofabrik.de/north-america/us-northeast.html>
- Routing engine: Mobility Solutions Inc's GraphHopper fork, commit
  `80ed17c5fa3f71175949ee0ad44732391172e03a`.
  <https://github.com/mobility-solutions-inc/graphhopper>
- Transformation software: Mobility Solutions Inc, *Ontra Manhattan TLC
  simulation generator*, commit
  `6d4f168a0724a0f0bc7795b57f75fac8cf3010dd`.
  <https://github.com/mobility-solutions-inc/ontra>

Redistribution has been confirmed. TLC-derived demand and fleet components are
released under CC BY 4.0. The GraphHopper road-time matrix retains OpenStreetMap
Open Database License 1.0 attribution and reuse requirements. Every upstream
file is pinned by SHA-256 in the collection archive.

The GraphHopper input is a deterministic `osmium-tool` `complete_ways` crop of
that extract with WGS84 bounding box `[-74.35, 40.45, -73.65, 41.0]`. The
parent extract, crop, crop tool, and container image are independently pinned;
the crop is included in the source archive because the upstream `latest` URL is
mutable.

The released requests are not observed door-to-door passenger trajectories.
TLC supplies pickup and drop-off taxi zones and times; the generator sampled
synthetic points inside those zones and remapped them to a frozen routable point
pool. TLC states that provider-submitted records may be incomplete or inaccurate,
and no City endorsement is implied.

The complete directed matrix uses GraphHopper 11.0's `car` profile with turn
costs and contraction hierarchies. Raw milliseconds are truncated to whole
seconds, multiplied by 1.4, and rounded to the nearest whole second, matching the
Ontra Rust dispatcher's routing semantics. A 1,000-meter high-resolution
location index with `index.max_region_search=8` keeps every frozen point
routable in the compact graph. GraphHopper road distance is retained in
millimeters.

The exact retained 2,000-vehicle Rust-regression fleet is supplemental. The
original generator reused a filename, and a later 500-request pilot overwrote
the fleet generated for the full hour. Three official balanced deployments are
generated at 1,000, 2,000, and 4,000 vehicles. The benchmark preserves the caveat
instead of silently rewriting the historical artifact.

## Reference implementations and values

The design also consults the open-source DARP implementation and compiled
reference values at <https://github.com/brenobeirigo/darp>. No code or data from
that repository is included in v0.1. If incorporated later, its exact version,
license, and scholarly citations will be added here and to affected manifests.

## Import gate

No third-party source enters an official suite until a pull request records:

1. the exact release and immutable retrieval URL;
2. an explicit license or written redistribution permission;
3. all required scholarly and data-provider citations;
4. source and normalized-file SHA-256 checksums;
5. deterministic transformation code and lineage; and
6. privacy and sensitive-data review.
