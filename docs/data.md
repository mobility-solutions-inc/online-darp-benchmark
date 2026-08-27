---
layout: default
title: Data downloads and storage
---

# Data downloads and storage

Complete Parquet collections are kept out of Git and Git LFS. Each immutable
public collection is archived on Zenodo for a durable DOI and may also be
mirrored as a GitHub Release asset. The repository contains converters,
manifests, checksums, and tiny CI fixtures only.

This means the 1,102-stop NYC network, 96 demand windows, and 62 fleet
deployments are stored once. The 2,976 compatible logical instances are small
YAML compositions, not duplicate data bundles.

Every archive includes source and normalized checksums, citations, license
notices, transformation parameters, and a machine-readable validation report.
Published bytes are immutable; corrections receive a new collection version.

## Draft downloads

The RFC-0001 prerelease contains:

- [Eccel DDARP v1.2 Parquet collection](https://github.com/mobility-solutions-inc/online-darp-benchmark/releases/download/parquet-data-v1.0.0-draft.1/eccel-ddarp-v1.2.parquet-draft.1.tar.gz)
  (68 instances, 1,158,386 bytes, SHA-256
  `69aafcc4ac5969b385ecfa611d2a5ed9664b60d8881a05aa4ea293f151cfd4a6`);
- [NYC-DARP v1.0 Parquet collection](https://github.com/mobility-solutions-inc/online-darp-benchmark/releases/download/parquet-data-v1.0.0-draft.1/nyc-darp-v1.0.parquet-draft.1.tar.gz)
  (96 demand windows, 62 fleets, 150,096,002 bytes, SHA-256
  `af1c09a4ce2ea657f0fa751d474c7c259c76ec50f016ab7b611bc2cbbc6507f4`).

These are GitHub prerelease mirrors while the DOI-bearing Zenodo record is
pending. The machine-readable registry is
[`manifests/collections.yaml`](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/proposal/parquet-instance-format/manifests/collections.yaml).

See the full [data storage and distribution policy](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/DATA_STORAGE.md).
