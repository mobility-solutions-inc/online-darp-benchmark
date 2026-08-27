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
separately labeled adjacent task and needs a fleet/capacity format extension
before normalization.

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
