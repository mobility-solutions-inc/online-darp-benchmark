# RFC-0003: Hidden-Instance Submission and Result Eligibility

- Status: Draft
- Authors: Online DARP Benchmark maintainers
- Created: 2026-08-27
- Discussion: [Issue #7](https://github.com/mobility-solutions-inc/online-darp-benchmark/issues/7)
- Proposed policy version: `0.1.0-draft.1`

## Summary

The benchmark should accept both public and confidential hidden instance
collections. Public collections use ordinary pull requests. Hidden collections
use a dedicated private staging area for each submission, an append-only access
ledger, and a deliberately small public metadata record.

An instance contributor who has seen hidden data may submit a reference result.
That result can be validated and published, but it is permanently classified as
`contributor_reference` and is not official. An official hidden result is possible
only when an immutable algorithm is evaluated under benchmark control and no
algorithm developer had pre-evaluation access to the hidden instances.

Connor Riley has a standing conflict because he administers and can access the
hidden suite. Results for code he authors or controls are therefore ineligible
for official hidden-result status. He may publish them only as clearly labeled
unofficial or contributor reference results.

This RFC is a proposal and does not activate official hidden evaluation. It does
define a safe intake path that can operate before sponsored compute exists.

## Goals

- Let researchers contribute useful public or unreleased instances.
- Keep hidden bytes and sensitive scientific details out of public GitHub areas.
- Prevent one hidden contributor from seeing another contributor's data.
- Record everyone who received access and why.
- Preserve useful contributor-supplied baselines without calling them official.
- Make official-result eligibility a machine-readable property, not an informal
  leaderboard judgment.
- Apply the same conflict rules to maintainers, sponsors, contributors, and
  outside participants.

## Non-goals

- Launching an always-on container evaluation service in this RFC.
- Guaranteeing official evaluation before compute and operations are funded.
- Hiding the benchmark's scoring metrics or public protocol.
- Treating secrecy as a substitute for representative instance design.
- Erasing prior access by deleting a file or leaving a project.

## Definitions

**Public instance**
: An instance whose complete normalized inputs are available to every
  participant under documented redistribution terms.

**Hidden instance**
: An instance whose complete evaluation inputs are restricted to authorized
  instance contributors and evaluation operators. Public metadata may use only
  an opaque identifier.

**Pre-evaluation access**
: Any access before a result-producing run to raw requests, exact reveal
  schedules, fleet states, exact generator seeds, unredacted instance manifests,
  or other information that permits instance-specific development or tuning.
  Deleting a copy later does not remove this status.

**Instance contributor**
: A person or organization that created, selected, transformed, supplied, or
  validated the hidden instances with access to their confidential content.

**Algorithm team**
: People who authored, controlled, tuned, selected, or materially modified the
  evaluated algorithm or its submitted configuration.

**Evaluation operator**
: A benchmark-authorized person or service that runs a frozen algorithm against
  hidden instances. Operator access alone does not disqualify a result when the
  operator is independent of that algorithm's team and follows the controlled
  protocol.

## Two submission routes

| Property | Public collection | Hidden collection |
|---|---|---|
| Initial request | Public proposal issue | Metadata-minimal intake request or private contact |
| Review area | Public pull request | Dedicated private staging repository |
| Bulk data | Zenodo/release asset with checksum | Private release asset or approved object storage |
| Manifest | Public instance/collection manifest | Confidential hidden-submission manifest |
| Access record | Ordinary repository history | Append-only confidential access ledger |
| Suite metadata | Full | Opaque ID; approved summary optional |
| Contributor reference result | Ordinary disclosed result | Allowed, always unofficial |
| Official result | Public protocol | Controlled evaluation plus access eligibility |

## Public instance workflow

The existing `New public instance` pull-request workflow remains authoritative.
It requires redistribution rights, citations, immutable source and normalized
checksums, deterministic conversion, validation, and complete declared source
membership. Public data is never submitted through the hidden path merely to
avoid licensing or scientific review.

## Confidential hidden-instance workflow

### 1. Request an intake channel

A contributor opens the public `Hidden instance intake request` form with only:

- their GitHub handle;
- whether they control redistribution/evaluation rights;
- a coarse upload-size range; and
- whether even their identity must remain confidential.

The form MUST NOT contain instance geography, dates, request counts, generator
parameters, filenames, samples, credentials, or download links. A contributor
who cannot publicly disclose their identity uses the private maintainer contact
listed in `MAINTAINERS.md`.

### 2. Create an isolated staging area

A maintainer assigns an opaque `hidden_submission_id` and creates one dedicated
private repository for that submission. Only that submission's contributors and
authorized benchmark reviewers receive access. A shared contributor-visible
intake repository is prohibited because it would expose submissions to one
another.

The private repository stores the confidential manifest, review record, access
ledger, validation reports, and small artifacts. Bulk inputs remain outside Git
history. During the pilot phase, files below GitHub's release-asset limit may be
attached to a private repository release; larger inputs use approved private
object storage or split immutable parts. Git LFS is not the canonical store.

### 3. Submit the confidential package

The contributor completes `templates/hidden-instance-submission.yaml`, including:

- an opaque submission ID and format version;
- scientific scope, source lineage, citations, and transformation code;
- exact artifact sizes and SHA-256 checksums;
- rights to provide the data for confidential evaluation;
- privacy and sensitive-data review;
- approved public disclosure level;
- every person or organization already known to have access; and
- optional contributor reference results.

The source bytes need not be redistributable to the public, but the contributor
must have authority to provide them to the benchmark for the declared evaluation
and retention purposes. A hidden label never cures unlawful collection or use.

### 4. Review and accept

At least one non-contributing reviewer verifies integrity, format, rights,
privacy, uniqueness, difficulty claims, leakage risk, and evaluator feasibility.
Scientific acceptance and data access are separate decisions. A reviewer sees
raw data only when necessary and is added to the access ledger before access.

Acceptance assigns opaque suite and instance IDs. The public repository records
only the contributor-approved summary. Exact dates, geography, distributions,
counts, checksums, and citations may remain confidential when they would enable
reconstruction or identification.

### 5. Transfer and retention

Accepted bytes move to evaluation-only storage. Staging access may be revoked,
but the access ledger is never rewritten to imply that prior access disappeared.
Retention, deletion, and eventual public release follow the confidential
manifest. Every material download, decryption, copy, or validation access is
recorded.

## Access ledger

Each hidden submission has an append-only confidential ledger containing:

- opaque suite/submission ID;
- person identity and affiliation;
- role and reason for access;
- access scope;
- grant and revocation timestamps;
- approver;
- whether the person belongs to an algorithm team;
- result IDs affected by the conflict; and
- incident or accidental-access notes.

Repository administrators and infrastructure operators with technical ability to
retrieve raw instances count as having access even if they state that they did
not inspect the content. The conservative classification protects trust and
avoids unverifiable distinctions.

Public result records disclose conflicts relevant to that result. The complete
ledger need not identify confidential contributors publicly until their result or
approved attribution is published.

## Result standing

Every new result declares one of three classifications.

### `official`

An official result satisfies the released protocol and independent validation.
For a hidden instance it additionally requires:

- the submitted algorithm artifact and configuration were immutable before the
  hidden run;
- no algorithm-team member had pre-evaluation hidden-instance access;
- no instance contributor participated in algorithm development, tuning,
  configuration selection, or result selection;
- the run was performed by an authorized controlled evaluator;
- all required instances, horizons, and seeds were run under fixed budgets;
- failures and missing runs remain visible; and
- an access attestation and evaluation record are retained.

The evaluation operator may have hidden access. They must be independent of the
algorithm team and may not relay instance-specific feedback beyond the published
protocol.

### `contributor_reference`

A hidden instance contributor or an algorithm team with hidden access may submit
a feasible solution, offline bound, baseline, or online result. It is useful as a
reference but:

- `official` is always `false`;
- it appears in a contextual reference section, not an official comparison;
- its contributor access and tuning opportunity are disclosed;
- it cannot establish a winning claim, official record, or official rank;
- it cannot be relabeled official later; and
- later independent official results do not retroactively validate its standing.

The result still must pass ordinary schema, feasibility, artifact, solver, and
metric validation. “Unofficial” describes eligibility, not permission to submit
unreproducible numbers.

### `unofficial`

Other incomplete, exploratory, self-reported, protocol-deviating, or
conflict-affected results use `unofficial`. The exact reasons remain visible.

## Standing conflict for Connor Riley

Connor Riley is the founding maintainer and has administrative access to hidden
instances and their infrastructure. He therefore adopts this standing rule:

> Code authored or controlled by Connor Riley is ineligible for official results
> on hidden instances. Any such result must be classified `contributor_reference`
> or `unofficial`, even when another operator performs the run.

This is a continuing access-based restriction, not a case-by-case recusal. Connor
may operate evaluations for unrelated algorithms if he has no role in their
development or tuning, but another non-conflicted reviewer must approve and
publish the eligibility decision once governance has enough maintainers.

The standing restriction is recorded in `manifests/hidden-conflicts.yaml` so it
cannot be lost in prose or selectively omitted from a result review.

## Submission timing and anti-tuning rules

Before an official hidden run, the participant submits:

- immutable source commit or container digest;
- exact configuration and random seeds;
- public training/tuning-data disclosure;
- hardware-independent resource request;
- algorithm-team access attestation; and
- consent to publish all run statuses.

Evaluation returns only the released scorecard and diagnostics. It does not
return raw hidden events, per-request failures, routes, or repeated adaptive
feedback unless the public protocol grants the same information and quota to all
participants. Repeated submissions use declared quotas and cooldowns when the
official service launches.

## Leakage and retirement

Suspected disclosure pauses affected official evaluation. Maintainers record the
scope, accessors, affected algorithms, and results. Possible responses include
invalidating results, moving instances to a public/retired set, replacing a suite,
and disclosing an incident after protecting sensitive data.

Revealing a retired suite does not make prior access conflicts disappear. New
results on the now-public suite may use public-instance standing, while historical
hidden results retain the classification they had when produced.

## Appeals

A participant may appeal an eligibility decision with evidence about identity,
algorithm authorship, access scope, or evaluator procedure. A person named in the
conflict does not decide the appeal. Secrecy of the instances is preserved in the
public decision record.

## Adoption plan

1. Review this RFC for the governance minimum.
2. Adopt the confidential submission schema and templates.
3. Add result-standing fields and validation conditions.
4. Record the standing maintainer conflict.
5. Test one synthetic confidential intake without real hidden data.
6. Accept hidden submissions into isolated private staging repositories.
7. Launch official hidden result production only after compute, access controls,
   quotas, retention, and incident response are funded and audited.

## Open decisions before official evaluation

1. Select the sponsored execution and object-storage providers.
2. Set encryption-key custody and recovery rules.
3. Set submission quotas, cooldowns, compute budgets, and disclosure granularity.
4. Define how many independent people must approve an official hidden result.
5. Define a sustainable rotation policy based on leakage evidence rather than a
   fixed high-maintenance schedule.
