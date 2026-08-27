"""Convert the Eccel v1.2 DDARP instances into RFC-0001 Parquet packages."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from .parquet_collection import (
    FORMAT_VERSION,
    SCHEMA_VERSION,
    artifact_record,
    dump_yaml,
    physical_problem_sha256,
    sha256_file,
    write_parquet,
)


SOURCE_COMMIT = "77c301eab45f735734f114fdfefd4da02f19c8b1"
SOURCE_RELEASE = "v1.2"
COLLECTION_ID = "eccel-ddarp-v1.2"
TIME_SCALE_MS = 60_000

FAMILIES = {
    "cordeau_laporte_2003": "cordeau-laporte-2003",
    "ropke_etal_2007": "ropke-et-al-2007",
}

CITATIONS_BIB = """@dataset{eccel2020instances,
  author = {Eccel, Renan Artur Lopes},
  title = {instances-DDARP-DPDPTW},
  year = {2020},
  version = {1.2},
  doi = {10.5281/zenodo.4107192}
}

@article{eccel2021dynamic,
  author = {Eccel, Renan Artur Lopes and Carlson, Rodrigo Castelan},
  title = {Análise de problemas dinâmicos de coleta e entrega e dial-a-ride},
  journal = {Transportes},
  volume = {28},
  number = {4},
  pages = {103--116},
  year = {2021},
  doi = {10.14295/transportes.v28i4.2412}
}

@article{berbeglia2012hybrid,
  author = {Berbeglia, Gerardo and Cordeau, Jean-François and Laporte, Gilbert},
  title = {A Hybrid Tabu Search and Constraint Programming Algorithm for the Dynamic Dial-a-Ride Problem},
  journal = {INFORMS Journal on Computing},
  volume = {24},
  number = {3},
  pages = {343--355},
  year = {2012},
  doi = {10.1287/ijoc.1110.0454}
}
"""


def _time_ms(value: int | float) -> int:
    return int(round(float(value) * TIME_SCALE_MS))


def _source_pair_root(source: Path, family: str) -> Path:
    return source / "instances" / "benchmark" / "ddarp" / "berbeglia_2012" / family


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_pair(static: dict[str, Any], dynamic: dict[str, Any], label: str) -> None:
    static_requests = static["requests"]
    dynamic_requests = dynamic["requests"]
    if len(static_requests) != len(dynamic_requests):
        raise ValueError(f"{label}: static/dynamic request counts differ")
    for static_request, dynamic_request in zip(static_requests, dynamic_requests, strict=True):
        stripped = {key: value for key, value in dynamic_request.items() if key != "arrival_time"}
        if static_request != stripped:
            raise ValueError(f"{label}: physical request data differ between static and dynamic")
        if "arrival_time" not in dynamic_request:
            raise ValueError(f"{label}: dynamic request lacks arrival_time")
    fields = (
        "number_of_vehicles",
        "vehicle_capacity",
        "max_ride_time",
        "max_route_time",
        "planing_horizon",
        "depot_location",
        "travel_time_between_nodes",
    )
    for field in fields:
        if static["static_info"].get(field) != dynamic["static_info"].get(field):
            raise ValueError(f"{label}: static_info.{field} differs")


def _normalize(
    static: dict[str, Any], dynamic: dict[str, Any]
) -> tuple[list[dict[str, Any]], ...]:
    info = static["static_info"]
    requests: list[dict[str, Any]] = []
    reveals: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = [
        {
            "node_index": 0,
            "node_id": "depot",
            "source_node_id": "depot",
            "relocation_allowed": True,
            "x": float(info["depot_location"]["x_coord"]),
            "y": float(info["depot_location"]["y_coord"]),
        }
    ]
    for request_index, (source_request, dynamic_request) in enumerate(
        zip(static["requests"], dynamic["requests"], strict=True)
    ):
        source_id = str(source_request["id"])
        pickup_index = len(nodes)
        nodes.append(
            {
                "node_index": pickup_index,
                "node_id": f"request-{source_id}-pickup",
                "source_node_id": f"{source_id}:pickup",
                "relocation_allowed": True,
                "x": float(source_request["pickup_location"]["x_coord"]),
                "y": float(source_request["pickup_location"]["y_coord"]),
            }
        )
        dropoff_index = len(nodes)
        nodes.append(
            {
                "node_index": dropoff_index,
                "node_id": f"request-{source_id}-dropoff",
                "source_node_id": f"{source_id}:delivery",
                "relocation_allowed": True,
                "x": float(source_request["delivery_location"]["x_coord"]),
                "y": float(source_request["delivery_location"]["y_coord"]),
            }
        )
        requests.append(
            {
                "request_index": request_index,
                "request_id": f"request-{source_id}",
                "source_request_id": source_id,
                "party_size": int(source_request["load"]),
                "pickup_node_index": pickup_index,
                "dropoff_node_index": dropoff_index,
                "earliest_pickup_time_ms": _time_ms(source_request["pickup_lower_tw"]),
                "latest_pickup_time_ms": _time_ms(source_request["pickup_upper_tw"]),
                "earliest_dropoff_time_ms": _time_ms(source_request["delivery_lower_tw"]),
                "latest_dropoff_time_ms": _time_ms(source_request["delivery_upper_tw"]),
                "max_ride_time_ms": _time_ms(info["max_ride_time"]),
                "pickup_service_time_ms": _time_ms(source_request["pickup_service_time"]),
                "dropoff_service_time_ms": _time_ms(source_request["delivery_service_time"]),
            }
        )
        reveals.append(
            {
                "request_index": request_index,
                "base_reveal_time_ms": _time_ms(dynamic_request["arrival_time"]),
            }
        )

    horizon_ms = _time_ms(info["planing_horizon"])
    vehicles = [
        {
            "vehicle_index": vehicle_index,
            "vehicle_id": f"vehicle-{vehicle_index + 1}",
            "source_vehicle_id": str(vehicle_index + 1),
            "start_node_index": 0,
            "end_node_index": 0,
            "shift_start_time_ms": 0,
            "shift_end_time_ms": horizon_ms,
            "max_route_duration_ms": _time_ms(info["max_route_time"]),
            "seat_capacity": int(info["vehicle_capacity"]),
            "initial_load": 0,
        }
        for vehicle_index in range(int(info["number_of_vehicles"]))
    ]

    travel_times: list[dict[str, Any]] = []
    for origin in nodes:
        for destination in nodes:
            source_time = math.ceil(
                math.hypot(origin["x"] - destination["x"], origin["y"] - destination["y"])
            )
            travel_times.append(
                {
                    "from_node_index": origin["node_index"],
                    "to_node_index": destination["node_index"],
                    "travel_time_ms": _time_ms(source_time),
                    "distance_mm": None,
                }
            )
    return requests, reveals, vehicles, nodes, travel_times


def _write_component(
    root: Path,
    artifacts: dict[str, Any],
    *,
    artifact_id: str,
    relative_path: str,
    rows: list[dict[str, Any]],
    role: str,
    source_sha256: str | list[str],
    spatial_profile: str | None = None,
) -> None:
    file_record = write_parquet(
        root / relative_path,
        rows,
        schema_name=role,
        collection_id=COLLECTION_ID,
        artifact_id=artifact_id,
        spatial_profile=spatial_profile,
    )
    artifacts[artifact_id] = artifact_record(
        role=role,
        file_record=file_record,
        collection_root=root,
        source_sha256=source_sha256,
        spatial_profile=spatial_profile,
    )


def convert(source: Path, output: Path, converter_version: str) -> dict[str, Any]:
    """Convert all 68 DDARP physical instances and paired reveal schedules."""

    if (output / "collection.yaml").exists():
        raise FileExistsError(f"refusing to replace existing collection: {output}")
    artifacts: dict[str, Any] = {}
    instance_paths: list[str] = []
    source_checksums: list[tuple[str, str]] = []

    for source_family, normalized_family in FAMILIES.items():
        family_root = _source_pair_root(source, source_family)
        static_root = family_root / "json_static_instances"
        dynamic_root = family_root / "json_dynamic_instances"
        static_paths = sorted(static_root.glob("*.json"))
        if not static_paths:
            raise FileNotFoundError(f"no Eccel instances found in {static_root}")
        for static_path in static_paths:
            dynamic_path = dynamic_root / static_path.name
            if not dynamic_path.is_file():
                raise FileNotFoundError(f"missing dynamic pair: {dynamic_path}")
            slug = f"{normalized_family}.{static_path.stem.lower()}"
            static = _load(static_path)
            dynamic = _load(dynamic_path)
            _verify_pair(static, dynamic, slug)
            static_sha = sha256_file(static_path)
            dynamic_sha = sha256_file(dynamic_path)
            source_checksums.extend(
                [
                    (static_sha, static_path.relative_to(source).as_posix()),
                    (dynamic_sha, dynamic_path.relative_to(source).as_posix()),
                ]
            )
            requests, reveals, vehicles, nodes, travel_times = _normalize(static, dynamic)
            prefix = f"{COLLECTION_ID}.{slug}"
            component_ids = {
                "requests": f"{prefix}.requests",
                "reveal_times": f"{prefix}.reveal-original",
                "vehicles": f"{prefix}.fleet-original",
                "nodes": f"{prefix}.nodes",
                "travel_times": f"{prefix}.travel-times",
            }
            _write_component(
                output,
                artifacts,
                artifact_id=component_ids["requests"],
                relative_path=f"tables/demand/{slug}/requests.parquet",
                rows=requests,
                role="requests",
                source_sha256=static_sha,
            )
            _write_component(
                output,
                artifacts,
                artifact_id=component_ids["reveal_times"],
                relative_path=f"tables/demand/{slug}/reveals/original.parquet",
                rows=reveals,
                role="reveal_times",
                source_sha256=dynamic_sha,
            )
            _write_component(
                output,
                artifacts,
                artifact_id=component_ids["vehicles"],
                relative_path=f"tables/fleets/{slug}/vehicles.parquet",
                rows=vehicles,
                role="vehicles",
                source_sha256=static_sha,
            )
            _write_component(
                output,
                artifacts,
                artifact_id=component_ids["nodes"],
                relative_path=f"tables/networks/{slug}/nodes.parquet",
                rows=nodes,
                role="nodes",
                source_sha256=static_sha,
                spatial_profile="abstract_cartesian",
            )
            _write_component(
                output,
                artifacts,
                artifact_id=component_ids["travel_times"],
                relative_path=f"tables/networks/{slug}/travel-times.parquet",
                rows=travel_times,
                role="travel_times",
                source_sha256=static_sha,
            )

            horizon_ms = _time_ms(static["static_info"]["planing_horizon"])
            instance_id = f"{prefix}.reveal-original.fleet-original"
            relative_manifest = f"instances/{instance_id}.yaml"
            instance = {
                "format_version": FORMAT_VERSION,
                "instance_id": instance_id,
                "physical_problem_id": f"{prefix}.fleet-original",
                "physical_problem_sha256": physical_problem_sha256(
                    component_ids,
                    artifacts,
                    service_horizon_ms=horizon_ms,
                    relocation_allowed=True,
                ),
                "problem_family": "darp",
                "tier": "exact_classical",
                "collection_id": COLLECTION_ID,
                "components": component_ids,
                "time": {
                    "semantics": "relative_elapsed",
                    "unit": "millisecond",
                    "service_horizon_ms": horizon_ms,
                    "source_time_origin": None,
                },
                "spatial": {
                    "profile": "abstract_cartesian",
                    "coordinate_unit": "source_euclidean_unit",
                },
                "relocation": {
                    "allowed": True,
                    "destinations": "nodes.relocation_allowed",
                },
                "extensions": [],
                "provenance": {
                    "static_source_path": static_path.relative_to(source).as_posix(),
                    "dynamic_source_path": dynamic_path.relative_to(source).as_posix(),
                    "source_time_unit": "minute",
                    "travel_time_rule": "ceil(euclidean_distance) source minutes",
                },
            }
            dump_yaml(output / relative_manifest, instance)
            instance_paths.append(relative_manifest)

    license_source = source / "LICENSE"
    if license_source.is_file():
        license_target = output / "LICENSES" / "eccel-source-MIT.txt"
        license_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_source, license_target)
    (output / "citations.bib").write_text(CITATIONS_BIB, encoding="utf-8")
    checksum_text = "".join(f"{digest}  {path}\n" for digest, path in source_checksums)
    provenance_root = output / "provenance"
    provenance_root.mkdir(parents=True, exist_ok=True)
    (provenance_root / "source-checksums.sha256").write_text(checksum_text, encoding="utf-8")
    transformation = {
        "transformation_id": "online-darp-benchmark-eccel-normalizer",
        "code_url": "https://github.com/mobility-solutions-inc/online-darp-benchmark",
        "code_version": converter_version,
        "parameters": {
            "source_time_unit": "minute",
            "normalized_time_unit": "millisecond",
            "travel_time_rule": "ceil Euclidean distance",
            "relocation_allowed_at_all_nodes": True,
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
            "source_id": "eccel-ddarp-dpdptw",
            "source_release": SOURCE_RELEASE,
            "source_commit": SOURCE_COMMIT,
            "canonical_url": "https://doi.org/10.5281/zenodo.4107192",
            "repository_url": "https://github.com/renan-eccel/instances-DDARP-DPDPTW",
            "citations": [
                "https://doi.org/10.5281/zenodo.4107192",
                "https://doi.org/10.14295/transportes.v28i4.2412",
                "https://doi.org/10.1287/ijoc.1110.0454",
            ],
        },
        "license": {
            "spdx_or_name": "MIT",
            "notice_paths": ["LICENSES/eccel-source-MIT.txt"],
            "redistribution": "confirmed",
        },
        "scope": {
            "included": "all DDARP instances and paired reveal schedules in Eccel v1.2",
            "excluded": "DPDPTW adjacent-task instances require a fleet/capacity extension",
        },
        "artifacts": artifacts,
        "transformations": [transformation],
        "instances": instance_paths,
    }
    dump_yaml(output / "collection.yaml", collection)
    return {
        "collection_id": COLLECTION_ID,
        "instances": len(instance_paths),
        "artifacts": len(artifacts),
        "source_files": len(source_checksums),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="checkout of instances-DDARP-DPDPTW v1.2")
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
