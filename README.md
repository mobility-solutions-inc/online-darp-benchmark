# Online DARP Benchmark

[![Validate](https://github.com/mobility-solutions-inc/online-darp-benchmark/actions/workflows/validate.yml/badge.svg)](https://github.com/mobility-solutions-inc/online-darp-benchmark/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/benchmark_code-MIT-blue.svg)](LICENSE)

A reproducible, multidimensional benchmark for online dial-a-ride (DARP)
algorithms.

The benchmark is designed to show both how online algorithms compare with one
another and how much performance is lost because future requests are unknown.
It combines small instances with objective-specific, certified offline
references and large instances that test operational scale.

This repository is in its **v0.1 incubation phase**. It defines the benchmark
contract, contribution process, schemas, converters, examples, and public source
registry. Complete datasets are distributed as immutable external archives, not
committed to Git or Git LFS; every archive retains provenance, licenses,
citations, and checksums.

## What makes this benchmark different

- **Small and large tiers.** Small instances support exact offline comparison;
  large instances test realistic online performance and computation.
- **Lookahead curves.** Runs vary how much advance notice an algorithm receives:
  0, 15, 30, 60, and 240 minutes, plus full information where meaningful.
- **No single score.** Results remain a scorecard of service, passenger,
  vehicle, stability, feasibility, and computational outcomes.
- **No prescribed internal objective.** Algorithms may use hand-designed,
  learned, or unconventional objectives. The benchmark standardizes realized
  outcomes, not what an algorithm tries to optimize.
- **Prediction and relocation are first-class.** Empty repositioning is allowed,
  and predictive methods declare which training-data track they use.
- **Explicit information and commitments.** Information, planning, and
  commitment horizons are reported separately.

## Initial public corpus

The intended v1 public suite uses every applicable passenger DARP instance from
these pinned sources:

1. [Eccel et al. DDARP v1.2](https://doi.org/10.5281/zenodo.4107192)
   for the small tier;
2. [NYC-DARP v1.0](https://doi.org/10.5281/zenodo.20452171), distributed with
   [dynamic-ips](https://github.com/lab-core/dynamic-ips), for the large tier;
   and
3. [Ontra Manhattan TLC 2025-01-22](https://github.com/mobility-solutions-inc/online-darp-benchmark/releases/tag/ontra-manhattan-tlc-2025-01-22-v1.0.0-draft.1),
   a new public large-instance family derived from NYC TLC records.

The draft conversions currently cover all 68 Eccel DDARP request/reveal pairs and
all 96 NYC-DARP demand windows with all 62 compatible fleet deployments. The
Ontra collection adds one 24,325-request Manhattan demand window with three
official balanced fleet deployments; its exact historical Rust-regression fleet
is available as a clearly labeled supplemental deployment. Its complete road
matrix uses pinned GraphHopper `car` routing with a 1.4 time multiplier and no
Haversine fallback. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution and import
status.

## Scorecard

Each completed run reports individual values rather than an aggregate rank:

| Category | Example fields |
|---|---|
| Service | requests/passengers served and rejected, service rate |
| Passenger | wait, pickup lateness, ride time, excess ride time, tail values |
| Vehicle | total, occupied, and empty distance/time; utilization |
| Stability | reassignments, promise changes, post-acceptance rejections |
| Computation | decision latency, timeout count, wall time, memory |
| Feasibility | capacity, time-window, ride-time, and route violations |

The full metric definitions and execution rules live in
[BENCHMARK_CARD.md](BENCHMARK_CARD.md).

## Repository layout

```text
schemas/       Versioned instance, result, and event-log contracts
templates/     Commented templates for new submissions
examples/      Small schema-valid examples
manifests/     Public source and benchmark-suite registries
proposals/     Draft benchmark-semantic RFCs under public review
src/           Validation and deterministic conversion command-line tools
tests/         Contract tests
docs/          GitHub Pages site
```

## Validate a submission

Python 3.11 or newer is required.

```bash
python -m pip install -e '.[dev]'
odb-validate instance examples/instance.yaml
odb-validate result examples/result.yaml
odb-validate events examples/event-log.jsonl
pytest
```

To generate and validate normalized collections:

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

See [DATA_STORAGE.md](DATA_STORAGE.md) for the Zenodo, GitHub Release, and future
hidden-instance storage policy. Draft downloads and exact archive checksums are
listed in [manifests/collections.yaml](manifests/collections.yaml).

## Contribute

New public instances and benchmark results are welcome through pull requests.
Start with [CONTRIBUTING.md](CONTRIBUTING.md) and use the matching pull-request
template. Changes to benchmark semantics follow the process in
[GOVERNANCE.md](GOVERNANCE.md).

Active design proposals include [RFC-0001, Parquet Instance Package
Format](proposals/0001-parquet-instance-format.md), and [RFC-0004, Ontra
Manhattan TLC public instances](proposals/0004-ontra-manhattan-tlc-public-instances.md).

## License and citation

Benchmark-owned code and documentation are MIT licensed. Source datasets retain
their own licenses and attribution requirements; the MIT license does not
relicense them. Cite this benchmark using [CITATION.cff](CITATION.cff), and cite
each source dataset used in an experiment.

Project site: <https://mobility-solutions-inc.github.io/online-darp-benchmark/>
