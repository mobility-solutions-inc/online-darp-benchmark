# RFC-0004: Ontra Manhattan TLC public passenger instances

- Status: Draft
- Authors: Connor at Mobility Solutions Inc
- Created: 2026-08-27
- Discussion: https://github.com/mobility-solutions-inc/online-darp-benchmark/issues/9
- Depends on: RFC-0001 Parquet Instance Package Format

## Summary

Add the complete Manhattan hour previously used for Ontra's Rust dispatcher
testing as a public, reproducible passenger dial-a-ride collection. The source
contains 24,325 requests with pickup times from 08:00 inclusive to 09:00
exclusive on 2025-01-22 and four public fleet deployments.

Three balanced deployments are proposed for the official scorecard: 1,000,
2,000, and 4,000 vehicles. The exact surviving historical 2,000-vehicle artifact
is published as supplemental regression data because it has a documented
generation caveat.

## Motivation

The existing public suite begins with Eccel DDARP for small instances and
NYC-DARP for large instances. Publishing this independently generated Manhattan
hour adds a current, high-volume case, preserves a real regression workload, and
demonstrates the standard public-instance intake and Parquet normalization path.

The collection is large-tier data. It does not claim a known optimum and does
not replace the small instances used for objective-specific exact offline
references.

## Source and request semantics

The generator uses official NYC TLC January 2025 FHV, high-volume FHV, green,
and yellow trip records plus taxi-zone geometry. Exact upstream files, source
JSON artifacts, generator code, routing inputs, and transformation code are
pinned by SHA-256 or Git commit.

The data contain zones and trip times rather than door-to-door passenger
coordinates. Ontra sampled synthetic points within the reported zones and then
remapped them to a frozen pool of 25 GraphHopper-routable points for each of 217
zones. The released rows therefore must not be described as observed passenger
trajectories.

The normalized request semantics are:

- `base_reveal_time_ms` equals the observed pickup time;
- `earliest_pickup_time_ms` also equals the observed pickup time;
- no latest pickup, latest drop-off, or maximum ride-time bound is imposed;
- pickup and drop-off service time is 30 seconds; and
- passenger parties are retained, with the generator's documented missing-value
  and capacity policy.

Standard lookahead points are evaluator parameters. For lookahead `H`, the
evaluator exposes a request no later than `base_reveal_time - H`, subject to the
benchmark's time-origin rules. The collection does not duplicate request tables
for each lookahead value.

## Network and travel model

The collection includes 2,750 geographic nodes: every point used by demand or
the historical fleet, plus every frozen point in each of the 66 represented
Manhattan pickup zones. Relocation is allowed at all nodes.

A complete directed 2,750 by 2,750 matrix contains 7,562,500 rows. It uses
GraphHopper 11.0's `car` profile with turn costs and contraction hierarchies over
a deterministic NYC-region crop of the exact Geofabrik US Northeast snapshot
used by the original experiment (replication timestamp
`2026-08-05T20:21:23Z`). The crop uses `osmium-tool`'s `complete_ways`
strategy and WGS84 box
`[-74.35, 40.45, -73.65, 41.0]`, deliberately including adjacent New Jersey so
cross-Hudson routes are not clipped at a state boundary. The parent extract,
crop bytes, osmium build, GraphHopper fork commit, container image,
configuration, a 1,000-meter high-resolution location index with
`index.max_region_search=8`, and server metadata are all pinned. The 148 MB
cropped PBF is included in the source release because Geofabrik's `latest` URL
is mutable.

To match the Ontra Rust dispatcher, raw GraphHopper milliseconds are truncated
to whole seconds, multiplied by 1.4, and rounded to the nearest whole second.
GraphHopper road distance is stored in millimeters. There is no Haversine or
straight-line fallback in the published matrix.

## Fleet deployments

The official fleets use demand-frequency-independent round-robin allocation
across the 66 represented Manhattan pickup zones. A seeded hash chooses among
all 25 frozen pool points in each zone. Each fleet has 75% capacity-five and 25%
capacity-seven vehicles and a four-hour shift horizon.

| Deployment | Vehicles | Suite membership |
|---|---:|---|
| `balanced-manhattan-1000` | 1,000 | Official |
| `balanced-manhattan-2000` | 2,000 | Official |
| `balanced-manhattan-4000` | 4,000 | Official |
| `historical-rust-regression-2000` | 2,000 | Supplemental |

The original generator reused one output filename. A later 500-request pilot
overwrote the fleet generated for the full-hour run, so the surviving historical
fleet locations are demand-weighted from that pilot. The request artifact itself
was regenerated from the pinned upstream TLC files and reproduced byte for byte.
The proposal preserves the historical fleet honestly for regression use while
keeping it out of the official scorecard.

## Distribution, license, and attribution

The Git repository continues to contain no bulk dataset and uses no Git LFS. A
public release carries two immutable assets:

1. the three source JSON artifacts, exact cropped OSM PBF, source metadata,
   notices, GraphHopper build inputs, and checksums;
2. the validated RFC-0001 Parquet collection with manifests and transformation
   lineage.

TLC-derived demand and fleet components are CC BY 4.0. OpenStreetMap-derived
travel data retain ODbL 1.0 attribution and reuse requirements. Notices retain
NYC TLC, OpenStreetMap contributors, Geofabrik, GraphHopper, and Mobility
Solutions Inc attribution. The repository's code and documentation remain MIT
licensed.

## Acceptance criteria

- Exact official source files reproduce all 24,325 request rows and per-provider
  counts.
- Source, generator, GraphHopper build, OSM extract, converter, and normalized
  artifacts are immutably pinned.
- The reference validator passes all four logical instances without warnings.
- Official and supplemental fleet membership is machine-readable.
- The public source and normalized archives are downloadable with published
  byte sizes and SHA-256 checksums.
- Documentation describes synthetic endpoint semantics, travel-time rounding,
  and the historical-fleet caveat without ambiguity.

## Non-goals

- No optimal or best-known offline result is claimed for this large collection.
- No objective function is prescribed for online algorithms.
- No package-delivery or DPDPTW task is introduced.
- No hidden instance or hosted evaluation compute is part of this proposal.
