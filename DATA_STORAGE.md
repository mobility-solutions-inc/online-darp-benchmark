# Data Storage and Distribution

The benchmark repository does **not** use Git LFS for complete datasets. Git
contains source code, schemas, collection registries, checksums, documentation,
and deliberately tiny test fixtures. Bulk Parquet collections live in immutable
data releases.

## Storage tiers

| Material | Canonical location | Optional mirror |
|---|---|---|
| Public normalized collections | Versioned Zenodo record with DOI | GitHub Release asset when each file is below 2 GiB |
| Upstream source archives | Original author or archival record | None unless required for preservation and permitted |
| Tiny CI fixtures | Git repository | None |
| Future hidden instances | Sponsored S3/R2-compatible object storage | None |

Zenodo is the scholarly record: it supplies a durable DOI, version history, and
dataset metadata. GitHub Releases provide a convenient download path close to the
converter code. Release assets are mirrors, not the scientific identity of a
collection.

## Why not Git LFS

Git LFS is useful when large files must participate in ordinary Git checkout,
but that is not required here. Complete benchmark users download a collection
once; code contributors should not download hundreds of megabytes on every
clone. LFS storage and bandwidth are also metered, and every replaced object is a
new stored version. Immutable archives avoid that cost and keep repository
history small.

## Collection rules

- Every archive is immutable and named with its source and normalized format
  version.
- Every registry entry records SHA-256, byte size, license, source release, and
  canonical and mirror URLs.
- Every archive includes `collection.yaml`, file-level checksums, citations,
  license notices, deterministic transformation metadata, and a validation
  report.
- Large shared artifacts are stored once. Logical instances reference demand,
  fleet, reveal, network, and optional warm-start components by artifact ID.
- Lookahead points are evaluator parameters and do not duplicate request files.
- A correction creates a new archive version; published bytes are never replaced
  in place.

## Local generation

Generated collections are written outside the repository by default:

```bash
odb-convert-eccel /path/to/instances-DDARP-DPDPTW /data/eccel-ddarp-v1.2
odb-fetch-nyc /data/nyc-source
odb-convert-nyc /data/nyc-source/NYC_Dataset_2015-2016 /data/nyc-darp-v1.0
odb-convert-ontra-manhattan \
  /data/ontra-manhattan-source /data/ontra-manhattan-tlc-2025-01-22-v1 \
  --converter-version 9f28842d0a87e88d0b33da061e26a7911eccc342 \
  --graphhopper-url http://localhost:8991 \
  --osm-pbf-sha256 6769faafd0f994abc45d2b7fe3a3f86520d41b33f0d9ee0350b95d800976e245 \
  --graphhopper-build sha256:acff212715b0fc13b970da5837d51414e7ed1f9464b6cc35c0c3eb2dcb4228b1 \
  --graphhopper-config-sha256 ba5138c4beff955a84172d773dbd1b7a0edb3683258653aae1c0ac5537bb4f68
odb-validate-collection /data/eccel-ddarp-v1.2
odb-validate-collection /data/nyc-darp-v1.0
odb-validate-collection /data/ontra-manhattan-tlc-2025-01-22-v1
```

The NYC converter requires the uniform fleets from the v1.0 Zenodo archive and
the warm-start vehicle/onboard files from the pinned `dynamic-ips` commit. The
collection manifest records both origins.

## Future hidden evaluation

Hidden instances should use private object storage with short-lived download
credentials issued only to benchmark workers. Compute workers delete inputs and
outputs after scoring. This phase should begin only with sponsorship sufficient
to cover storage, egress, execution, monitoring, and abuse controls; it is not a
requirement for the public-only launch.
