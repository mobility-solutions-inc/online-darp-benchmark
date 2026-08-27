---
layout: default
title: Submit
---

# Submit an instance or result

Public submissions are reviewable pull requests backed by machine-readable
manifests. Confidential submissions use an isolated private intake channel.

## Public instances

Provide a stable release, explicit redistribution rights, complete citations,
SHA-256 checksums, deterministic transformations, and one instance manifest per
case. The official suite uses every applicable instance in a declared source
release; a favorable sample cannot replace the full scorecard.

[Open a new-instance pull request](https://github.com/mobility-solutions-inc/online-darp-benchmark/compare)

## Hidden instances

First open a metadata-minimal intake request. It is public, so provide only your
GitHub handle, rights status, and coarse upload size. Do not include any dataset
description, geography, dates, counts, filenames, samples, citations, generator
settings, checksum, credential, or download link. If your identity must remain
private, use the confidential contact in `MAINTAINERS.md` instead.

A maintainer will create a dedicated private staging repository and provide the
confidential manifest, access-ledger, and transfer instructions. Each submission
is isolated from other contributors. Hidden data never enters a public pull
request.

[Request a hidden-instance intake channel](https://github.com/mobility-solutions-inc/online-darp-benchmark/issues/new?template=hidden-instance-intake.yml)

## Benchmark results

Provide the result manifest, canonical event log, immutable algorithm artifact,
exact invocation, fixed seeds, hardware, and disclosures for the internal
objective, prediction data, tuning, and relocation. Missing, failed, and
unsupported configurations remain part of the record.

Results are labeled `official`, `contributor_reference`, or `unofficial`. A
hidden-instance contributor may submit a reference result, but it is never
official and does not establish an official rank or record. Official hidden
results require a frozen algorithm, no algorithm-team pre-access, independent
controlled evaluation, and an access attestation. Complete hidden result
artifacts use the private staging route; only approved aggregates and eligibility
information are published.

[Open a new-result pull request](https://github.com/mobility-solutions-inc/online-darp-benchmark/compare)

Read the [complete contribution guide](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/CONTRIBUTING.md)
before submitting.
