# RFC-0002: Solver and Access Disclosure

- Status: Draft
- Created: 2026-08-27
- Discussion: [Issue #5](https://github.com/mobility-solutions-inc/online-darp-benchmark/issues/5)
- Proposed result schema version: `0.2.0`

## Summary

Every benchmark result should state whether it used an external optimization
component and, if so, identify the exact solver or engine, version, role, access
terms, paid-license use, obtainability, threads, and parameters. Official
scorecards should display this information beside outcome metrics.

The benchmark continues to permit commercial, no-cost restricted, open-source,
private, and custom solvers. Disclosure informs reproducibility; it is not a
penalty, eligibility rule, or aggregate-score input.

## Motivation

Two algorithms with similar outcomes may impose very different reproduction
requirements. A researcher may be able to run an OR or routing library from a
public package immediately, qualify for a restricted academic license, need to
purchase commercial access, or be unable to obtain a private optimizer at all.
Naming only the algorithm hides that practical distinction.

Solver name alone is also insufficient. Version, parameters, thread count, and
the license actually used by the reported run can affect both results and access.
The benchmark should report facts about the submitted environment rather than
trying to maintain a permanent classification of third-party products.

## Required result record

The proposed `algorithm.optimization_stack` object contains:

```yaml
optimization_stack:
  uses_external_components: true
  components:
    - component_id: online-mip
      name: <solver-or-engine-name>
      component_type: solver
      version: <exact-version>
      role: online_decision
      license_name: <license-or-terms-used-for-this-run>
      license_url: <versioned-or-canonical-terms-url>
      access_class: <open_source-public_no_cost-restricted_no_cost-commercial-or-private>
      paid_license_used: false
      exact_environment_publicly_obtainable: false
      threads: 8
      parameters:
        <non-default and result-affecting parameters>
      notes: <optional reproduction details>
  notes: <optional stack-level notes>
```

An algorithm with no external optimization dependency records:

```yaml
optimization_stack:
  uses_external_components: false
  components: []
  notes: Optimization logic is included in the algorithm artifact.
```

This explicit form distinguishes “none” from missing disclosure.

## Component types and roles

`component_type` is one of:

- `solver`: mathematical programming, constraint programming, routing, search,
  or another optimization engine;
- `modeling_layer`: a separate model-construction/interface package;
- `routing_engine`: an external shortest-path or travel-time engine; or
- `other_optimization_component`: another external component that materially
  affects decisions.

`role` is one of:

- `online_decision`;
- `offline_reference`;
- `routing_or_travel_time`;
- `training_or_tuning`; or
- `other`.

Multiple components are allowed. For example, a submission can disclose both a
modeling layer and its MIP backend. Containerizing a commercial solver does not
change its access class or make its license publicly obtainable.

## Access classification

The submitter selects the class corresponding to the license used for the
reported run:

| Access class | Meaning |
|---|---|
| `open_source` | Source and license permit use under a recognized open-source license |
| `public_no_cost` | Generally obtainable without payment or eligibility restriction |
| `restricted_no_cost` | No-cost access depends on eligibility, scale, use, or another condition |
| `commercial` | The reported environment is obtained through commercial terms |
| `private` | The exact component is not publicly obtainable |

The benchmark stores `license_name` and `license_url` as the source of truth.
Maintainers do not permanently hard-code a product such as Gurobi, OR-Tools, or
another engine into one class because editions and terms can change. A submission
must state whether it actually used a paid license even when other editions of the
same product exist.

`exact_environment_publicly_obtainable` answers a separate question: can another
member of the public obtain the exact solver edition/version used under the cited
terms? A restricted academic environment can therefore be no-cost for the
submitter while not being publicly obtainable to everyone.

## Scorecard presentation

Every scorecard row gains visible experiment-metadata cells:

| Column | Display |
|---|---|
| Optimization stack | Component names, versions, types, and roles; `None` when empty |
| Access | Each component's declared access class |
| Paid license used | Per-component `Yes` or `No` |
| Exact environment obtainable | Per-component `Yes` or `No` |
| Threads | Per-component thread count |

Detailed views expose license links, parameters, and notes. If several components
exist, the matrix lists each one rather than collapsing them into a “most open” or
“least open” aggregate. Scorecards may provide filters, but solver access does not
change outcome values and is not converted to a composite score.

## Computational metrics

Completed runs additionally report:

- number of external solver calls;
- total wall time spent inside external solvers; and
- number of solver calls ending at their time limit.

These values are zero when no external solver is used and `null` only when a
declared external stack cannot expose the measurement. Notes explain nulls.

## Offline references

Offline reference records obey the same disclosure. Their certificate should
refer to the matching optimization-stack component, while retaining objective,
primal bound, dual bound, gap, runtime, and certificate artifact fields. A paid
solver is allowed for reference generation, but the scorecard must make that
dependency visible.

## Validation

The result schema enforces:

- the disclosure object is always present;
- `uses_external_components: false` requires an empty component list;
- `uses_external_components: true` requires at least one component;
- IDs are unique within the stack;
- versions, access terms, paid-license use, obtainability, and parameters are
  explicit; and
- solver-call metrics agree with an empty stack when the run completed.

Cross-record validation should also reject an offline certificate that names a
solver absent from the disclosed stack.

## Compatibility and adoption

This changes the result schema from `0.1.0` to `0.2.0`. There are no official
public submissions yet, so the synthetic example and result template can migrate
without invalidating scientific results. If accepted, the repository should add
scorecard rendering and filters before accepting v1 submissions.

