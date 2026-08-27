# Contributing

Thank you for helping build a reproducible online DARP benchmark. Contributions
may include public or confidential hidden instances, benchmark results,
validators, reference solutions, metric definitions, documentation, and bug
fixes.

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
Benchmark-changing decisions follow [GOVERNANCE.md](GOVERNANCE.md).

## Before opening a pull request

1. Search existing issues and pull requests.
2. Open a proposal issue before changing benchmark semantics, adding a source
   family, or introducing a required metric.
3. Keep one conceptual change per pull request.
4. Do not commit secrets, personal passenger data, or data you cannot legally
   redistribute.

Public and hidden instances use different submission routes. Never open a pull
request containing hidden data, a private download link, confidential metadata,
or a hidden-instance checksum.

## Development setup

```bash
python -m pip install -e '.[dev]'
pytest
odb-validate instance examples/instance.yaml
odb-validate result examples/result.yaml
odb-validate events examples/event-log.jsonl
```

## Submit a new public instance collection

Use the **New public instance** pull-request template. A submission must include:

- a stable source name and release/version;
- an explicit redistribution license or written permission;
- original authors, title, DOI or canonical URL, and required citation;
- source-relative filenames and SHA-256 checksums;
- a schema-valid instance manifest for every instance;
- deterministic transformation code and parameters for every derived field;
- the unmodified source artifact or an immutable retrieval procedure;
- problem-family and tier labels; and
- tests that validate counts, IDs, time semantics, and checksums.

Place manifests under:

```text
instances/<source>/<release>/<instance-id>/instance.yaml
```

Large artifacts may be stored in a release asset or archival repository rather
than Git. The manifest must still pin its URL and checksum. A convenience sample
does not substitute for the complete declared suite.

Derived instances must preserve lineage. In particular, a modified reveal
schedule must record the parent checksum, generator version, random seed,
parameters, and output checksum. `base_reveal_time` and
`earliest_pickup_time` must remain distinct.

### Data review checklist

Maintainers verify:

- licensing and attribution;
- absence or documented treatment of sensitive personal data;
- deterministic retrieval and transformation;
- stable IDs and checksums;
- physical and temporal consistency;
- complete rather than favorable sampling; and
- compatibility with a released benchmark version.

## Submit a confidential hidden instance collection

Open the [**Hidden instance intake request** issue form](https://github.com/mobility-solutions-inc/online-darp-benchmark/issues/new?template=hidden-instance-intake.yml)
with only your GitHub
handle, a rights-status choice, and a coarse upload-size range. The issue is
public: do not identify the dataset or include its geography, dates, counts,
filenames, generator settings, samples, citations, checksums, credentials, or
download links. If even your identity must be private, use the confidential
contact in [MAINTAINERS.md](MAINTAINERS.md).

A maintainer assigns an opaque ID and creates a dedicated private staging
repository for the submission. We do not use a shared contributor-visible intake
repository. Complete these files only inside the assigned repository:

```text
hidden-instance-submission.yaml  # from templates/hidden-instance-submission.yaml
hidden-access-ledger.yaml         # from templates/hidden-access-ledger.yaml
```

The manifest records provenance, rights for confidential evaluation, privacy
review, immutable checksums, all known prior accessors, and any approved public
description. Bulk data stays out of Git history and is transferred through the
private storage method assigned during intake. Public redistribution permission
is not required, but authority for confidential benchmark evaluation is.

Hidden intake can operate before an official hidden evaluation service exists.
Acceptance does not promise an evaluation date. The complete policy and security
model are proposed in
[RFC-0003](proposals/0003-hidden-instance-submission-and-result-eligibility.md).

## Submit benchmark results

Use the **New benchmark result** pull-request template. Put each result at:

```text
results/<benchmark-version>/<algorithm>/<submission-id>/result.yaml
results/<benchmark-version>/<algorithm>/<submission-id>/events.jsonl
```

Include a schema-valid result manifest, complete event log, algorithm source or
immutable artifact, reproducible invocation, license, and a disclosure of the
algorithm authors/controllers/tuners/configurators, internal objective,
prediction/training data, relocation policy, tuning, and hardware. Submit every
required instance/lookahead/seed combination or explicitly
list missing combinations with a run status and reason.

Every result must declare `code_available_publicly`. When it is `true`, provide
`public_code_url` as a public link to the code that produced the result,
preferably pinned to the exact commit reported by `version` and
`artifact_digest`. When it is `false`, `public_code_url` must be `null`. Code
availability is displayed in the scorecard but does not by itself determine a
result's standing.

Every result declares its standing:

- `official` means it passed the released protocol and eligibility review;
- `contributor_reference` is a valid contextual result supplied by someone with
  hidden-instance access and is never official; and
- `unofficial` covers exploratory, incomplete, self-reported, protocol-deviating,
  or otherwise conflict-affected results.

For an official hidden result, the algorithm and configuration must be frozen
before evaluation, its team must not have had hidden-instance access, the
instance contributor must not participate in algorithm development or result
selection, and an authorized independent evaluator must retain an access
attestation. Prior access cannot be undone by deleting data or changing who runs
the algorithm.

A hidden-instance contributor may submit a reference benchmark result. It must
be labeled `contributor_reference`, disclose the access conflict, and is excluded
from official ranks, records, and winning claims. Submit the complete result and
event log through the same private staging channel; the public record contains
only approved aggregates, opaque instance IDs, standing, and conflicts. A hidden
instance checksum may be `null` publicly while its exact value remains in the
confidential manifest.

Do not report a large-instance solution as optimal without a certificate. Do not
replace `null` with zero, omit failed runs, cherry-pick seeds, or calculate an
unofficial composite score in an official scorecard field.

Result corrections are append-only: add a new submission ID and use
`supersedes_result_id`. Historical artifacts stay available unless they contain
sensitive or unlawfully distributed data.

## Add an offline reference

In addition to the result requirements, state the exact objective and constraints
and include the primal bound, dual bound, gap, solver and version, runtime,
hardware, solution, and machine-checkable certificate when supported. A proof of
feasibility alone is not proof of optimality.

## Review and merge

All automated checks must pass. At least one maintainer who did not author the
change and has no relevant data or algorithm conflict must approve benchmark
semantics, datasets, and official results. During
the single-maintainer incubation period, such changes remain marked provisional
until independently reviewed.

Small documentation and tooling fixes may be merged by one maintainer. Releases
are tagged and summarized in [CHANGELOG.md](CHANGELOG.md).

## Licensing contributions

Code and documentation contributions are made under the repository's MIT license
unless a file clearly states another compatible license. Data retains its stated
license. By contributing, you confirm that you have the right to provide the
material under those terms.
