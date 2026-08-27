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

See the full [data storage and distribution policy](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/DATA_STORAGE.md).
