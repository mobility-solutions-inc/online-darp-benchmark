# Third-Party Notices and Data Provenance

The initial v0.1 repository contains benchmark-owned code, schemas,
documentation, and synthetic examples. **It does not redistribute the source
datasets listed below.** Links and citations are provided because the benchmark
design is based on them and the intended public suite will derive from them.

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

The source code repository declares the MIT license. The Zenodo record labels
the dataset “Other (Open)” without a sufficiently specific redistribution grant.
The methods article is CC BY 4.0. Before importing data, maintainers must confirm
the dataset files' applicable terms, preserve the original notices, pin the exact
release, and record SHA-256 checksums. The original Cordeau, Ropke, and other
instance-family citations carried by the release must be transcribed into the
per-instance provenance records.

## NYC-DARP and dynamic-ips

- Dataset: Elahe Amiri, Antoine Legrain, and Issmail El Hallaoui, *Manhattan
  Dial-a-Ride Benchmark Dataset with NYC TLC Taxi Trips, 2015–2016*, version 1.0
  (2026), Zenodo. <https://doi.org/10.5281/zenodo.20452171>
- Software: Laboratory for Combinatorial Optimization in Real-time Environment,
  *dynamic-ips*. <https://github.com/lab-core/dynamic-ips>

The dynamic-ips repository declares the MIT license. At the time this notice was
written, the Zenodo dataset record did not state a license. It describes derived
NYC Taxi and Limousine Commission trip records, OpenStreetMap road data, and OSRM
travel times. Redistribution therefore remains blocked pending confirmation of
the dataset terms and preservation of all upstream notices, including:

- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page);
- [OpenStreetMap copyright and license](https://www.openstreetmap.org/copyright);
  and
- [OSRM](https://github.com/Project-OSRM/osrm-backend).

The initial suite includes NYC-DARP only. Other collections present in
dynamic-ips, including Riley_Benchmark, are not implicitly part of v1.

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

