# Governance

## Scope

This policy governs benchmark definitions, public and hidden instances, official
and reference results, validation software, documentation, and hidden-test
infrastructure in the Online DARP Benchmark project.

## Roles

- **Users** run the benchmark and report problems.
- **Contributors** submit issues, code, data, documentation, or results.
- **Reviewers** provide documented technical, data, or reproducibility review.
- **Maintainers** merge changes, manage releases, and enforce project policy.
- A future **steering committee** may approve major benchmark versions and hidden
  evaluation policy once at least three independent maintainers participate.

Current maintainers are listed in [MAINTAINERS.md](MAINTAINERS.md). Maintainers
are expected to act for the benchmark's scientific integrity rather than the rank
of a particular algorithm or organization.

## Decision process

Routine fixes use lazy consensus through pull-request review. A change requires a
proposal issue when it would alter comparability, including:

- instance membership or transformation;
- request-reveal, commitment, or feasibility semantics;
- required metrics or their definitions;
- official offline references;
- prediction-data tracks;
- versioning or result-acceptance rules; or
- hidden evaluation construction or access.

The proposal must describe motivation, alternatives, compatibility, migration,
and validation evidence. It remains open for at least 14 calendar days. The
maintainers seek rough consensus and record the decision and dissent. If consensus
is not possible, non-conflicted maintainers decide by simple majority; a tie means
the change does not proceed.

During the single-maintainer incubation period, major semantic changes may be
merged as provisional but cannot define a stable v1 release without an independent
review recorded in the proposal.

## Benchmark integrity

- Official scorecards never publish a project-defined aggregate rank.
- Public suite membership is exhaustive for each declared source/release; changes
  require a benchmark version change.
- Published result artifacts are immutable and corrections are append-only.
- Conflicts, failed runs, unsupported configurations, and missing values remain
  visible.
- Optimality claims require objective-specific evidence and a valid certificate.
- Private test information may not be disclosed selectively.

## Conflicts of interest

Reviewers disclose employment, funding, authorship, close collaboration, or other
interests connected to a submitted algorithm, dataset, or result. A conflicted
maintainer may clarify process but does not cast the deciding review. The decision
record names recusals.

For hidden evaluation, anyone who created, selected, transformed, supplied, or
validated the instances with confidential access is an instance contributor.
Anyone who authored, controlled, tuned, selected, or materially modified an
algorithm or submitted configuration is part of its algorithm team. Official
hidden results require that no algorithm-team member had pre-evaluation access
and that no instance contributor participated in development, tuning,
configuration selection, or result selection for that algorithm.

Every hidden collection has a confidential append-only access ledger. Prior
access remains an eligibility fact after access is revoked, data is deleted, or a
person recuses. Public standing conflicts are recorded in
[manifests/hidden-conflicts.yaml](manifests/hidden-conflicts.yaml).

Connor Riley administers the hidden suite and therefore will not submit or claim
official hidden-instance results for code he authors or controls. Such results
may be published only as `contributor_reference` or `unofficial`, even if another
person operates the evaluation. This standing restriction is access-based and
does not expire through recusal or deletion.

## Releases

Maintainers publish signed or GitHub-verifiable tags, a changelog, suite manifest,
schema version, metric implementation version, and checksums. Releases follow the
compatibility rules in [BENCHMARK_CARD.md](BENCHMARK_CARD.md).

Security, privacy, or licensing problems may require withdrawing an artifact. The
project records what was removed, why, and whether prior results remain comparable.

## Hidden-instance intake and evaluation

The project may accept confidential hidden collections before sponsored
evaluation compute exists. Intake uses a metadata-minimal public request or
private contact, one isolated private staging repository per submission, a
confidential manifest, and an append-only access ledger. Hidden bytes and
scientific details never enter public issues or pull requests.

An instance contributor may provide a validated reference result, but it is
permanently `contributor_reference` and cannot establish an official record or
rank. Official hidden evaluation is not activated until the project publishes
and funds independent evaluator access, submission quotas, compute budgets,
retention, incident response, and leakage controls. Sponsors may fund
infrastructure but may not receive privileged test access or favorable scoring
treatment. The detailed proposal is
[RFC-0003](proposals/0003-hidden-instance-submission-and-result-eligibility.md).

## Maintainer changes

An active contributor may be nominated after sustained, constructive work and
approval by the existing non-conflicted maintainers. A maintainer may resign at
any time. Maintainers may be removed for prolonged inactivity, policy violations,
or loss of trust after notice and a documented vote by the other maintainers.

## Appeals and amendments

A contributor may appeal a benchmark decision by opening a governance issue with
new technical or process evidence. Amendments to this policy follow the same
14-day proposal process as other benchmark-changing decisions.
