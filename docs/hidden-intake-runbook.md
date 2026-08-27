---
layout: default
title: Hidden intake runbook
---

# Hidden-instance intake runbook

This is the maintainer procedure for confidential instance submissions. The
policy is proposed in [RFC-0003](https://github.com/mobility-solutions-inc/online-darp-benchmark/blob/main/proposals/0003-hidden-instance-submission-and-result-eligibility.md).
Do not use this workflow for data that can be submitted publicly.

## 1. Triage without collecting data publicly

Accept only the GitHub handle, rights-status choice, and coarse upload-size band
in the public intake issue. If it contains a hidden link, credential, sample, or
identifying scientific detail, treat that as possible leakage: restrict further
discussion, preserve the incident facts privately, and move to the security
channel. Do not quote the exposed value into another issue.

If the submitter identity itself is confidential, begin through the private
contact in `MAINTAINERS.md` and do not create a public intake issue.

## 2. Assign an opaque ID and isolated repository

Generate an ID that carries no geographic, institutional, temporal, or
scientific meaning. Create one private staging repository for that submission;
never place unrelated submitters in a shared private intake repository.

Initially grant access only to the intake maintainer. Add the confidential
manifest and access-ledger templates, disable public Pages and discussions, block
force pushes, and retain repository audit logs. Record a contributor in the
ledger before inviting that account. A repository administrator with technical
ability to retrieve the data is an accessor even if they do not open a file.

## 3. Transfer artifacts

The private Git repository stores manifests, review records, validation reports,
the access ledger, and small supporting files. Bulk instance data stays outside
Git history. Use a private immutable release asset when suitable, otherwise use
approved private object storage or immutable split parts. Pin every artifact by
SHA-256 and byte size. Git LFS is not canonical hidden-instance storage.

Never request a credential in an issue or manifest. Use a provider's scoped
invitation, short-lived upload link, or equivalent secret-transfer mechanism.

## 4. Review access and science separately

Before granting raw-data access, append the reviewer, exact scope, reason,
approver, and time to the ledger. A reviewer should inspect raw data only when
format, rights, privacy, integrity, uniqueness, or scientific claims cannot be
verified from reports and metadata.

At least one non-contributing reviewer records:

- authority for confidential evaluation and applicable retention terms;
- provenance, citations, transformation reproducibility, and checksums;
- privacy and sensitive-data treatment;
- format validation and evaluator feasibility;
- overlap, reconstruction, and leakage risks; and
- the exact public disclosure approved by the contributor.

## 5. Accept, reject, or hold

Acceptance assigns an opaque suite ID and version. Add only contributor-approved
fields to `manifests/hidden-suites.yaml`. `accepted_evaluation_inactive` means the
data passed intake but no official evaluation service is promised or available.

On rejection or withdrawal, follow the manifest's retention and deletion terms.
Set access revocation times but never remove historical ledger entries. Prior
access remains relevant to result eligibility.

## 6. Handle contributor reference results

The contributor may add a complete result and event log privately. Validate them
normally, then produce a sanitized public result record with:

- `classification: contributor_reference` and `official: false`;
- an opaque instance ID and, if needed, `instance_sha256: null`;
- access and tuning conflicts;
- only approved aggregate scorecard values; and
- a withheld/private artifact marker rather than a raw event-log link.

The result appears as context, never as an official rank, record, or winning
claim. It cannot later be relabeled official.

## 7. Produce official results only after activation

Do not produce official hidden results until compute funding, isolation,
immutable algorithm submission, quotas, access attestations, retention, incident
response, and independent approval are implemented and audited. Hidden intake
alone does not activate official evaluation.
