"""Convert the Ontra Manhattan TLC Rust-regression data into RFC-0001 Parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

from .parquet_collection import (
    FORMAT_VERSION,
    SCHEMA_VERSION,
    SORT_KEYS,
    artifact_record,
    dump_yaml,
    physical_problem_sha256,
    sha256_file,
    write_parquet,
)


COLLECTION_ID = "ontra-manhattan-tlc-2025-01-22-v1"
SOURCE_RELEASE = "v1.0.0"
ONTRA_GENERATOR_COMMIT = "6d4f168a0724a0f0bc7795b57f75fac8cf3010dd"
GENERATION_SEED = 20250122
SOURCE_TIME_ORIGIN = "2025-01-22T08:00:00-05:00"
SOURCE_EPOCH_SECONDS = 1_737_550_800
SERVICE_TIME_MS = 30_000
AVERAGE_SPEED_KMH = 30.0
HAVERSINE_BUFFER = 1.2
EARTH_RADIUS_KM = 6371.0
BALANCED_SHIFT_END_MS = 14_400_000

REQUESTS_FILENAME = "requests_manhattan_tlc_8am_pool25.json"
HISTORICAL_FLEET_FILENAME = "vehicles_manhattan_tlc_8am_2000_pool25.json"
POINT_POOL_FILENAME = "manhattan_tlc_graphhopper_point_pool_25.json"

PINNED_SOURCE_SHA256 = {
    REQUESTS_FILENAME: "e68e20594faaa9b863f905dcefa9d7fa5f5c747d1df8b3abdef705cd255bff98",
    HISTORICAL_FLEET_FILENAME: "64ac9adab27e36f2ce7152ea4dd70e5a59feed4a56c998e3fc3a7015dc3bb3fe",
    POINT_POOL_FILENAME: "87b2522fcd07386502cdbace190c9574a2fd99ec179773021ede9cbe0b3d9504",
}

UPSTREAM_TLC_SHA256 = {
    "fhv_tripdata_2025-01.parquet": "47e18b38cb541f565e88ea43d9595fc5a0f47cafbc126e04dd820ce1f3fd0f29",
    "fhvhv_tripdata_2025-01.parquet": "fcdef276f4e9887f2beab30590165cdea74caef50a1313d71fa01ff6afacca3a",
    "green_tripdata_2025-01.parquet": "84f3a121667157efcbf012c3566a6065df6f8e0312c678cb2f29cd72cc9c0f10",
    "nyc_taxi_zones.csv": "af93caa88250e5cf15988cd9f461404e19ad1ff87774e83b05ef31e6fe207cb4",
    "yellow_tripdata_2025-01.parquet": "9af277e4c0d3f9deb30644da822981e1e7df6af58313170fd3aa8a474485488a",
}

CITATIONS_BIB = """@misc{nyctlc2025triprecords,
  author = {{New York City Taxi and Limousine Commission}},
  title = {TLC Trip Record Data: January 2025},
  year = {2025},
  url = {https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page},
  note = {Accessed 2026-08-05}
}

@software{ontra2026manhattangenerator,
  author = {{Mobility Solutions Inc}},
  title = {Ontra Manhattan TLC simulation generator},
  year = {2026},
  url = {https://github.com/mobility-solutions-inc/ontra},
  note = {Commit 6d4f168a0724a0f0bc7795b57f75fac8cf3010dd}
}
"""

UPSTREAM_NOTICES = """# Ontra Manhattan TLC public-instance notices

This collection is a Mobility Solutions Inc transformation of New York City
Taxi and Limousine Commission public trip records and taxi-zone geometry.

- TLC source and data dictionaries:
  https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- NYC Open Data terms and disclaimers:
  https://cityofnewyork.github.io/opendatatsm/publicpolicies.html
- Generator source:
  https://github.com/mobility-solutions-inc/ontra/tree/6d4f168a0724a0f0bc7795b57f75fac8cf3010dd/dispatching/scripts

NYC Open Data requires source/version/modification identification when data are
republished. The City and TLC make no warranty about completeness, accuracy, or
fitness for a particular purpose. TLC states that provider-submitted trip records
may be incomplete or inaccurate.

The benchmark rows are not observed door-to-door passenger trajectories. The
source exposes pickup/drop-off taxi zones and times. Ontra sampled synthetic
points inside those zones, remapped them to a frozen routable point pool, created
synthetic fleets, and applies a deterministic great-circle travel model.

The normalized collection is released under CC BY 4.0. Attribution must identify
the NYC TLC source and Mobility Solutions Inc modifications. No City endorsement
is implied.
"""


def _point_key(value: dict[str, Any]) -> tuple[int, int]:
    return int(value["lat"]), int(value["lon"])


def _point_wkb(latitude_microdegrees: int, longitude_microdegrees: int) -> bytes:
    return struct.pack(
        "<BIdd",
        1,
        1,
        longitude_microdegrees / 1_000_000,
        latitude_microdegrees / 1_000_000,
    )


def _stable_index(identity: str, size: int) -> int:
    digest = hashlib.sha256(f"{GENERATION_SEED}:{identity}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % size


def _load_source(source: Path, enforce_pins: bool) -> tuple[list[Any], list[Any], Any]:
    paths = {
        REQUESTS_FILENAME: source / REQUESTS_FILENAME,
        HISTORICAL_FLEET_FILENAME: source / HISTORICAL_FLEET_FILENAME,
        POINT_POOL_FILENAME: source / POINT_POOL_FILENAME,
    }
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing source artifact: {path}")
        if enforce_pins and sha256_file(path) != PINNED_SOURCE_SHA256[name]:
            raise ValueError(f"source checksum does not match {SOURCE_RELEASE}: {name}")
    requests = json.loads(paths[REQUESTS_FILENAME].read_text(encoding="utf-8"))
    vehicles = json.loads(paths[HISTORICAL_FLEET_FILENAME].read_text(encoding="utf-8"))
    pool = json.loads(paths[POINT_POOL_FILENAME].read_text(encoding="utf-8"))
    return requests, vehicles, pool


def _used_nodes(
    requests: list[dict[str, Any]],
    historical_vehicles: list[dict[str, Any]],
    pool: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[tuple[int, int], int], dict[int, list[int]]]:
    source_by_point = {
        (int(point["lat"]), int(point["lon"])): (
            int(point["zone_id"]),
            int(point["pool_index"]),
        )
        for point in pool["points"]
    }
    pickup_zones = {int(request["pickup_zone_id"]) for request in requests}
    used_points = {
        _point_key(request[role])
        for request in requests
        for role in ("origin", "destination")
    } | {_point_key(vehicle["location"]) for vehicle in historical_vehicles}
    # Include the complete frozen point pool for every represented pickup zone.
    # Balanced fleet locations therefore do not depend on which points happened
    # to be selected by requests in this particular hour.
    used_points |= {
        (int(point["lat"]), int(point["lon"]))
        for point in pool["points"]
        if int(point["zone_id"]) in pickup_zones
    }
    missing = sorted(used_points - source_by_point.keys())
    if missing:
        raise ValueError(f"{len(missing)} used points are absent from the frozen point pool")
    ordered = sorted(used_points, key=lambda point: (*source_by_point[point], *point))
    point_to_index = {point: index for index, point in enumerate(ordered)}
    nodes: list[dict[str, Any]] = []
    pickup_nodes_by_zone: dict[int, set[int]] = {zone: set() for zone in pickup_zones}
    for index, point in enumerate(ordered):
        zone_id, pool_index = source_by_point[point]
        nodes.append(
            {
                "node_index": index,
                "node_id": f"tlc-zone-{zone_id:03d}-pool-{pool_index:02d}",
                "source_node_id": f"tlc-zone-{zone_id}:pool-{pool_index}",
                "relocation_allowed": True,
                "geometry": _point_wkb(*point),
            }
        )
        if zone_id in pickup_nodes_by_zone:
            pickup_nodes_by_zone[zone_id].add(index)
    return (
        nodes,
        point_to_index,
        {zone: sorted(indices) for zone, indices in pickup_nodes_by_zone.items()},
    )


def _write_component(
    root: Path,
    artifacts: dict[str, Any],
    *,
    artifact_id: str,
    relative_path: str,
    rows: Any,
    role: str,
    source_sha256: str | list[str],
    spatial_profile: str | None = None,
    crs: Any = None,
) -> None:
    file_record = write_parquet(
        root / relative_path,
        rows,
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


def _write_travel_matrix(
    output: Path,
    artifacts: dict[str, Any],
    nodes: list[dict[str, Any]],
    pool_sha256: str,
    shard_origins: int,
) -> str:
    artifact_id = f"{COLLECTION_ID}.pool25-haversine.nodes.travel-times"
    latitudes = [struct.unpack("<BIdd", node["geometry"])[3] for node in nodes]
    longitudes = [struct.unpack("<BIdd", node["geometry"])[2] for node in nodes]
    lat_radians = [math.radians(value) for value in latitudes]
    file_records: list[dict[str, Any]] = []
    node_count = len(nodes)
    for start in range(0, node_count, shard_origins):
        end = min(start + shard_origins, node_count)
        columns: dict[str, list[Any]] = {
            "from_node_index": [],
            "to_node_index": [],
            "travel_time_ms": [],
            "distance_mm": [],
        }
        for origin in range(start, end):
            lat1 = lat_radians[origin]
            lon1 = math.radians(longitudes[origin])
            for destination in range(node_count):
                columns["from_node_index"].append(origin)
                columns["to_node_index"].append(destination)
                if origin == destination:
                    distance_km = 0.0
                else:
                    delta_lat = lat_radians[destination] - lat1
                    delta_lon = math.radians(longitudes[destination]) - lon1
                    value = (
                        math.sin(delta_lat / 2.0) ** 2
                        + math.cos(lat1)
                        * math.cos(lat_radians[destination])
                        * math.sin(delta_lon / 2.0) ** 2
                    )
                    central_angle = 2.0 * math.atan2(
                        math.sqrt(value), math.sqrt(max(0.0, 1.0 - value))
                    )
                    distance_km = EARTH_RADIUS_KM * central_angle
                travel_seconds = math.ceil(
                    distance_km / AVERAGE_SPEED_KMH * 3600.0 * HAVERSINE_BUFFER
                )
                columns["travel_time_ms"].append(travel_seconds * 1000)
                columns["distance_mm"].append(round(distance_km * 1_000_000))
        relative_path = (
            "tables/networks/pool25-haversine/travel-times/"
            f"part-{start:05d}-{end - 1:05d}.parquet"
        )
        record = write_parquet(
            output / relative_path,
            columns,
            schema_name="travel_times",
            collection_id=COLLECTION_ID,
            artifact_id=artifact_id,
        )
        record["path"] = relative_path
        file_records.append(record)
    artifacts[artifact_id] = {
        "role": "travel_times",
        "schema_name": "travel_times",
        "schema_version": SCHEMA_VERSION,
        "sort_keys": SORT_KEYS["travel_times"],
        "files": file_records,
        "source_sha256": pool_sha256,
        "travel_model": {
            "name": "ontra-rust-haversine-fallback",
            "earth_radius_km": EARTH_RADIUS_KM,
            "average_speed_kmh": AVERAGE_SPEED_KMH,
            "buffer_multiplier": HAVERSINE_BUFFER,
            "rounding": "ceil whole seconds; distance rounded to millimeters",
        },
    }
    return artifact_id


def _requests(
    source_requests: list[dict[str, Any]],
    point_to_index: dict[tuple[int, int], int],
) -> tuple[dict[str, list[Any]], dict[str, list[Any]]]:
    request_columns: dict[str, list[Any]] = {
        "request_index": [],
        "request_id": [],
        "source_request_id": [],
        "party_size": [],
        "pickup_node_index": [],
        "dropoff_node_index": [],
        "earliest_pickup_time_ms": [],
        "latest_pickup_time_ms": [],
        "earliest_dropoff_time_ms": [],
        "latest_dropoff_time_ms": [],
        "max_ride_time_ms": [],
        "pickup_service_time_ms": [],
        "dropoff_service_time_ms": [],
    }
    reveal_columns = {"request_index": [], "base_reveal_time_ms": []}
    previous_time = -1
    for index, request in enumerate(source_requests):
        request_time_ms = (int(request["request_time"]) - SOURCE_EPOCH_SECONDS) * 1000
        if int(request["pickup_lb"]) != int(request["request_time"]):
            raise ValueError(f"request {index} has distinct request and pickup times")
        if request_time_ms < previous_time:
            raise ValueError("source requests are not sorted by request time")
        previous_time = request_time_ms
        request_columns["request_index"].append(index)
        request_columns["request_id"].append(str(request["request_id"]))
        request_columns["source_request_id"].append(str(request["request_id"]))
        request_columns["party_size"].append(int(request["passenger_count"]))
        request_columns["pickup_node_index"].append(
            point_to_index[_point_key(request["origin"])]
        )
        request_columns["dropoff_node_index"].append(
            point_to_index[_point_key(request["destination"])]
        )
        request_columns["earliest_pickup_time_ms"].append(request_time_ms)
        request_columns["latest_pickup_time_ms"].append(None)
        request_columns["earliest_dropoff_time_ms"].append(None)
        request_columns["latest_dropoff_time_ms"].append(None)
        request_columns["max_ride_time_ms"].append(None)
        request_columns["pickup_service_time_ms"].append(SERVICE_TIME_MS)
        request_columns["dropoff_service_time_ms"].append(SERVICE_TIME_MS)
        reveal_columns["request_index"].append(index)
        reveal_columns["base_reveal_time_ms"].append(request_time_ms)
    return request_columns, reveal_columns


def _historical_fleet(
    source_vehicles: list[dict[str, Any]],
    point_to_index: dict[tuple[int, int], int],
) -> dict[str, list[Any]]:
    columns: dict[str, list[Any]] = {
        "vehicle_index": [],
        "vehicle_id": [],
        "source_vehicle_id": [],
        "start_node_index": [],
        "end_node_index": [],
        "shift_start_time_ms": [],
        "shift_end_time_ms": [],
        "max_route_duration_ms": [],
        "seat_capacity": [],
        "initial_load": [],
    }
    for index, vehicle in enumerate(source_vehicles):
        vehicle_id = str(vehicle["vehicle_workflow_id"])
        columns["vehicle_index"].append(index)
        columns["vehicle_id"].append(vehicle_id)
        columns["source_vehicle_id"].append(vehicle_id)
        columns["start_node_index"].append(point_to_index[_point_key(vehicle["location"])])
        columns["end_node_index"].append(None)
        columns["shift_start_time_ms"].append(
            (int(vehicle["start_time"]) - SOURCE_EPOCH_SECONDS) * 1000
        )
        columns["shift_end_time_ms"].append(
            (int(vehicle["route"]["shift_end_time"]) - SOURCE_EPOCH_SECONDS) * 1000
        )
        columns["max_route_duration_ms"].append(None)
        columns["seat_capacity"].append(int(vehicle["capacity"]))
        columns["initial_load"].append(0)
    return columns


def _balanced_fleet(
    vehicle_count: int,
    pickup_nodes_by_zone: dict[int, list[int]],
) -> dict[str, list[Any]]:
    if vehicle_count < 4 or vehicle_count % 4:
        raise ValueError("balanced fleet size must be a positive multiple of four")
    zones = sorted(pickup_nodes_by_zone)
    columns: dict[str, list[Any]] = {
        "vehicle_index": list(range(vehicle_count)),
        "vehicle_id": [],
        "source_vehicle_id": [None] * vehicle_count,
        "start_node_index": [],
        "end_node_index": [None] * vehicle_count,
        "shift_start_time_ms": [0] * vehicle_count,
        "shift_end_time_ms": [BALANCED_SHIFT_END_MS] * vehicle_count,
        "max_route_duration_ms": [None] * vehicle_count,
        "seat_capacity": [5] * (vehicle_count * 3 // 4)
        + [7] * (vehicle_count // 4),
        "initial_load": [0] * vehicle_count,
    }
    for index in range(vehicle_count):
        vehicle_id = f"balanced-{vehicle_count}-vehicle-{index + 1:04d}"
        zone = zones[index % len(zones)]
        candidates = pickup_nodes_by_zone[zone]
        selected = candidates[_stable_index(f"{vehicle_id}:zone:{zone}", len(candidates))]
        columns["vehicle_id"].append(vehicle_id)
        columns["start_node_index"].append(selected)
    return columns


def convert(
    source: Path,
    output: Path,
    converter_version: str,
    *,
    enforce_pins: bool = True,
    balanced_fleet_sizes: tuple[int, ...] = (1000, 2000, 4000),
    matrix_shard_origins: int = 128,
) -> dict[str, Any]:
    if (output / "collection.yaml").exists():
        raise FileExistsError(f"refusing to replace existing collection: {output}")
    if matrix_shard_origins < 1:
        raise ValueError("matrix_shard_origins must be at least one")
    source_requests, source_vehicles, pool = _load_source(source, enforce_pins)
    nodes, point_to_index, pickup_nodes_by_zone = _used_nodes(
        source_requests, source_vehicles, pool
    )
    artifacts: dict[str, Any] = {}
    pool_sha = sha256_file(source / POINT_POOL_FILENAME)
    requests_sha = sha256_file(source / REQUESTS_FILENAME)
    historical_fleet_sha = sha256_file(source / HISTORICAL_FLEET_FILENAME)

    nodes_id = f"{COLLECTION_ID}.pool25-haversine.nodes"
    _write_component(
        output,
        artifacts,
        artifact_id=nodes_id,
        relative_path="tables/networks/pool25-haversine/nodes.parquet",
        rows=nodes,
        role="nodes",
        source_sha256=pool_sha,
        spatial_profile="geographic",
        crs="OGC:CRS84",
    )
    travel_id = _write_travel_matrix(
        output, artifacts, nodes, pool_sha, matrix_shard_origins
    )

    request_columns, reveal_columns = _requests(source_requests, point_to_index)
    requests_id = f"{COLLECTION_ID}.20250122-0800-0900.requests"
    reveals_id = f"{COLLECTION_ID}.20250122-0800-0900.reveal-observed-pickup"
    _write_component(
        output,
        artifacts,
        artifact_id=requests_id,
        relative_path="tables/demand/20250122-0800-0900/requests.parquet",
        rows=request_columns,
        role="requests",
        source_sha256=requests_sha,
    )
    _write_component(
        output,
        artifacts,
        artifact_id=reveals_id,
        relative_path="tables/demand/20250122-0800-0900/reveals/observed-pickup.parquet",
        rows=reveal_columns,
        role="reveal_times",
        source_sha256=requests_sha,
    )

    fleets: list[dict[str, Any]] = []
    historical_columns = _historical_fleet(source_vehicles, point_to_index)
    historical_slug = "historical-rust-regression-2000"
    historical_id = f"{COLLECTION_ID}.fleet.{historical_slug}"
    _write_component(
        output,
        artifacts,
        artifact_id=historical_id,
        relative_path=f"tables/fleets/{historical_slug}/vehicles.parquet",
        rows=historical_columns,
        role="vehicles",
        source_sha256=historical_fleet_sha,
    )
    fleets.append(
        {
            "slug": historical_slug,
            "artifact_id": historical_id,
            "service_horizon_ms": max(historical_columns["shift_end_time_ms"]),
            "official_suite": False,
            "provenance": (
                "Exact surviving Rust-regression fleet. The original generator reused its "
                "vehicle filename, so a later 500-request pilot overwrote the fleet generated "
                "for the full hour. Its locations are demand-weighted from that pilot."
            ),
        }
    )
    for vehicle_count in balanced_fleet_sizes:
        slug = f"balanced-manhattan-{vehicle_count}"
        artifact_id = f"{COLLECTION_ID}.fleet.{slug}"
        _write_component(
            output,
            artifacts,
            artifact_id=artifact_id,
            relative_path=f"tables/fleets/{slug}/vehicles.parquet",
            rows=_balanced_fleet(vehicle_count, pickup_nodes_by_zone),
            role="vehicles",
            source_sha256=[requests_sha, pool_sha],
        )
        fleets.append(
            {
                "slug": slug,
                "artifact_id": artifact_id,
                "service_horizon_ms": BALANCED_SHIFT_END_MS,
                "official_suite": True,
                "provenance": (
                    "Demand-independent placement balanced across the 66 Manhattan pickup "
                    "zones represented in the source hour; 75% capacity five and 25% capacity seven."
                ),
            }
        )

    instance_paths: list[str] = []
    for fleet in fleets:
        components = {
            "requests": requests_id,
            "reveal_times": reveals_id,
            "vehicles": fleet["artifact_id"],
            "nodes": nodes_id,
            "travel_times": travel_id,
        }
        instance_id = f"{COLLECTION_ID}.full.{fleet['slug']}"
        relative_manifest = f"instances/{instance_id}.yaml"
        instance = {
            "format_version": FORMAT_VERSION,
            "instance_id": instance_id,
            "physical_problem_id": f"{COLLECTION_ID}.full.{fleet['slug']}",
            "physical_problem_sha256": physical_problem_sha256(
                components,
                artifacts,
                service_horizon_ms=fleet["service_horizon_ms"],
                relocation_allowed=True,
            ),
            "problem_family": "darp",
            "tier": "large_derived_real_demand",
            "collection_id": COLLECTION_ID,
            "suite_membership": "official" if fleet["official_suite"] else "supplemental",
            "components": components,
            "time": {
                "semantics": "relative_elapsed",
                "unit": "millisecond",
                "service_horizon_ms": fleet["service_horizon_ms"],
                "source_time_origin": SOURCE_TIME_ORIGIN,
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
                "request_count": len(source_requests),
                "source_service_date": "2025-01-22",
                "source_pickup_window": "08:00:00 inclusive to 09:00:00 exclusive",
                "source_pickup_borough": "Manhattan",
                "source_datasets": ["fhvhv", "yellow", "green", "fhv"],
                "source_counts": {"fhvhv": 17273, "yellow": 6781, "fhv": 174, "green": 97},
                "passenger_count_policy": (
                    "FHV/FHVHV use one; missing or nonpositive yellow/green values use one; "
                    "values above seven are capped at seven"
                ),
                "base_reveal_time": "observed pickup time",
                "earliest_pickup_time": "observed pickup time",
                "request_upper_bounds": "not imposed",
                "max_ride_time": "not imposed",
                "point_semantics": "synthetic frozen point sampled within each TLC taxi zone",
                "travel_model": (
                    "Rust Haversine fallback: Earth radius 6371 km, 30 km/h, 1.2 buffer, "
                    "ceil to whole seconds"
                ),
                "fleet": fleet["provenance"],
            },
        }
        dump_yaml(output / relative_manifest, instance)
        instance_paths.append(relative_manifest)

    license_root = output / "LICENSES"
    license_root.mkdir(parents=True, exist_ok=True)
    (license_root / "upstream-notices.md").write_text(UPSTREAM_NOTICES, encoding="utf-8")
    (output / "citations.bib").write_text(CITATIONS_BIB, encoding="utf-8")
    provenance_root = output / "provenance"
    provenance_root.mkdir(parents=True, exist_ok=True)
    source_checksums = {
        **{name: sha256_file(source / name) for name in PINNED_SOURCE_SHA256},
        **{f"upstream/{name}": digest for name, digest in UPSTREAM_TLC_SHA256.items()},
    }
    (provenance_root / "source-checksums.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(source_checksums.items())),
        encoding="utf-8",
    )
    transformation = {
        "transformation_id": "online-darp-benchmark-ontra-manhattan-normalizer",
        "code_url": "https://github.com/mobility-solutions-inc/online-darp-benchmark",
        "code_version": converter_version,
        "source_generator_url": "https://github.com/mobility-solutions-inc/ontra",
        "source_generator_commit": ONTRA_GENERATOR_COMMIT,
        "parameters": {
            "generation_seed": GENERATION_SEED,
            "service_time_ms": SERVICE_TIME_MS,
            "travel_model": {
                "earth_radius_km": EARTH_RADIUS_KM,
                "average_speed_kmh": AVERAGE_SPEED_KMH,
                "buffer_multiplier": HAVERSINE_BUFFER,
                "rounding": "ceil whole seconds",
            },
            "balanced_fleet_sizes": list(balanced_fleet_sizes),
            "balanced_fleet_capacity_mix": {"capacity_5": 0.75, "capacity_7": 0.25},
            "relocation_allowed_at_all_nodes": True,
        },
        "random_seed": GENERATION_SEED,
        "deterministic": True,
    }
    dump_yaml(provenance_root / "transformations.yaml", [transformation])
    collection = {
        "format_version": FORMAT_VERSION,
        "collection_id": COLLECTION_ID,
        "collection_version": "1.0.0-draft.1",
        "source": {
            "source_id": "ontra-manhattan-tlc",
            "source_release": SOURCE_RELEASE,
            "service_date": "2025-01-22",
            "canonical_url": "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
            "repository_url": "https://github.com/mobility-solutions-inc/ontra",
            "repository_commit": ONTRA_GENERATOR_COMMIT,
            "citations": [
                "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
                "https://cityofnewyork.github.io/opendatatsm/publicpolicies.html",
                "https://github.com/mobility-solutions-inc/ontra",
            ],
        },
        "license": {
            "spdx_or_name": "CC-BY-4.0",
            "notice_paths": ["LICENSES/upstream-notices.md"],
            "redistribution": "confirmed",
        },
        "scope": {
            "request_windows": 1,
            "request_count": len(source_requests),
            "fleet_deployments": len(fleets),
            "official_fleet_deployments": sum(fleet["official_suite"] for fleet in fleets),
            "supplemental_fleet_deployments": sum(
                not fleet["official_suite"] for fleet in fleets
            ),
            "logical_instances": len(instance_paths),
            "node_count": len(nodes),
            "travel_matrix_rows": len(nodes) ** 2,
        },
        "artifacts": artifacts,
        "transformations": [transformation],
        "instances": instance_paths,
    }
    dump_yaml(output / "collection.yaml", collection)
    return {
        "collection_id": COLLECTION_ID,
        "requests": len(source_requests),
        "nodes": len(nodes),
        "travel_matrix_rows": len(nodes) ** 2,
        "fleet_deployments": len(fleets),
        "instances": len(instance_paths),
        "artifacts": len(artifacts),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory containing the pinned source JSON")
    parser.add_argument("output", type=Path, help="new normalized collection directory")
    parser.add_argument(
        "--converter-version",
        default="unreleased",
        help="immutable converter commit or release identifier",
    )
    parser.add_argument(
        "--matrix-shard-origins",
        type=int,
        default=128,
        help="number of matrix origins in each Parquet shard",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = convert(
        args.source,
        args.output,
        args.converter_version,
        matrix_shard_origins=args.matrix_shard_origins,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
