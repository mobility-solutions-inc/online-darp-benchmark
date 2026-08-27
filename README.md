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
contract, contribution process, schemas, examples, and public source registry.
The source datasets are not yet redistributed here; each complete pinned release
will be imported only after its license, provenance, and checksums are recorded.

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

The intended v1 public suite uses every applicable instance from these pinned
sources:

1. [Eccel et al. DDARP/DPDPTW v1.2](https://doi.org/10.5281/zenodo.4107192)
   for the small tier; and
2. [NYC-DARP v1.0](https://doi.org/10.5281/zenodo.20452171), distributed with
   [dynamic-ips](https://github.com/lab-core/dynamic-ips), for the large tier.

DPDPTW instances will remain available as a separately labeled adjacent task;
they will not be silently mixed into DARP scorecards. See
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
| Reproducibility | solver/engine, version, access terms, paid license, threads |
| Feasibility | capacity, time-window, ride-time, and route violations |

The full metric definitions and execution rules live in
[BENCHMARK_CARD.md](BENCHMARK_CARD.md).

## Repository layout

```text
schemas/       Versioned instance, result, and event-log contracts
templates/     Commented templates for new submissions
examples/      Small schema-valid examples
manifests/     Public source and benchmark-suite registries
src/           Validation command-line tool
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

## Contribute

New public instances and benchmark results are welcome through pull requests.
Start with [CONTRIBUTING.md](CONTRIBUTING.md) and use the matching pull-request
template. Changes to benchmark semantics follow the process in
[GOVERNANCE.md](GOVERNANCE.md).

## License and citation

Benchmark-owned code and documentation are MIT licensed. Source datasets retain
their own licenses and attribution requirements; the MIT license does not
relicense them. Cite this benchmark using [CITATION.cff](CITATION.cff), and cite
each source dataset used in an experiment.

Project site: <https://mobility-solutions-inc.github.io/online-darp-benchmark/>
