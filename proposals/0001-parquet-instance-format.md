# RFC-0001: Parquet Instance Package Format

- Status: Draft
- Authors: Online DARP Benchmark maintainers
- Created: 2026-08-27
- Discussion: [Issue #2](https://github.com/mobility-solutions-inc/online-darp-benchmark/issues/2)
- Proposed format version: `1.0.0-draft.1`

## Summary

Normalized benchmark instances should use Apache Parquet for tabular data and a
small YAML control plane for composition, provenance, licensing, and integrity.
An instance is not one monolithic file. It is a manifest-defined combination of
five required reusable components and one optional initial-state component:

1. physical requests;
2. a request reveal schedule;
3. a fleet deployment;
4. nodes; and
5. static directed travel times.

An optional `onboard_requests` table represents passengers already in vehicles
at simulation start. It is required whenever a fleet has a nonzero initial load.

Separating physical requests from reveal times is central to the design. Many
online information scenarios can share exactly the same offline physical problem,
so they can also share its objective-specific offline references.

This RFC is a proposal, not yet an accepted benchmark contract. Normative words
such as MUST and SHOULD describe the proposed contract.

## Decision in one page

| Concern | Proposal |
|---|---|
| Tabular normalized data | Parquet files |
| Human-readable control plane | YAML manifests |
| Small and large sources | Same logical schemas |
| Physical demand vs. information | Separate `requests` and `reveal_times` tables |
| Shared NYC network/fleet assets | Referenced, never copied per logical instance |
| Time | Signed `int64` milliseconds relative to service start |
| Distance | Nonnegative `int64` millimeters |
| Joins | Stable string IDs plus contiguous `int32` indices |
| Geospatial nodes | GeoParquet 1.1.0 WKB profile |
| Abstract nodes | `float64` Cartesian coordinates with an explicit unit |
| Travel times | Sorted long-form directed all-pairs table; optional sharding |
| Parquet compatibility | Format 1.0, Data Page V1, ZSTD, no INT96 |
| Integrity | SHA-256 for every file and physical-problem fingerprint |
| Extensibility | Namespaced extension columns; no opaque core JSON blobs |

## Goals

- Give algorithms one source-independent input contract.
- Support both small exact instances and large NYC-DARP instances.
- Preserve the distinction between information time and physical service time.
- Avoid duplicating large networks, matrices, fleets, or physical requests.
- Permit selective reads and efficient conversion to in-memory matrices.
- Be practical in Python, Rust, Java, C++, R, DuckDB, and other Parquet readers.
- Make every official instance, transformation, and offline reference pin exact
  bytes and exact physical semantics.
- Preserve original data, licenses, citations, and source-to-normalized lineage.

## Non-goals

- Replacing original source archives with Parquet.
- Standardizing algorithm internals, online objectives, or solver file formats.
- Encoding event logs or result scorecards in this RFC.
- Supporting arbitrary time-dependent routing engines in format v1.
- Treating a Parquet file checksum as a proof that its scientific content is
  correct.

## Why Parquet plus YAML

Parquet provides typed columns, nullability, compression, column projection,
statistics, and row groups. Those properties are useful for both a 16-request
classical instance and a multi-million-row travel-time table. A manifest is still
needed because citations, licenses, transformations, component composition, and
checksums are not naturally modeled as repeated data rows.

Parquet is the normalized **data plane**. YAML is the **control plane**. BibTeX,
license text, solver certificates, and unchanged upstream artifacts remain in
their natural formats. “Parquet wherever possible” does not mean transcoding PDFs,
licenses, or opaque road-engine indexes into Parquet.

## Package layout

One source release is normalized into a collection package:

```text
collections/<source-id>/<source-release>/
├── collection.yaml
├── citations.bib
├── LICENSES/
│   └── <upstream notices>
├── provenance/
│   ├── transformations.yaml
│   └── source-checksums.sha256
├── tables/
│   ├── networks/<network-id>/nodes.parquet
│   ├── networks/<network-id>/travel-times/
│   │   ├── part-00000.parquet
│   │   └── part-00001.parquet
│   ├── demand/<demand-id>/requests.parquet
│   ├── demand/<demand-id>/reveals/<reveal-schedule-id>.parquet
│   └── fleets/<fleet-id>/
│       ├── vehicles.parquet
│       └── onboard-requests.parquet   # optional warm-start state
└── instances/
    ├── <instance-id>.yaml
    └── ...
```

A single-file travel-time table is named `travel-times.parquet`. The directory
form is used only when sharding is needed. Paths in manifests are relative to the
collection root, use `/`, and MUST NOT contain `..`.

The benchmark repository may store only manifests and retrieve large immutable
Parquet files from a release asset or archival repository. Remote artifacts obey
the same schema, size, row-count, and checksum rules.

### Reuse rather than copying

NYC request windows, fleet deployments, and network data form a cross-product.
Copying the travel-time matrix into every instance would waste storage and make
updates error-prone. Each component is stored once and referenced by many instance
manifests. An instance is immutable because every referenced file has a checksum,
not because every file sits in the same directory.

## Collection manifest

`collection.yaml` catalogs source provenance and artifacts. It MUST contain:

- `format_version`;
- a stable `collection_id` and `collection_version`;
- source release, canonical URL, citations, and license notices;
- every artifact ID, role, schema name/version, file locator, SHA-256, byte size,
  row count, and sort keys;
- converter source/version, parameters, and random seed where applicable; and
- the exhaustive list of instance manifests in that normalized release.

Every artifact locator is exactly one of:

- `path`, for a file inside the package; or
- immutable `uri`, for an external artifact.

Mutable branch URLs and unversioned “latest” download URLs are forbidden.

See the draft [collection manifest](0001-parquet-collection.example.yaml) and
[instance manifest](0001-parquet-instance.example.yaml) for complete composition
examples. Their placeholder checksums describe the contract; they are not
published instance artifacts.

## Instance manifest and composition

Each instance manifest identifies one experimental scenario and references these
artifact roles:

```yaml
format_version: 1.0.0-draft.1
instance_id: eccel-v1.2.darp-a01.reveal-original.fleet-original
physical_problem_id: eccel-v1.2.darp-a01.fleet-original
physical_problem_sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
problem_family: darp
tier: exact_classical
components:
  requests: eccel-v1.2.darp-a01.requests
  reveal_times: eccel-v1.2.darp-a01.reveal-original
  vehicles: eccel-v1.2.darp-a01.fleet-original
  nodes: eccel-v1.2.darp-a01.nodes
  travel_times: eccel-v1.2.darp-a01.travel-times
time:
  semantics: relative_elapsed
  unit: millisecond
  service_horizon_ms: 86400000
  source_time_origin: null
spatial:
  profile: abstract_cartesian
  coordinate_unit: source_unit
relocation:
  allowed: true
  destinations: nodes.relocation_allowed
```

`physical_problem_id` and `physical_problem_sha256` exclude only the reveal
schedule. They include requests, fleet, optional onboard state, nodes, travel
times, service horizon, and relocation semantics. Therefore, changing
`reveal_times` alone MUST leave both
physical-problem fields unchanged. Offline references key to the physical problem,
not the online reveal schedule.

The draft reference tooling constructs the fingerprint as SHA-256 over canonical
UTF-8 JSON: keys sorted, no insignificant whitespace, and no non-finite numbers.
The object contains `format_version`; file-digest lists for `requests`,
`vehicles`, `nodes`, `travel_times`, and optional `onboard_requests`;
`service_horizon_ms`; and the relocation fields. It deliberately avoids
writer-dependent logical reserialization.

## Common table contract

All tables MUST satisfy these rules:

- Explicit Arrow/Parquet schemas are used; type inference is forbidden in release
  converters.
- Column names use lowercase `snake_case` ASCII.
- Core IDs are nonempty UTF-8 strings normalized to Unicode NFC.
- Each entity has a human-stable string ID and a zero-based contiguous `int32`
  index. Integer indices are the foreign keys used in large fact tables.
- Rows are sorted by the table's declared sort keys before writing.
- Required fields are never null. Optionality is defined per schema, not inferred
  from observed values.
- Floating-point NaN and positive/negative infinity are forbidden.
- Times and durations are signed `int64` milliseconds unless a narrower type is
  explicitly listed. Distances are `int64` millimeters.
- Absolute timestamps are not used for simulation semantics. Real-world source
  timestamps may be recorded in manifest provenance as RFC 3339 strings.
- Empty strings do not stand in for null.
- Unknown columns are rejected unless they use the extension convention below.
- Every file includes the required benchmark key-value metadata.

### Required Parquet file metadata

Each file MUST contain UTF-8 key-value metadata:

| Key | Meaning |
|---|---|
| `online_darp.format_version` | Instance package format version |
| `online_darp.schema_name` | Registered table schema name |
| `online_darp.schema_version` | Table schema version |
| `online_darp.collection_id` | Owning normalized collection |
| `online_darp.artifact_id` | Artifact ID from `collection.yaml` |

Geospatial node tables additionally contain the metadata required by GeoParquet.
Parquet's own `FileMetadata.version` is not used as the benchmark schema version.

## Core table schemas

The companion
[`0001-parquet-instance-format.schemas.yaml`](0001-parquet-instance-format.schemas.yaml)
is the machine-readable draft. The tables below are the normative human-readable
form.

### `requests` — physical demand

One row represents one paired pickup and drop-off request. No reveal-time field is
allowed in this table.

| Column | Arrow type | Null? | Constraint/meaning |
|---|---|---:|---|
| `request_index` | `int32` | No | Primary key, contiguous `0..N-1` |
| `request_id` | `string` | No | Unique stable normalized ID |
| `source_request_id` | `string` | Yes | Original source identifier |
| `party_size` | `int32` | No | At least 1 |
| `pickup_node_index` | `int32` | No | Foreign key to `nodes` |
| `dropoff_node_index` | `int32` | No | Foreign key to `nodes` |
| `earliest_pickup_time_ms` | `int64` | No | Physical availability, at least 0 |
| `latest_pickup_time_ms` | `int64` | Yes | Null means no pickup upper bound |
| `earliest_dropoff_time_ms` | `int64` | Yes | Null means no drop-off lower bound |
| `latest_dropoff_time_ms` | `int64` | Yes | Null means no drop-off upper bound |
| `max_ride_time_ms` | `int64` | Yes | Positive when present |
| `pickup_service_time_ms` | `int64` | No | Nonnegative |
| `dropoff_service_time_ms` | `int64` | No | Nonnegative |

An arrive-by request still needs an explicit physical earliest pickup time. Time
windows must be internally ordered when both bounds exist. The request table
contains physical constraints only; an algorithm's rejection penalties or
objective weights do not belong here.

### `reveal_times` — information schedule

Exactly one row exists for every request in the referenced physical demand table.

| Column | Arrow type | Null? | Constraint/meaning |
|---|---|---:|---|
| `request_index` | `int32` | No | Primary/foreign key to `requests` |
| `base_reveal_time_ms` | `int64` | No | Time a causal `H=0` method learns the request |

Reveal time may be negative when a request is known before service start. It may
also be later than the earliest pickup in an intentionally difficult schedule,
but validators flag that case as a diagnostic. Lookahead is applied by the
evaluator using `base_reveal_time_ms <= t + H`; separate Parquet files are not
created for 15-, 30-, 60-, or 240-minute lookahead points.

Every derived reveal schedule records its parent request checksum, generator
version, parameters, seed, and output checksum in `collection.yaml`.

### `vehicles` — fleet deployment

One row represents one vehicle at the start of the simulation.

| Column | Arrow type | Null? | Constraint/meaning |
|---|---|---:|---|
| `vehicle_index` | `int32` | No | Primary key, contiguous `0..V-1` |
| `vehicle_id` | `string` | No | Unique stable normalized ID |
| `source_vehicle_id` | `string` | Yes | Original source identifier |
| `start_node_index` | `int32` | No | Initial node |
| `end_node_index` | `int32` | Yes | Required terminal node; null means unrestricted |
| `shift_start_time_ms` | `int64` | No | Vehicle becomes available |
| `shift_end_time_ms` | `int64` | No | Must be at terminal, if any, by this time |
| `max_route_duration_ms` | `int64` | Yes | Positive maximum elapsed route duration; null means none |
| `seat_capacity` | `int32` | No | At least 1 |
| `initial_load` | `int32` | No | Nonnegative and no greater than capacity |

`initial_load` MUST equal the total `party_size` assigned to the vehicle in the
optional `onboard_requests` component. If the component is absent, all initial
loads MUST be zero.

### `onboard_requests` — optional warm-start state

This component is present only when passengers have already been picked up at
simulation start. It makes the initial condition explicit rather than hiding it
inside algorithm state.

| Column | Arrow type | Null? | Constraint/meaning |
|---|---|---:|---|
| `onboard_request_index` | `int32` | No | Primary key, contiguous `0..B-1` |
| `onboard_request_id` | `string` | No | Unique stable normalized ID |
| `source_request_id` | `string` | Yes | Original source identifier |
| `party_size` | `int32` | No | At least 1 |
| `pickup_node_index` | `int32` | No | Completed pickup location |
| `dropoff_node_index` | `int32` | No | Pending drop-off location |
| `earliest_pickup_time_ms` | `int64` | No | Original physical availability |
| `pickup_time_ms` | `int64` | No | Realized pickup time |
| `pickup_departure_time_ms` | `int64` | No | Realized pickup departure time |
| `assigned_vehicle_index` | `int32` | No | Vehicle carrying this party |
| `dropoff_route_position` | `int32` | No | Source warm-start route position, at least 1 |
| `max_ride_time_ms` | `int64` | Yes | Positive bound when imposed by the instance |
| `dropoff_service_time_ms` | `int64` | No | Nonnegative |

Times may be negative because the pickup can precede service start. A source may
also schedule a warm-start departure just after the nominal start; converters
preserve that state and report it rather than shifting times.

### `nodes` — service and relocation locations

All node tables have these core columns:

| Column | Arrow type | Null? | Constraint/meaning |
|---|---|---:|---|
| `node_index` | `int32` | No | Primary key, contiguous `0..K-1` |
| `node_id` | `string` | No | Unique stable normalized ID |
| `source_node_id` | `string` | Yes | Original network/source identifier |
| `relocation_allowed` | `bool` | No | Vehicle may intentionally wait/reposition here |

The instance selects exactly one spatial profile:

- `matrix_only`: no coordinate columns are required;
- `abstract_cartesian`: non-null `x` and `y` `float64` columns plus an explicit
  coordinate unit in the manifest; or
- `geographic`: a non-null Point `geometry` column encoded as WKB under
  GeoParquet 1.1.0, with an explicit CRS. The `.parquet` extension and
  `application/vnd.apache.parquet` media type are used.

Coordinates are descriptive. The travel-time table remains authoritative for
movement and feasibility.

### `travel_times` — static directed matrix

The v1 core profile uses a long table rather than a wide table or nested arrays:

| Column | Arrow type | Null? | Constraint/meaning |
|---|---|---:|---|
| `from_node_index` | `int32` | No | Foreign key to `nodes` |
| `to_node_index` | `int32` | No | Foreign key to `nodes` |
| `travel_time_ms` | `int64` | No | Nonnegative directed travel time |
| `distance_mm` | `int64` | Yes | Nonnegative; null when source has no distance |

The composite primary key is `(from_node_index, to_node_index)`, which is also the
required sort order. A core matrix has exactly `K²` rows, including a zero-time
diagonal. Symmetry is not required. Triangle inequality is reported as a
diagnostic rather than required because a source may intentionally encode a
different model.

Large matrices may be split into files by contiguous `from_node_index` ranges.
Every shard has the identical schema, each pair appears exactly once across the
artifact, and `collection.yaml` lists shards in sort order with individual
checksums and row counts. Hive-style implicit partition columns are not used.

Time-dependent matrices, stochastic travel times, and graph-backed or remote
oracles require a later registered profile. They must not masquerade as this
static-matrix schema.

## Extension columns and new variants

An experimental column may use:

```text
x_<organization>__<column_name>
```

Its Arrow type, nullability, unit, semantics, and owner are declared in the
collection manifest. Core readers may preserve and ignore it. An extension MUST
NOT change core feasibility or official core metrics unless a benchmark variant
registers it through governance. Opaque JSON “attributes” columns are discouraged;
typed columns or separate typed tables are preferred.

Multidimensional capacities, accessibility requirements, heterogeneous service
rules, and time-dependent travel are likely early registered extensions. They are
not silently encoded in `party_size` or free text.

## Physical Parquet interoperability profile

The logical schema is authoritative; encoding choices do not change values. The
reference release writer should use this conservative profile:

```text
Parquet logical-type compatibility: version 1.0
Data pages:                         version 1.0
Compression:                        ZSTD, level 3
Dictionary encoding:                enabled
Statistics:                         enabled
Deprecated INT96 timestamps:        disabled
Stored Arrow schema:                enabled
Compliant nested types:             enabled
Maximum rows per row group:          1,048,576
```

Core tables deliberately avoid timestamps, unsigned integers, decimals, maps, and
nested lists, so the Parquet 1.0 compatibility profile is sufficient. The writer
implementation and exact version are pinned in transformation provenance because
byte-for-byte output can differ between writer releases.

Writers SHOULD target compressed files between roughly 64 MiB and 512 MiB when a
table needs sharding. Small tables remain single files. A release MUST NOT be
rewritten merely to improve compression: changed bytes produce a new artifact
checksum and normalized collection version.

## Integrity and provenance

For every Parquet file, the manifest records:

- SHA-256 of exact bytes;
- byte size;
- row count;
- schema name and version;
- sort keys;
- source artifact checksum;
- converter commit and dependency lock;
- parameters and random seed; and
- required license/citation identifiers.

Parquet footer metadata is inspected but never trusted instead of the external
manifest checksum. Source artifacts remain available unchanged when licensing
permits; otherwise an immutable retrieval record and checksum are retained.

## Validation levels

The reference validator reports four independent levels.

### 1. Package integrity

- Manifest schema and format version are recognized.
- Every path is safe and every URI immutable.
- Bytes, row counts, and SHA-256 values match.
- Citations, licenses, and transformation lineage are present.

### 2. Table contract

- Required metadata, fields, physical types, nullability, and sort order match.
- Primary keys are unique and integer indices are contiguous.
- String IDs are unique and normalized.
- No forbidden float values or unregistered columns occur.

### 3. Cross-table integrity

- Request, vehicle, and matrix node indices exist.
- Reveal rows match request indices one-to-one.
- The directed matrix contains every ordered pair exactly once.
- Component IDs and file metadata agree with the manifests.

### 4. DARP semantics

- Time windows are ordered and service durations are nonnegative.
- Vehicle shifts and capacities are valid.
- Warm-start vehicle loads equal their onboard passenger rows.
- Matrix diagonals are zero and values are nonnegative.
- Every request is individually physically serviceable, or is explicitly marked
  as an intended infeasible/adversarial case by a registered variant.
- Reveal-after-service-window, asymmetry, triangle violations, duplicate
  coordinates, and disconnected-looking data are visible diagnostics.

Validation output is a machine-readable report. Warnings do not silently mutate
data.

## Versioning

The package format and each table schema use semantic versioning independent of
benchmark-suite releases and the Parquet specification's own version field.

- Patch: clarification or stricter validation of already-invalid data.
- Minor: new optional metadata, extension, or table profile that old readers can
  safely ignore or reject explicitly.
- Major: changed field meaning, unit, key, nullability, physical type, or physical
  problem semantics.

Official instance IDs are immutable. Corrected normalized data gets a new
collection version and checksums. Old manifests remain archived so published
results stay interpretable.

## Mapping the initial sources

### Eccel v1.2

- Static physical request fields become `requests.parquet`.
- Dynamic `arrival_time` becomes `base_reveal_time_ms` in a separate
  `reveal_times` table.
- Instance coordinates become the abstract Cartesian node profile unless a
  source-specific CRS is documented.
- The source's `ceil(EuclideanDistance)` travel-time rule is deterministically
  expanded into the complete long-form matrix.
- Additional reveal generators create small new reveal tables, not duplicate
  physical request tables.

### NYC-DARP v1.0

- Each solver-ready service window becomes one physical demand artifact.
- Source rows with nonpositive `passenger_count` are excluded and counted in
  provenance because they are not valid passenger requests; values are never
  silently coerced.
- Original request timestamps map to a reveal schedule after the source time
  origin and timezone are explicitly recorded.
- Virtual stops use GeoParquet Point WKB with the documented CRS.
- The shared edge-time matrix becomes one reusable long-form matrix.
- Vehicle deployment files become reusable fleet artifacts. Logical instances
  reference demand, fleet, and network components without copying them.
- Warm-start fleet files and their onboard passengers use the optional initial
  state component; 7:00 demand windows use compatible uniform fleets and 11:00
  windows use compatible warm-start fleets.

Redistribution has been confirmed for both pinned releases. Normalized archives
retain dataset, NYC TLC, OpenStreetMap, OSRM, and software notices alongside the
source and normalized checksums.

## Adoption plan

1. Review this RFC for at least the governance minimum.
2. Review the complete Eccel DDARP and NYC-DARP draft conversions and reports.
3. Measure matrix read latency, memory conversion, and cross-language behavior.
4. Validate representative fixtures with a Rust Parquet/Arrow reader.
5. Finalize the collection and instance manifest JSON Schemas.
6. Publish immutable normalized collection archives and checksums.
7. Accept the format before official reference solutions or scorecards are
   released.

## Open decisions

1. Confirm milliseconds rather than microseconds as the only v1 time precision.
2. Confirm the long-form complete matrix after measuring the largest NYC network.
3. Confirm GeoParquet 1.1.0 rather than the current 2.0 release candidate.
4. Decide whether `distance_mm` should be required by deriving missing NYC
   distances or remain nullable.
5. Register multidimensional capacity/accessibility tables in core v1 or the first
   minor extension.

## References

- [Apache Parquet file format](https://parquet.apache.org/docs/file-format/)
- [Apache Parquet logical types](https://parquet.apache.org/docs/file-format/types/logicaltypes/)
- [Apache Parquet format-version guidance](https://parquet.apache.org/docs/file-format/versions/)
- [Apache Arrow Parquet writer options](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html)
- [GeoParquet 1.1.0 specification](https://geoparquet.org/releases/v1.1.0/)
