# Benchmark Card

Version: 0.1.0 (incubation)

## Purpose

The Online DARP Benchmark evaluates algorithms that dispatch vehicles while
requests arrive over time. It is intended to separate three questions:

1. What outcomes does an algorithm produce online?
2. How do those outcomes change as more future information is revealed?
3. How far are those outcomes from objective-specific offline references that
   know every request in advance?

It is not intended to identify a universal DARP objective or collapse competing
service goals into a single leaderboard number.

## Public benchmark tiers

| Tier | Scale | Reference | Purpose |
|---|---:|---|---|
| Exact classical | Small established instances | Certified optimum or Pareto reference | Online-versus-offline loss |
| Exact realistic | Small samples of realistic demand | Newly certified reference | Realistic geography with exact comparison |
| Bounded medium | Hundreds of requests | Incumbent plus valid bound | Scaling with a known optimality interval |
| Large online | Thousands to full-day demand | Best known feasible result and optional bound | Operational behavior and computation |

Size labels are descriptive, not hard request-count thresholds. Difficulty also
depends on fleet size, time windows, ride-time limits, geography, and objective.

## Request and time semantics

Every request distinguishes:

- `base_reveal_time`: when a causal algorithm first learns the request exists;
- `earliest_pickup_time`: when service may physically begin; and
- pickup/delivery time-window bounds, where applicable.

At simulation time `t`, lookahead `H` exposes a request when:

```text
base_reveal_time <= t + H
```

Advance information never permits pickup before `earliest_pickup_time`.

The standard lookahead curve is 0, 15, 30, 60, and 240 minutes. Full information
is an additional point when computationally meaningful. A method that cannot
accept a full day of requests may report that point as `unsupported`; it is not
counted as an infeasible routing result.

### “Same algorithm with clairvoyance”

A full-information replay uses the same submitted algorithm, version, parameters,
internal objective, physical constraints, execution environment, and compute
limits as its online runs. The only change is information: every request record
for the instance is visible at time zero. Pickup still cannot precede physical
availability. The replay does not know stochastic outcomes that are not encoded
in the instance, and its result is not called optimal merely because it had full
request information.

This replay is distinct from an **offline reference solver**. An offline reference
may use another formulation, algorithm, and documented compute budget to certify
an objective-specific optimum or bound. Reporting both, when tractable, separates
loss caused by limited information from loss caused by the submitted method's own
search or formulation.

Every run separately declares:

- **information horizon**: which requests are visible;
- **planning horizon**: how far ahead routes or consequences are planned; and
- **commitment horizon**: which assignments or route prefixes are locked.

Acceptance semantics must state whether an accepted request can later be
rejected, reassigned, or given a changed pickup promise.

## Offline references

An offline reference sees all requests at time zero but obeys the same physical
system as online algorithms: fleet, initial vehicle state, travel times,
capacities, shifts, service times, passenger constraints, and relocation costs.
It may reposition vehicles in anticipation of demand. This is part of the value
of perfect information.

Optimality is objective-dependent. Consequently, the small suite may publish
multiple references, such as:

- maximum passengers or requests served;
- minimum vehicle or empty distance at a specified service level;
- minimum wait or excess ride time;
- minimum tail lateness; and
- exact or epsilon-constraint points on a Pareto frontier.

Each reference names its objective and constraints and records the solver,
version, hardware, runtime, primal bound, dual bound, gap, solution, and
certificate when available. A large-instance result is called “optimal” only if
optimality is certified.

## Algorithm freedom

The benchmark does not prescribe an algorithm's internal objective. A submission
may use a proxy, weighted objective, policy, reward model, forecast, or another
approach. It must disclose enough to reproduce its behavior, including:

- objective or reward and hard versus soft constraints;
- tuning and penalty parameters;
- planning and commitment policies;
- use of forecast demand and relocation; and
- benchmark or external data used in training or tuning.

The evaluator checks information access and realized outcomes, not whether the
algorithm optimizes a preferred formulation.

## Prediction-data tracks

Results are labeled with one of these tracks:

| Track | Permitted information |
|---|---|
| `none` | No learned demand prediction |
| `provided_only` | Only training data explicitly released for that benchmark split |
| `external_disclosed` | Public or private external data, fully disclosed |

Test requests may never be used before their reveal time except at the declared
lookahead. A hidden suite separates train, validation, and test periods or
generators; confidential intake may begin before official hidden evaluation is
funded. Public evaluation cannot prevent test-set tuning, so results must
disclose it.

## Relocation

Empty relocation is allowed, with or without a prediction component. It uses the
same road network, travel-time model, availability rules, and commitment rules as
other movement. Empty distance and time are always reported separately.

## Required scorecard fields

No composite score is official. The machine-readable result schema records the
following groups individually.

### Algorithm availability

- whether the evaluated algorithm's code is publicly available; and
- a direct public code link when it is available, preferably pinned to the
  evaluated version or commit.

The scorecard renders the availability value as a linked “Yes” when a public
URL is supplied and as “No” otherwise. Public code is encouraged but is not a
condition of official standing; the disclosure allows readers to distinguish
open implementations from reproducible immutable artifacts that are not public.

### Service

- requests and passengers offered, served, rejected, and abandoned;
- request and passenger service rate.

### Passenger experience

- mean and 95th-percentile wait;
- mean and 95th-percentile pickup lateness;
- mean and 95th-percentile in-vehicle time;
- mean and 95th-percentile excess ride time.

### Vehicle operation

- total, occupied, and empty distance;
- total, occupied, and empty driving time;
- utilization.

### Stability

- reassignments after acceptance;
- promised-pickup changes;
- rejections after acceptance.

### Computation

- mean, 95th-percentile, and maximum decision latency;
- run wall time, peak memory, decision epochs, and timeouts.

### Feasibility

- capacity, pickup-window, delivery-window, maximum-ride-time, and route
  continuity violations.

Metrics that do not apply are `null` and accompanied by notes. Zero means the
quantity was measured and no event occurred; `null` must not be silently treated
as zero.

## Result standing

The scorecard and a result's eligibility are separate. Every result is labeled:

- `official` after protocol and conflict review;
- `contributor_reference` when a hidden-instance contributor or algorithm team
  with hidden access supplies useful context; or
- `unofficial` for exploratory, incomplete, self-reported, protocol-deviating,
  or other conflict-affected runs.

A contributor reference can be reproducible and feasible but is never an
official rank or record. Official hidden results require an algorithm frozen
before the run, a disclosed algorithm team, no pre-evaluation hidden access by
that team, no instance-
contributor involvement in algorithm or result selection, independent controlled
evaluation, and an access attestation. The complete proposed policy is
[RFC-0003](proposals/0003-hidden-instance-submission-and-result-eligibility.md).

## Repetition and uncertainty

Deterministic runs use a declared seed and may be submitted once. Stochastic
methods submit all preregistered seeds, not only favorable runs. Scorecard views
should show per-run results plus median and dispersion across the fixed seed set.
Statistical summaries do not replace raw run records.

## Reproducibility record

Each result identifies the exact benchmark version, instance checksum, algorithm
version or commit, public-code availability and link, container digest where
available, parameters, random seed, hardware, operating system, time limit, and
memory limit. The event log is the source of truth for metric recomputation.

## Versioning and comparability

Benchmark releases use semantic versioning:

- patch: clarification or tooling fix that does not change outcomes;
- minor: additive instances, metrics, or optional fields; and
- major: changed semantics, required metrics, instance transformations, or
  comparability rules.

Published results are immutable. Corrections create a new result record that
links to and supersedes the old record.

## Known limitations of the incubation release

- Public instances permit tuning to the test set.
- Large-instance offline optima will usually be unknown.
- Cross-solver travel-time reproduction requires pinned network artifacts.
- The precise standard acceptance and promise semantics still require empirical
  validation before v1.0.
- Source data redistribution is pending a recorded license and provenance audit.
