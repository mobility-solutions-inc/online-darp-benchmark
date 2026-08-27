"""Convert NYC-DARP v1.0 solver-ready data into RFC-0001 Parquet packages."""

from __future__ import annotations

import argparse
import json
import re
import struct
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .parquet_collection import (
    FORMAT_VERSION,
    artifact_record,
    dump_yaml,
    physical_problem_sha256,
    sha256_file,
    write_parquet,
)


COLLECTION_ID = "nyc-darp-v1.0"
SOURCE_RELEASE = "v1.0"
SOURCE_RECORD = "20452171"
SOURCE_ARCHIVE_SHA256 = "2e52d138260951d29b4a0b084a86a7122a24cfe40c357a7252739add51db2401"
DYNAMIC_IPS_COMMIT = "c7ba9948501f58babf4d8112e00f821a5b8185b6"
SERVICE_TIME_MS = 30_000
NYC_TIME_ZONE = ZoneInfo("America/New_York")
INSTANCE_PATTERN = re.compile(r"^(?P<date>\d{8})_(?P<hour>\d{2})-(?P<minutes>\d+)m$")

CITATIONS_BIB = """@dataset{amiri2026nycdarp,
  author = {Amiri, Elahe and Legrain, Antoine and El Hallaoui, Issmail},
  title = {Manhattan Dial-a-Ride Benchmark Dataset with NYC TLC Taxi Trips, 2015--2016},
  year = {2026},
  version = {1.0},
  doi = {10.5281/zenodo.20452171}
}

@misc{dynamicips,
  author = {{Laboratory for Combinatorial Optimization in Real-time Environment}},
  title = {dynamic-ips},
  url = {https://github.com/lab-core/dynamic-ips},
  note = {Commit c7ba9948501f58babf4d8112e00f821a5b8185b6}
}
"""

UPSTREAM_NOTICES = """# NYC-DARP upstream notices

- NYC-DARP v1.0 is licensed CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
- Dataset DOI and attribution: https://doi.org/10.5281/zenodo.20452171
- NYC Taxi and Limousine Commission trip records: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- OpenStreetMap contributors and ODbL notice: https://www.openstreetmap.org/copyright
- OSRM routing engine: https://github.com/Project-OSRM/osrm-backend
- dynamic-ips software (MIT): https://github.com/lab-core/dynamic-ips
"""


def _section_rows(path: Path, marker: str, field_count: int) -> list[list[str]]:
    rows: list[list[str]] = []
    in_section = False
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not in_section:
                if line == marker:
                    in_section = True
                continue
            if not line:
                continue
            fields = line.split()
            if len(fields) != field_count:
                raise ValueError(
                    f"{path}: expected {field_count} fields after {marker}, got {len(fields)}"
                )
            rows.append(fields)
    if not in_section:
        raise ValueError(f"{path}: missing section {marker}")
    return rows


def _instance_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            if "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def _point_wkb(longitude: float, latitude: float) -> bytes:
    return struct.pack("<BIdd", 1, 1, longitude, latitude)


def _write_component(
    root: Path,
    artifacts: dict[str, Any],
    *,
    artifact_id: str,
    relative_path: str,
    columns: dict[str, list[Any]],
    role: str,
    source_sha256: str | list[str],
    spatial_profile: str | None = None,
    crs: Any = None,
) -> None:
    file_record = write_parquet(
        root / relative_path,
        columns,
        schema_name=role,
        collection_id=COLLECTION_ID,
        artifact_id=artifact_id,
        spatial_profile=spatial_profile,
        crs=crs,
    )
    artifacts[artifact_id] = artifact_record(
        role=role,
        file_record=file_record,
        collection_root=root,
        source_sha256=source_sha256,
        spatial_profile=spatial_profile,
    )


def _network(source: Path, output: Path, artifacts: dict[str, Any]) -> dict[str, str]:
    network_root = source / "1_Network"
    node_source = network_root / "virtual_stops_latlon.geojson"
    node_document = json.loads(node_source.read_text(encoding="utf-8"))
    features = sorted(node_document["features"], key=lambda item: item["properties"]["stop_id"])
    if [item["properties"]["stop_id"] for item in features] != list(range(len(features))):
        raise ValueError("virtual stop IDs are not contiguous and zero-based")
    node_columns: dict[str, list[Any]] = {
        "node_index": [],
        "node_id": [],
        "source_node_id": [],
        "relocation_allowed": [],
        "geometry": [],
    }
    for feature in features:
        properties = feature["properties"]
        stop_id = int(properties["stop_id"])
        longitude, latitude = feature["geometry"]["coordinates"]
        node_columns["node_index"].append(stop_id)
        node_columns["node_id"].append(f"stop-{stop_id}")
        node_columns["source_node_id"].append(str(properties["osmid"]))
        node_columns["relocation_allowed"].append(True)
        node_columns["geometry"].append(_point_wkb(float(longitude), float(latitude)))

    node_id = f"{COLLECTION_ID}.manhattan-virtual-stops.nodes"
    node_sha = sha256_file(node_source)
    _write_component(
        output,
        artifacts,
        artifact_id=node_id,
        relative_path="tables/networks/manhattan-virtual-stops/nodes.parquet",
        columns=node_columns,
        role="nodes",
        source_sha256=node_sha,
        spatial_profile="geographic",
        crs="OGC:CRS84",
    )

    matrix_source = network_root / "edge_time_matrix.txt"
    matrix_rows = _section_rows(matrix_source, "DURATION_INFO", 3)
    expected_rows = len(features) * len(features)
    if len(matrix_rows) != expected_rows:
        raise ValueError(f"travel matrix has {len(matrix_rows)} rows, expected {expected_rows}")
    matrix_columns: dict[str, list[Any]] = {
        "from_node_index": [],
        "to_node_index": [],
        "travel_time_ms": [],
        "distance_mm": [None] * expected_rows,
    }
    for offset, fields in enumerate(matrix_rows):
        origin, destination, duration = (int(value) for value in fields)
        if origin != offset // len(features) or destination != offset % len(features):
            raise ValueError("travel matrix rows are not a sorted complete cross-product")
        matrix_columns["from_node_index"].append(origin)
        matrix_columns["to_node_index"].append(destination)
        matrix_columns["travel_time_ms"].append(duration * 1000)
    travel_id = f"{COLLECTION_ID}.manhattan-virtual-stops.travel-times"
    matrix_sha = sha256_file(matrix_source)
    _write_component(
        output,
        artifacts,
        artifact_id=travel_id,
        relative_path="tables/networks/manhattan-virtual-stops/travel-times.parquet",
        columns=matrix_columns,
        role="travel_times",
        source_sha256=matrix_sha,
    )
    return {"nodes": node_id, "travel_times": travel_id}


def _demand(
    source: Path,
    output: Path,
    artifacts: dict[str, Any],
    instance_root: Path,
) -> dict[str, Any]:
    slug = instance_root.name.lower()
    match = INSTANCE_PATTERN.fullmatch(slug)
    if match is None:
        raise ValueError(f"unexpected NYC instance name: {slug}")
    date = datetime.strptime(match.group("date"), "%Y%m%d")
    hour = int(match.group("hour"))
    duration_minutes = int(match.group("minutes"))
    origin = datetime(date.year, date.month, date.day, hour, tzinfo=NYC_TIME_ZONE)
    simulation_start_seconds = hour * 3600

    metadata_path = next(instance_root.glob("INSTANCE_*.txt"))
    trip_path = next(instance_root.glob("TRIP_*.txt"))
    metadata = _instance_metadata(metadata_path)
    if int(float(metadata["SIMULATION_START"])) != simulation_start_seconds:
        raise ValueError(f"{slug}: simulation start does not match instance name")
    source_trip_rows = _section_rows(trip_path, "REQUESTS_INFO", 6)
    if int(metadata["NUM_REQUESTS"]) != len(source_trip_rows):
        raise ValueError(f"{slug}: request count does not match INSTANCE file")
    trip_rows = [row for row in source_trip_rows if int(row[0]) >= 1]
    excluded_nonpositive_party_size = len(source_trip_rows) - len(trip_rows)

    request_count = len(trip_rows)
    request_columns: dict[str, list[Any]] = {
        "request_index": list(range(request_count)),
        "request_id": [f"request-{index + 1:07d}" for index in range(request_count)],
        "source_request_id": [None] * request_count,
        "party_size": [],
        "pickup_node_index": [],
        "dropoff_node_index": [],
        "earliest_pickup_time_ms": [],
        "latest_pickup_time_ms": [None] * request_count,
        "earliest_dropoff_time_ms": [None] * request_count,
        "latest_dropoff_time_ms": [None] * request_count,
        "max_ride_time_ms": [None] * request_count,
        "pickup_service_time_ms": [SERVICE_TIME_MS] * request_count,
        "dropoff_service_time_ms": [SERVICE_TIME_MS] * request_count,
    }
    reveal_columns: dict[str, list[Any]] = {
        "request_index": list(range(request_count)),
        "base_reveal_time_ms": [],
    }
    for fields in trip_rows:
        party_size, pickup, dropoff, request_time, _pickup_district, _dropoff_district = (
            int(value) for value in fields
        )
        relative_time_ms = (request_time - simulation_start_seconds) * 1000
        request_columns["party_size"].append(party_size)
        request_columns["pickup_node_index"].append(pickup)
        request_columns["dropoff_node_index"].append(dropoff)
        request_columns["earliest_pickup_time_ms"].append(relative_time_ms)
        reveal_columns["base_reveal_time_ms"].append(relative_time_ms)

    trip_sha = sha256_file(trip_path)
    metadata_sha = sha256_file(metadata_path)
    prefix = f"{COLLECTION_ID}.{slug}"
    requests_id = f"{prefix}.requests"
    reveals_id = f"{prefix}.reveal-original"
    _write_component(
        output,
        artifacts,
        artifact_id=requests_id,
        relative_path=f"tables/demand/{slug}/requests.parquet",
        columns=request_columns,
        role="requests",
        source_sha256=[trip_sha, metadata_sha],
    )
    _write_component(
        output,
        artifacts,
        artifact_id=reveals_id,
        relative_path=f"tables/demand/{slug}/reveals/original.parquet",
        columns=reveal_columns,
        role="reveal_times",
        source_sha256=trip_sha,
    )
    return {
        "slug": slug,
        "requests": requests_id,
        "reveal_times": reveals_id,
        "service_horizon_ms": duration_minutes * 60_000,
        "source_time_origin": origin.isoformat(),
        "start_hour": hour,
        "trip_path": trip_path,
        "metadata_path": metadata_path,
        "source_default_vehicle_count": int(metadata["NUM_VEHICLES"]),
        "source_request_count": len(source_trip_rows),
        "excluded_nonpositive_party_size": excluded_nonpositive_party_size,
    }


def _uniform_fleet(
    output: Path,
    artifacts: dict[str, Any],
    path: Path,
    simulation_start_seconds: int,
) -> dict[str, Any]:
    rows = _section_rows(path, "VEHICLES_INFO", 7)
    vehicle_count = int(path.stem.split("_")[1])
    if len(rows) != vehicle_count:
        raise ValueError(f"{path}: vehicle count mismatch")
    columns: dict[str, list[Any]] = {
        "vehicle_index": [],
        "vehicle_id": [],
        "source_vehicle_id": [],
        "start_node_index": [],
        "end_node_index": [],
        "shift_start_time_ms": [],
        "shift_end_time_ms": [],
        "max_route_duration_ms": [None] * vehicle_count,
        "seat_capacity": [],
        "initial_load": [0] * vehicle_count,
    }
    for expected_index, fields in enumerate(rows):
        vehicle_id, capacity, depart_time, end_time, depart_node, sink_node, _zone = (
            int(value) for value in fields
        )
        if vehicle_id != expected_index:
            raise ValueError(f"{path}: vehicle IDs are not contiguous")
        columns["vehicle_index"].append(vehicle_id)
        columns["vehicle_id"].append(f"vehicle-{vehicle_id}")
        columns["source_vehicle_id"].append(str(vehicle_id))
        columns["start_node_index"].append(depart_node)
        columns["end_node_index"].append(sink_node)
        columns["shift_start_time_ms"].append(
            (max(depart_time, simulation_start_seconds) - simulation_start_seconds) * 1000
        )
        columns["shift_end_time_ms"].append((end_time - simulation_start_seconds) * 1000)
        columns["seat_capacity"].append(capacity)
    fleet_slug = f"uniform-{vehicle_count}-capacity-{columns['seat_capacity'][0]}"
    artifact_id = f"{COLLECTION_ID}.fleet.{fleet_slug}"
    _write_component(
        output,
        artifacts,
        artifact_id=artifact_id,
        relative_path=f"tables/fleets/{fleet_slug}/vehicles.parquet",
        columns=columns,
        role="vehicles",
        source_sha256=sha256_file(path),
    )
    return {"slug": fleet_slug, "vehicles": artifact_id, "onboard_requests": None}


def _warm_fleet(
    output: Path,
    artifacts: dict[str, Any],
    vehicle_path: Path,
    onboard_path: Path,
    simulation_start_seconds: int,
) -> dict[str, Any]:
    vehicle_rows = _section_rows(vehicle_path, "VEHICLES_INFO", 11)
    onboard_rows = _section_rows(onboard_path, "REQUESTS_INFO", 10)
    vehicle_count = int(vehicle_path.stem.split("_")[1])
    if len(vehicle_rows) != vehicle_count:
        raise ValueError(f"{vehicle_path}: vehicle count mismatch")
    loads: defaultdict[int, int] = defaultdict(int)
    for fields in onboard_rows:
        loads[int(fields[6])] += int(fields[0])

    vehicle_columns: dict[str, list[Any]] = {
        "vehicle_index": [],
        "vehicle_id": [],
        "source_vehicle_id": [],
        "start_node_index": [],
        "end_node_index": [],
        "shift_start_time_ms": [],
        "shift_end_time_ms": [],
        "max_route_duration_ms": [None] * vehicle_count,
        "seat_capacity": [],
        "initial_load": [],
    }
    for expected_index, fields in enumerate(vehicle_rows):
        vehicle_id = int(fields[0])
        if vehicle_id != expected_index:
            raise ValueError(f"{vehicle_path}: vehicle IDs are not contiguous")
        capacity = int(fields[1])
        vehicle_columns["vehicle_index"].append(vehicle_id)
        vehicle_columns["vehicle_id"].append(f"vehicle-{vehicle_id}")
        vehicle_columns["source_vehicle_id"].append(str(vehicle_id))
        vehicle_columns["start_node_index"].append(int(fields[4]))
        vehicle_columns["end_node_index"].append(int(fields[5]))
        vehicle_columns["shift_start_time_ms"].append(
            int(round((float(fields[2]) - simulation_start_seconds) * 1000))
        )
        vehicle_columns["shift_end_time_ms"].append(
            int(round((float(fields[3]) - simulation_start_seconds) * 1000))
        )
        vehicle_columns["seat_capacity"].append(capacity)
        vehicle_columns["initial_load"].append(loads[vehicle_id])
        if loads[vehicle_id] > capacity:
            raise ValueError(f"{vehicle_path}: onboard load exceeds capacity")

    fleet_slug = f"warm-start-11-{vehicle_count}-capacity-{vehicle_columns['seat_capacity'][0]}"
    vehicle_id = f"{COLLECTION_ID}.fleet.{fleet_slug}"
    _write_component(
        output,
        artifacts,
        artifact_id=vehicle_id,
        relative_path=f"tables/fleets/{fleet_slug}/vehicles.parquet",
        columns=vehicle_columns,
        role="vehicles",
        source_sha256=sha256_file(vehicle_path),
    )

    onboard_count = len(onboard_rows)
    onboard_columns: dict[str, list[Any]] = {
        "onboard_request_index": list(range(onboard_count)),
        "onboard_request_id": [f"onboard-{index + 1:07d}" for index in range(onboard_count)],
        "source_request_id": [None] * onboard_count,
        "party_size": [],
        "pickup_node_index": [],
        "dropoff_node_index": [],
        "earliest_pickup_time_ms": [],
        "pickup_time_ms": [],
        "pickup_departure_time_ms": [],
        "assigned_vehicle_index": [],
        "dropoff_route_position": [],
        "max_ride_time_ms": [None] * onboard_count,
        "dropoff_service_time_ms": [SERVICE_TIME_MS] * onboard_count,
    }
    for fields in onboard_rows:
        onboard_columns["party_size"].append(int(fields[0]))
        onboard_columns["pickup_node_index"].append(int(fields[1]))
        onboard_columns["dropoff_node_index"].append(int(fields[2]))
        onboard_columns["earliest_pickup_time_ms"].append(
            int(round((float(fields[3]) - simulation_start_seconds) * 1000))
        )
        onboard_columns["pickup_time_ms"].append(
            int(round((float(fields[4]) - simulation_start_seconds) * 1000))
        )
        onboard_columns["pickup_departure_time_ms"].append(
            int(round((float(fields[5]) - simulation_start_seconds) * 1000))
        )
        onboard_columns["assigned_vehicle_index"].append(int(fields[6]))
        onboard_columns["dropoff_route_position"].append(int(fields[9]))
    onboard_id = f"{COLLECTION_ID}.fleet.{fleet_slug}.onboard-requests"
    _write_component(
        output,
        artifacts,
        artifact_id=onboard_id,
        relative_path=f"tables/fleets/{fleet_slug}/onboard-requests.parquet",
        columns=onboard_columns,
        role="onboard_requests",
        source_sha256=sha256_file(onboard_path),
    )
    return {"slug": fleet_slug, "vehicles": vehicle_id, "onboard_requests": onboard_id}


def convert(source: Path, output: Path, converter_version: str) -> dict[str, Any]:
    if (output / "collection.yaml").exists():
        raise FileExistsError(f"refusing to replace existing collection: {output}")
    artifacts: dict[str, Any] = {}
    network_components = _network(source, output, artifacts)

    benchmark_root = source / "3_Benchmark_instances"
    uniform_fleets = [
        _uniform_fleet(output, artifacts, path, 7 * 3600)
        for path in sorted(
            (benchmark_root / "vehicles_uniform").glob("vehicles_*.txt"),
            key=lambda item: int(item.stem.split("_")[1]),
        )
    ]
    warm_root = benchmark_root / "vehicles_warmStart_11"
    warm_fleets = [
        _warm_fleet(
            output,
            artifacts,
            vehicle_path,
            warm_root / f"ONBOARDS_{vehicle_path.name}",
            11 * 3600,
        )
        for vehicle_path in sorted(
            warm_root.glob("vehicles_*.txt"),
            key=lambda item: int(item.stem.split("_")[1]),
        )
    ]
    if len(uniform_fleets) != 41 or len(warm_fleets) != 21:
        raise ValueError(
            f"expected 41 uniform and 21 warm fleets, got {len(uniform_fleets)} and {len(warm_fleets)}"
        )

    demand_roots = sorted(
        path
        for family in sorted(benchmark_root.glob("Instances_*"))
        for path in family.iterdir()
        if path.is_dir()
    )
    demands = [_demand(source, output, artifacts, path) for path in demand_roots]
    if len(demands) != 96:
        raise ValueError(f"expected 96 demand windows, got {len(demands)}")

    instance_paths: list[str] = []
    for demand in demands:
        compatible_fleets = uniform_fleets if demand["start_hour"] == 7 else warm_fleets
        for fleet in compatible_fleets:
            components = {
                "requests": demand["requests"],
                "reveal_times": demand["reveal_times"],
                "vehicles": fleet["vehicles"],
                **network_components,
            }
            if fleet["onboard_requests"] is not None:
                components["onboard_requests"] = fleet["onboard_requests"]
            instance_id = f"{COLLECTION_ID}.{demand['slug']}.reveal-original.{fleet['slug']}"
            relative_manifest = f"instances/{instance_id}.yaml"
            instance = {
                "format_version": FORMAT_VERSION,
                "instance_id": instance_id,
                "physical_problem_id": f"{COLLECTION_ID}.{demand['slug']}.{fleet['slug']}",
                "physical_problem_sha256": physical_problem_sha256(
                    components,
                    artifacts,
                    service_horizon_ms=demand["service_horizon_ms"],
                    relocation_allowed=True,
                ),
                "problem_family": "darp",
                "tier": "large_real_world",
                "collection_id": COLLECTION_ID,
                "components": components,
                "time": {
                    "semantics": "relative_elapsed",
                    "unit": "millisecond",
                    "service_horizon_ms": demand["service_horizon_ms"],
                    "source_time_origin": demand["source_time_origin"],
                    "source_time_zone": "America/New_York",
                },
                "spatial": {
                    "profile": "geographic",
                    "coordinate_unit": None,
                    "crs": "OGC:CRS84",
                },
                "relocation": {
                    "allowed": True,
                    "destinations": "nodes.relocation_allowed",
                },
                "extensions": [],
                "provenance": {
                    "source_default_vehicle_count": demand["source_default_vehicle_count"],
                    "fleet_scenario": fleet["slug"],
                    "source_time_unit": "second",
                    "source_service_time_seconds": 30,
                    "source_request_count": demand["source_request_count"],
                    "normalized_request_count": (
                        demand["source_request_count"]
                        - demand["excluded_nonpositive_party_size"]
                    ),
                    "excluded_nonpositive_party_size": demand[
                        "excluded_nonpositive_party_size"
                    ],
                    "request_upper_bounds": "not specified in source data",
                    "max_ride_time": "experiment-specific in dynamic-ips; not imposed by this instance",
                },
            }
            dump_yaml(output / relative_manifest, instance)
            instance_paths.append(relative_manifest)

    license_root = output / "LICENSES"
    license_root.mkdir(parents=True, exist_ok=True)
    (license_root / "upstream-notices.md").write_text(UPSTREAM_NOTICES, encoding="utf-8")
    (output / "citations.bib").write_text(CITATIONS_BIB, encoding="utf-8")

    used_sources = [
        source / "1_Network" / "virtual_stops_latlon.geojson",
        source / "1_Network" / "edge_time_matrix.txt",
        *(demand["trip_path"] for demand in demands),
        *(demand["metadata_path"] for demand in demands),
        *(benchmark_root / "vehicles_uniform").glob("*.txt"),
        *warm_root.glob("*.txt"),
    ]
    source_checksums = sorted(
        (sha256_file(path), path.relative_to(source).as_posix()) for path in used_sources
    )
    provenance_root = output / "provenance"
    provenance_root.mkdir(parents=True, exist_ok=True)
    (provenance_root / "source-checksums.sha256").write_text(
        "".join(f"{digest}  {path}\n" for digest, path in source_checksums), encoding="utf-8"
    )
    transformation = {
        "transformation_id": "online-darp-benchmark-nyc-normalizer",
        "code_url": "https://github.com/mobility-solutions-inc/online-darp-benchmark",
        "code_version": converter_version,
        "parameters": {
            "time_origin": "per-demand service start in America/New_York",
            "normalized_time_unit": "millisecond",
            "service_time_seconds": 30,
            "nonpositive_party_size_policy": "exclude and report",
            "relocation_allowed_at_all_virtual_stops": True,
            "fleet_composition": "all compatible public deployment configurations",
        },
        "random_seed": None,
        "deterministic": True,
    }
    dump_yaml(provenance_root / "transformations.yaml", [transformation])

    collection = {
        "format_version": FORMAT_VERSION,
        "collection_id": COLLECTION_ID,
        "collection_version": "1.0.0-draft.1",
        "source": {
            "source_id": "nyc-darp",
            "source_release": SOURCE_RELEASE,
            "zenodo_record": SOURCE_RECORD,
            "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
            "dynamic_ips_commit": DYNAMIC_IPS_COMMIT,
            "canonical_url": "https://doi.org/10.5281/zenodo.20452171",
            "repository_url": "https://github.com/lab-core/dynamic-ips",
            "citations": [
                "https://doi.org/10.5281/zenodo.20452171",
                "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
                "https://www.openstreetmap.org/copyright",
                "https://github.com/Project-OSRM/osrm-backend",
            ],
        },
        "license": {
            "spdx_or_name": "CC-BY-4.0",
            "notice_paths": ["LICENSES/upstream-notices.md"],
            "redistribution": "confirmed",
        },
        "scope": {
            "demand_windows": len(demands),
            "uniform_fleets": len(uniform_fleets),
            "warm_start_fleets": len(warm_fleets),
            "logical_instances": len(instance_paths),
            "excluded_nonpositive_party_size_records": sum(
                demand["excluded_nonpositive_party_size"] for demand in demands
            ),
            "composition": "7:00 demand uses every uniform fleet; 11:00 demand uses every warm-start fleet",
            "raw_trip_generation_data": "retained in upstream archive, not normalized as benchmark input",
        },
        "artifacts": artifacts,
        "transformations": [transformation],
        "instances": instance_paths,
    }
    dump_yaml(output / "collection.yaml", collection)
    return {
        "collection_id": COLLECTION_ID,
        "demand_windows": len(demands),
        "fleet_deployments": len(uniform_fleets) + len(warm_fleets),
        "instances": len(instance_paths),
        "artifacts": len(artifacts),
        "source_files": len(source_checksums),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        type=Path,
        help="NYC_Dataset_2015-2016 root with pinned warm-start files added",
    )
    parser.add_argument("output", type=Path, help="new normalized collection directory")
    parser.add_argument(
        "--converter-version",
        default="unreleased",
        help="immutable converter commit or release identifier",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = convert(args.source, args.output, args.converter_version)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
