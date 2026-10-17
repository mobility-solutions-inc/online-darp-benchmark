"""Reference Parquet writer and validator for RFC-0001 collections."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import sys
import tempfile
import unicodedata
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml
from jsonschema import Draft7Validator


FORMAT_VERSION = "1.0.0-draft.1"
SCHEMA_VERSION = "1.0.0-draft.1"

# GeoParquet 1.1 requires `crs` to be PROJJSON. Generated with
# pyproj.CRS("OGC:CRS84").to_json_dict() (pyproj 3.8.0, PROJ 9.8.1).
OGC_CRS84_PROJJSON: dict[str, Any] = {
    "$schema": "https://proj.org/schemas/v0.7/projjson.schema.json",
    "type": "GeographicCRS",
    "name": "WGS 84 (CRS84)",
    "datum_ensemble": {
        "name": "World Geodetic System 1984 ensemble",
        "members": [
            {
                "name": "World Geodetic System 1984 (Transit)",
                "id": {
                    "authority": "EPSG",
                    "code": 1166
                }
            },
            {
                "name": "World Geodetic System 1984 (G730)",
                "id": {
                    "authority": "EPSG",
                    "code": 1152
                }
            },
            {
                "name": "World Geodetic System 1984 (G873)",
                "id": {
                    "authority": "EPSG",
                    "code": 1153
                }
            },
            {
                "name": "World Geodetic System 1984 (G1150)",
                "id": {
                    "authority": "EPSG",
                    "code": 1154
                }
            },
            {
                "name": "World Geodetic System 1984 (G1674)",
                "id": {
                    "authority": "EPSG",
                    "code": 1155
                }
            },
            {
                "name": "World Geodetic System 1984 (G1762)",
                "id": {
                    "authority": "EPSG",
                    "code": 1156
                }
            },
            {
                "name": "World Geodetic System 1984 (G2139)",
                "id": {
                    "authority": "EPSG",
                    "code": 1309
                }
            },
            {
                "name": "World Geodetic System 1984 (G2296)",
                "id": {
                    "authority": "EPSG",
                    "code": 1383
                }
            }
        ],
        "ellipsoid": {
            "name": "WGS 84",
            "semi_major_axis": 6378137,
            "inverse_flattening": 298.257223563
        },
        "accuracy": "2.0",
        "id": {
            "authority": "EPSG",
            "code": 6326
        }
    },
    "coordinate_system": {
        "subtype": "ellipsoidal",
        "axis": [
            {
                "name": "Geodetic longitude",
                "abbreviation": "Lon",
                "direction": "east",
                "unit": "degree"
            },
            {
                "name": "Geodetic latitude",
                "abbreviation": "Lat",
                "direction": "north",
                "unit": "degree"
            }
        ]
    },
    "scope": "Not known.",
    "area": "World.",
    "bbox": {
        "south_latitude": -90,
        "west_longitude": -180,
        "north_latitude": 90,
        "east_longitude": 180
    },
    "id": {
        "authority": "OGC",
        "code": "CRS84"
    }
}
ROW_GROUP_SIZE = 1_048_576

REQUESTS_SCHEMA = pa.schema(
    [
        pa.field("request_index", pa.int32(), nullable=False),
        pa.field("request_id", pa.string(), nullable=False),
        pa.field("source_request_id", pa.string(), nullable=True),
        pa.field("party_size", pa.int32(), nullable=False),
        pa.field("pickup_node_index", pa.int32(), nullable=False),
        pa.field("dropoff_node_index", pa.int32(), nullable=False),
        pa.field("earliest_pickup_time_ms", pa.int64(), nullable=False),
        pa.field("latest_pickup_time_ms", pa.int64(), nullable=True),
        pa.field("earliest_dropoff_time_ms", pa.int64(), nullable=True),
        pa.field("latest_dropoff_time_ms", pa.int64(), nullable=True),
        pa.field("max_ride_time_ms", pa.int64(), nullable=True),
        pa.field("pickup_service_time_ms", pa.int64(), nullable=False),
        pa.field("dropoff_service_time_ms", pa.int64(), nullable=False),
    ]
)

REVEAL_TIMES_SCHEMA = pa.schema(
    [
        pa.field("request_index", pa.int32(), nullable=False),
        pa.field("base_reveal_time_ms", pa.int64(), nullable=False),
    ]
)

VEHICLES_SCHEMA = pa.schema(
    [
        pa.field("vehicle_index", pa.int32(), nullable=False),
        pa.field("vehicle_id", pa.string(), nullable=False),
        pa.field("source_vehicle_id", pa.string(), nullable=True),
        pa.field("start_node_index", pa.int32(), nullable=False),
        pa.field("end_node_index", pa.int32(), nullable=True),
        pa.field("shift_start_time_ms", pa.int64(), nullable=False),
        pa.field("shift_end_time_ms", pa.int64(), nullable=False),
        pa.field("max_route_duration_ms", pa.int64(), nullable=True),
        pa.field("seat_capacity", pa.int32(), nullable=False),
        pa.field("initial_load", pa.int32(), nullable=False),
    ]
)

ONBOARD_REQUESTS_SCHEMA = pa.schema(
    [
        pa.field("onboard_request_index", pa.int32(), nullable=False),
        pa.field("onboard_request_id", pa.string(), nullable=False),
        pa.field("source_request_id", pa.string(), nullable=True),
        pa.field("party_size", pa.int32(), nullable=False),
        pa.field("pickup_node_index", pa.int32(), nullable=False),
        pa.field("dropoff_node_index", pa.int32(), nullable=False),
        pa.field("earliest_pickup_time_ms", pa.int64(), nullable=False),
        pa.field("pickup_time_ms", pa.int64(), nullable=False),
        pa.field("pickup_departure_time_ms", pa.int64(), nullable=False),
        pa.field("assigned_vehicle_index", pa.int32(), nullable=False),
        pa.field("dropoff_route_position", pa.int32(), nullable=False),
        pa.field("max_ride_time_ms", pa.int64(), nullable=True),
        pa.field("dropoff_service_time_ms", pa.int64(), nullable=False),
    ]
)

NODE_CORE_FIELDS = [
    pa.field("node_index", pa.int32(), nullable=False),
    pa.field("node_id", pa.string(), nullable=False),
    pa.field("source_node_id", pa.string(), nullable=True),
    pa.field("relocation_allowed", pa.bool_(), nullable=False),
]
NODES_MATRIX_SCHEMA = pa.schema(NODE_CORE_FIELDS)
NODES_CARTESIAN_SCHEMA = pa.schema(
    NODE_CORE_FIELDS
    + [
        pa.field("x", pa.float64(), nullable=False),
        pa.field("y", pa.float64(), nullable=False),
    ]
)
NODES_GEOGRAPHIC_SCHEMA = pa.schema(
    NODE_CORE_FIELDS + [pa.field("geometry", pa.binary(), nullable=False)]
)

TRAVEL_TIMES_SCHEMA = pa.schema(
    [
        pa.field("from_node_index", pa.int32(), nullable=False),
        pa.field("to_node_index", pa.int32(), nullable=False),
        pa.field("travel_time_ms", pa.int64(), nullable=False),
        pa.field("distance_mm", pa.int64(), nullable=True),
    ]
)

SCHEMAS = {
    "requests": REQUESTS_SCHEMA,
    "reveal_times": REVEAL_TIMES_SCHEMA,
    "vehicles": VEHICLES_SCHEMA,
    "onboard_requests": ONBOARD_REQUESTS_SCHEMA,
    "nodes_matrix": NODES_MATRIX_SCHEMA,
    "nodes_cartesian": NODES_CARTESIAN_SCHEMA,
    "nodes_geographic": NODES_GEOGRAPHIC_SCHEMA,
    "travel_times": TRAVEL_TIMES_SCHEMA,
}

REQUIRED_INSTANCE_ROLES = frozenset(
    {"requests", "reveal_times", "vehicles", "nodes", "travel_times"}
)

SORT_KEYS = {
    "requests": ["request_index"],
    "reveal_times": ["request_index"],
    "vehicles": ["vehicle_index"],
    "onboard_requests": ["onboard_request_index"],
    "nodes": ["node_index"],
    "travel_times": ["from_node_index", "to_node_index"],
}


class CollectionValidationError(ValueError):
    """Raised when a normalized collection violates RFC-0001."""

    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__(yaml.safe_dump(report, sort_keys=False, width=float("inf")))
        self.report = report


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _schema_for(schema_name: str, spatial_profile: str | None) -> pa.Schema:
    if schema_name != "nodes":
        return SCHEMAS[schema_name]
    profile = spatial_profile or "matrix_only"
    profile_key = {
        "matrix_only": "matrix",
        "abstract_cartesian": "cartesian",
        "geographic": "geographic",
    }[profile]
    return SCHEMAS[f"nodes_{profile_key}"]


def _file_metadata(
    schema_name: str,
    collection_id: str,
    artifact_id: str,
    spatial_profile: str | None,
    crs: Mapping[str, Any] | None,
) -> dict[bytes, bytes]:
    metadata = {
        b"online_darp.format_version": FORMAT_VERSION.encode(),
        b"online_darp.schema_name": schema_name.encode(),
        b"online_darp.schema_version": SCHEMA_VERSION.encode(),
        b"online_darp.collection_id": collection_id.encode(),
        b"online_darp.artifact_id": artifact_id.encode(),
    }
    if schema_name == "nodes" and spatial_profile == "geographic":
        if not isinstance(crs, Mapping):
            raise TypeError("geographic nodes require a PROJJSON crs object")
        geo = {
            "version": "1.1.0",
            "primary_column": "geometry",
            "columns": {
                "geometry": {
                    "encoding": "WKB",
                    "geometry_types": ["Point"],
                    "crs": crs,
                }
            },
        }
        metadata[b"geo"] = json.dumps(geo, separators=(",", ":")).encode()
    return metadata


def write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Sequence[Any]] | pa.Table,
    *,
    schema_name: str,
    collection_id: str,
    artifact_id: str,
    spatial_profile: str | None = None,
    crs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one deterministic-profile Parquet artifact and return its file record."""

    schema = _schema_for(schema_name, spatial_profile).with_metadata(
        _file_metadata(schema_name, collection_id, artifact_id, spatial_profile, crs)
    )
    if isinstance(rows, pa.Table):
        table = rows.cast(schema.remove_metadata()).replace_schema_metadata(schema.metadata)
    elif isinstance(rows, Mapping):
        table = pa.Table.from_pydict(rows, schema=schema)
    else:
        table = pa.Table.from_pylist(list(rows), schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    pq.write_table(
        table,
        partial,
        version="1.0",
        data_page_version="1.0",
        compression="zstd",
        compression_level=3,
        use_dictionary=True,
        write_statistics=True,
        use_compliant_nested_type=True,
        store_schema=True,
        row_group_size=ROW_GROUP_SIZE,
    )
    partial.replace(path)
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "row_count": table.num_rows,
    }


def artifact_record(
    *,
    role: str,
    file_record: Mapping[str, Any],
    collection_root: Path,
    source_sha256: str | Sequence[str] | None = None,
    spatial_profile: str | None = None,
) -> dict[str, Any]:
    record = dict(file_record)
    record["path"] = Path(record["path"]).relative_to(collection_root).as_posix()
    artifact = {
        "role": role,
        "schema_name": role,
        "schema_version": SCHEMA_VERSION,
        "sort_keys": SORT_KEYS[role],
        "files": [record],
    }
    if source_sha256 is not None:
        artifact["source_sha256"] = source_sha256
    if spatial_profile is not None:
        artifact["spatial_profile"] = spatial_profile
    return artifact


def dump_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def physical_problem_sha256(
    components: Mapping[str, str],
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    service_horizon_ms: int,
    relocation_allowed: bool,
) -> str:
    physical_roles = ["requests", "vehicles", "nodes", "travel_times"]
    if "onboard_requests" in components:
        physical_roles.append("onboard_requests")
    value = {
        "format_version": FORMAT_VERSION,
        "components": {
            role: [file["sha256"] for file in artifacts[components[role]]["files"]]
            for role in physical_roles
        },
        "service_horizon_ms": service_horizon_ms,
        "relocation": {
            "allowed": relocation_allowed,
            "destinations": "nodes.relocation_allowed",
        },
    }
    return canonical_sha256(value)


def _normal(value: str) -> bool:
    return value == unicodedata.normalize("NFC", value) and bool(value)


def _check_contiguous(values: list[int], label: str, errors: list[str]) -> None:
    if values != list(range(len(values))):
        errors.append(f"{label} must be sorted, contiguous, and zero-based")


def _package_path(root: Path, relative_path: str) -> Path | None:
    """Resolve a manifest path, or return None if it escapes the package root."""

    if Path(relative_path).is_absolute():
        return None
    path = (root / relative_path).resolve()
    return path if path.is_relative_to(root.resolve()) else None


EXTENSION_COLUMN_PATTERN = re.compile(r"x_[a-z0-9]+(?:_[a-z0-9]+)*__[a-z0-9]+(?:_[a-z0-9]+)*")


def _projjson_validator() -> Draft7Validator:
    """Validator for the vendored PROJJSON v0.7 schema (MIT, PROJ contributors)."""

    schema_path = Path(__file__).with_name("data") / "projjson-0.7.schema.json"
    return Draft7Validator(json.loads(schema_path.read_text(encoding="utf-8")))


_PROJJSON_VALIDATOR = _projjson_validator()


def _extension_errors(
    schema: pa.Schema, core_names: Sequence[str], declared: Any
) -> list[str]:
    """Check extra columns against the artifact's declared extension columns."""

    if not isinstance(declared, list) or not all(
        isinstance(column, Mapping) for column in declared
    ):
        return ["extension_columns must be a list of mappings"]
    declarations = {column.get("name"): column for column in declared}
    errors = []
    for name, column in declarations.items():
        if not isinstance(name, str) or not EXTENSION_COLUMN_PATTERN.fullmatch(name):
            errors.append(f"extension column {name!r} must match x_<organization>__<column>")
            continue
        missing = [
            key
            for key in ("arrow_type", "nullable", "unit", "semantics", "owner")
            if key not in column
        ]
        if missing:
            errors.append(f"extension column {name} missing {', '.join(missing)}")
        if name not in schema.names:
            errors.append(f"declared extension column {name} is absent")
            continue
        field = schema.field(name)
        if str(field.type) != column.get("arrow_type"):
            errors.append(
                f"extension column {name} type {field.type} is not {column.get('arrow_type')}"
            )
        if column.get("nullable") is False and field.nullable:
            errors.append(f"extension column {name} must be non-nullable")
    for name in schema.names:
        if name not in core_names and name not in declarations:
            errors.append(f"undeclared column {name}")
    return errors


def _geo_metadata_errors(metadata: Mapping[bytes, bytes]) -> list[str]:
    try:
        geo = json.loads(metadata[b"geo"])
        column = geo["columns"][geo["primary_column"]]
    except (KeyError, TypeError, json.JSONDecodeError):
        return ["missing or malformed GeoParquet metadata"]
    errors = []
    if geo.get("version") != "1.1.0" or column.get("encoding") != "WKB":
        errors.append("GeoParquet metadata must be version 1.1.0 with WKB encoding")
    if geo.get("primary_column") != "geometry" or column.get("geometry_types") != ["Point"]:
        errors.append("GeoParquet primary column must be a Point `geometry` column")
    crs = column.get("crs")
    if not isinstance(crs, dict) or any(True for _ in _PROJJSON_VALIDATOR.iter_errors(crs)):
        errors.append("GeoParquet crs must be an explicit PROJJSON object")
    return errors


def _is_point_wkb(value: bytes) -> bool:
    """Return whether *value* is a 2D WKB Point with finite coordinates."""

    if len(value) != 21 or value[0] not in (0, 1):
        return False
    order = "<" if value[0] == 1 else ">"
    geometry_type, x, y = struct.unpack(f"{order}Idd", value[1:])
    return geometry_type == 1 and math.isfinite(x) and math.isfinite(y)


def _download_uri(uri: str, directory: Path) -> Path:
    """Download an immutable HTTPS artifact into *directory*."""

    target = directory / hashlib.sha256(uri.encode()).hexdigest()
    request = urllib.request.Request(uri, headers={"User-Agent": "online-darp-benchmark"})
    with urllib.request.urlopen(request) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    return target


def _uri_error(uri: str) -> str | None:
    parts = urlsplit(uri)
    if parts.scheme != "https" or not parts.netloc:
        return "artifact uri must be an absolute https URL"
    segments = parts.path.split("/")
    if "latest" in (segment.lower() for segment in segments):
        return "artifact uri must not be an unversioned latest URL"
    host = parts.netloc.lower()
    ref = None
    if host == "raw.githubusercontent.com" and len(segments) > 3:
        ref = segments[3]
    elif host in {"github.com", "gitlab.com"}:
        for marker in ("raw", "blob"):
            if marker in segments[3:]:
                position = segments.index(marker, 3) + 1
                ref = segments[position] if position < len(segments) else ""
                break
    if ref is not None and not (
        len(ref) in (40, 64) and all(character in "0123456789abcdef" for character in ref)
    ):
        return "artifact uri must pin a full commit hash, not a branch or tag"
    return None


def _instance_errors(instance: Any, collection_id: Any) -> list[str]:
    """Check the instance manifest fields the validator relies on."""

    if not isinstance(instance, Mapping):
        return ["instance manifest must be a mapping"]
    if instance.get("format_version") != FORMAT_VERSION:
        return [f"unsupported format_version: {instance.get('format_version')}"]
    errors = [
        f"missing {key}"
        for key in (
            "instance_id",
            "physical_problem_id",
            "physical_problem_sha256",
            "problem_family",
            "tier",
        )
        if not instance.get(key)
    ]
    if instance.get("collection_id") != collection_id:
        errors.append(f"collection_id must be {collection_id!r}")
    components = instance.get("components")
    if not isinstance(components, Mapping):
        errors.append("components must be a mapping")
    else:
        if missing := sorted(REQUIRED_INSTANCE_ROLES - set(components)):
            errors.append(f"missing components {', '.join(missing)}")
        if unknown := sorted(set(components) - REQUIRED_INSTANCE_ROLES - {"onboard_requests"}):
            errors.append(f"unknown components {', '.join(unknown)}")
    sections = {}
    for key in ("time", "spatial", "relocation"):
        section = instance.get(key)
        if not isinstance(section, Mapping):
            errors.append(f"{key} must be a mapping")
            section = {}
        sections[key] = section
    horizon = sections["time"].get("service_horizon_ms")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 0:
        errors.append("time.service_horizon_ms must be a nonnegative integer")
    if not isinstance(sections["spatial"].get("profile"), str):
        errors.append("spatial.profile must be declared")
    if not isinstance(sections["relocation"].get("allowed"), bool):
        errors.append("relocation.allowed must be a boolean")
    return errors


def _manifest_errors(collection: Any) -> list[str]:
    """Check the collection manifest fields RFC-0001 requires."""

    if not isinstance(collection, Mapping):
        return ["collection.yaml must be a mapping"]
    errors = [
        f"collection.yaml missing {key}"
        for key in ("format_version", "collection_id", "collection_version")
        if not collection.get(key)
    ]
    source = collection.get("source")
    if not isinstance(source, Mapping):
        errors.append("collection.yaml missing source")
    else:
        errors.extend(
            f"collection.yaml missing source.{key}"
            for key in ("source_id", "source_release", "canonical_url", "citations")
            if not source.get(key)
        )
    license_record = collection.get("license")
    if not isinstance(license_record, Mapping) or not license_record.get("spdx_or_name"):
        errors.append("collection.yaml missing license.spdx_or_name")
    elif not isinstance(license_record.get("notice_paths"), list):
        errors.append("collection.yaml license.notice_paths must be a list")
    transformations = collection.get("transformations")
    if not isinstance(transformations, list) or not transformations:
        errors.append("collection.yaml missing transformations")
    else:
        for index, transformation in enumerate(transformations):
            for key in (
                "transformation_id",
                "code_url",
                "code_version",
                "parameters",
                "random_seed",
                "deterministic",
            ):
                if not isinstance(transformation, Mapping) or key not in transformation:
                    errors.append(f"collection.yaml transformations[{index}] missing {key}")
    if not isinstance(collection.get("instances"), list) or not collection["instances"]:
        errors.append("collection.yaml missing instances")
    artifacts = collection.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        errors.append("collection.yaml missing artifacts")
        return errors
    for artifact_id, artifact in artifacts.items():
        if not isinstance(artifact, Mapping):
            errors.append(f"{artifact_id}: artifact must be a mapping")
            continue
        missing = [
            key
            for key in ("role", "schema_name", "schema_version", "sort_keys", "files")
            if key not in artifact
        ]
        if missing:
            errors.append(f"{artifact_id}: missing {', '.join(missing)}")
            continue
        if artifact["schema_name"] not in SORT_KEYS or artifact["role"] != artifact["schema_name"]:
            errors.append(f"{artifact_id}: unknown or mismatched role/schema_name")
            continue
        if artifact["schema_version"] != SCHEMA_VERSION:
            errors.append(f"{artifact_id}: unsupported schema_version {artifact['schema_version']}")
        if artifact["sort_keys"] != SORT_KEYS[artifact["schema_name"]]:
            errors.append(f"{artifact_id}: sort_keys must be {SORT_KEYS[artifact['schema_name']]}")
        if not isinstance(artifact["files"], list) or not artifact["files"]:
            errors.append(f"{artifact_id}: files must be a nonempty list")
            continue
        for file_record in artifact["files"]:
            missing = [
                key
                for key in ("sha256", "byte_size", "row_count")
                if not isinstance(file_record, Mapping) or key not in file_record
            ]
            if missing:
                errors.append(f"{artifact_id}: file record missing {', '.join(missing)}")
    return errors


def _artifact_table(
    root: Path,
    collection: Mapping[str, Any],
    artifact_id: str,
    errors: list[str],
    fetch_uri: Callable[[str], Path],
) -> pa.Table | None:
    artifact = collection["artifacts"].get(artifact_id)
    if artifact is None:
        errors.append(f"unknown artifact: {artifact_id}")
        return None
    tables: list[pa.Table] = []
    for file_record in artifact["files"]:
        if ("path" in file_record) == ("uri" in file_record):
            errors.append(f"{artifact_id}: file locator must be exactly one of path or uri")
            continue
        locator = file_record.get("path") or file_record["uri"]
        if "path" in file_record:
            path = _package_path(root, file_record["path"])
            if path is None:
                errors.append(f"artifact path escapes collection root: {locator}")
                continue
            if not path.is_file():
                errors.append(f"missing artifact file: {locator}")
                continue
        else:
            if uri_error := _uri_error(locator):
                errors.append(f"{uri_error}: {locator}")
                continue
            try:
                path = fetch_uri(locator)
            except OSError as error:
                errors.append(f"unretrievable artifact uri: {locator}: {error}")
                continue
        if path.stat().st_size != file_record["byte_size"]:
            errors.append(f"byte size mismatch: {locator}")
        if sha256_file(path) != file_record["sha256"]:
            errors.append(f"SHA-256 mismatch: {locator}")
        try:
            parquet_file = pq.ParquetFile(path)
            table = parquet_file.read()
        except (OSError, pa.ArrowException) as error:
            errors.append(f"unreadable Parquet artifact: {locator}: {error}")
            continue
        metadata = parquet_file.schema_arrow.metadata or {}
        required_metadata = {
            b"online_darp.format_version": FORMAT_VERSION.encode(),
            b"online_darp.schema_name": artifact["schema_name"].encode(),
            b"online_darp.schema_version": artifact["schema_version"].encode(),
            b"online_darp.collection_id": collection["collection_id"].encode(),
            b"online_darp.artifact_id": artifact_id.encode(),
        }
        for key, expected in required_metadata.items():
            if metadata.get(key) != expected:
                errors.append(f"metadata mismatch for {key.decode()}: {locator}")
        if artifact.get("spatial_profile") == "geographic":
            errors.extend(
                f"{message}: {locator}" for message in _geo_metadata_errors(metadata)
            )
            if "geometry" in table.column_names and not all(
                isinstance(value, bytes) and _is_point_wkb(value)
                for value in table.column("geometry").to_pylist()
            ):
                errors.append(f"geometry values must be finite 2D WKB Points: {locator}")
        if table.num_rows != file_record["row_count"]:
            errors.append(f"row count mismatch: {locator}")
        expected_schema = _schema_for(
            artifact["schema_name"], artifact.get("spatial_profile")
        ).remove_metadata()
        core_names = expected_schema.names
        if not set(core_names) <= set(table.column_names) or not table.select(
            core_names
        ).schema.remove_metadata().equals(expected_schema, check_metadata=False):
            errors.append(f"schema mismatch: {locator}")
            continue
        if extension_errors := _extension_errors(
            table.schema, core_names, artifact.get("extension_columns", [])
        ):
            errors.extend(f"{message}: {locator}" for message in extension_errors)
            continue
        for name in table.column_names:
            column = table.column(name)
            if (
                pa.types.is_floating(column.type)
                and pc.all(pc.is_finite(column)).as_py() is False
            ):
                errors.append(f"non-finite {name} values: {locator}")
        tables.append(table)
    # Semantic checks run only when every file is present, readable, and
    # schema-valid; the failures above are already reported.
    if not tables or len(tables) != len(artifact["files"]):
        return None
    return pa.concat_tables(tables)


def _requests_outside_fleet_shifts(
    requests: pa.Table, vehicles: pa.Table, travel: pa.Table, node_count: int
) -> int:
    """Count requests that no vehicle can serve alone within its shift and limits.

    A vehicle qualifies if it has enough seats, can travel from its start node
    to reach the pickup by the latest pickup time, and can then finish pickup
    service, direct travel, drop-off service, and travel to its terminal (if
    any) within its shift and maximum route duration. Onboard passengers and
    other requests are ignored, so this never rejects a request that the
    vehicle could serve on its own.
    """

    times = travel["travel_time_ms"]
    pickup = pc.cast(requests["pickup_node_index"], pa.int64())
    dropoff = pc.cast(requests["dropoff_node_index"], pa.int64())
    busy = pc.add(
        pc.add(
            requests["pickup_service_time_ms"],
            pc.take(times, pc.add(pc.multiply(pickup, node_count), dropoff)),
        ),
        requests["dropoff_service_time_ms"],
    )
    remaining = pa.table(
        {
            "pickup": pickup,
            "dropoff": dropoff,
            "party_size": requests["party_size"],
            "earliest": requests["earliest_pickup_time_ms"],
            "latest": requests["latest_pickup_time_ms"],
            "busy": busy,
        }
    )
    vehicle_groups = set(
        zip(
            *(
                vehicles[name].to_pylist()
                for name in (
                    "seat_capacity",
                    "start_node_index",
                    "end_node_index",
                    "shift_start_time_ms",
                    "shift_end_time_ms",
                    "max_route_duration_ms",
                )
            ),
            strict=True,
        )
    )
    # Most permissive shifts first, so later groups only see the few requests left.
    for capacity, start_node, end_node, shift_start, shift_end, max_duration in sorted(
        vehicle_groups,
        key=lambda group: (group[3], -group[4], group[5] is not None, -group[0]),
    ):
        if remaining.num_rows == 0:
            break
        to_pickup = pc.take(times, pc.add(remaining["pickup"], start_node * node_count))
        arrival = pc.max_element_wise(pc.add(to_pickup, shift_start), remaining["earliest"])
        finish = pc.add(arrival, remaining["busy"])
        driving = pc.add(to_pickup, remaining["busy"])
        if end_node is not None:
            to_end = pc.take(
                times, pc.add(pc.multiply(remaining["dropoff"], node_count), end_node)
            )
            finish = pc.add(finish, to_end)
            driving = pc.add(driving, to_end)
        served = pc.and_(
            pc.and_(
                pc.less_equal(remaining["party_size"], capacity),
                pc.fill_null(pc.less_equal(arrival, remaining["latest"]), True),
            ),
            pc.less_equal(finish, shift_end),
        )
        if max_duration is not None:
            served = pc.and_(served, pc.less_equal(driving, max_duration))
        remaining = remaining.filter(pc.invert(served))
    return remaining.num_rows


def validate_collection(
    root: Path, *, fetch_uri: Callable[[str], Path] | None = None
) -> dict[str, Any]:
    """Validate package integrity, tables, joins, and core DARP semantics.

    External ``uri`` artifacts are downloaded over HTTPS by default; *fetch_uri*
    may supply another retriever that returns a local file for a URI.
    """

    with tempfile.TemporaryDirectory(prefix="odb-validate-") as download_directory:
        return _validate_collection(
            root,
            fetch_uri or (lambda uri: _download_uri(uri, Path(download_directory))),
        )


def _validate_collection(root: Path, fetch_uri: Callable[[str], Path]) -> dict[str, Any]:
    collection_path = root / "collection.yaml"
    collection = yaml.safe_load(collection_path.read_text(encoding="utf-8"))
    errors: list[str] = _manifest_errors(collection)
    warnings: list[str] = []
    if errors:
        raise CollectionValidationError(
            {
                "collection_id": collection.get("collection_id")
                if isinstance(collection, Mapping)
                else None,
                "valid": False,
                "artifact_count": 0,
                "instance_count": 0,
                "errors": errors,
                "warnings": warnings,
            }
        )
    if collection.get("format_version") != FORMAT_VERSION:
        errors.append(f"unsupported format_version: {collection.get('format_version')}")
    for notice_path in collection.get("license", {}).get("notice_paths", []):
        resolved = _package_path(root, notice_path)
        if resolved is None:
            errors.append(f"license notice path escapes collection root: {notice_path}")
        elif not resolved.is_file():
            errors.append(f"missing license notice: {notice_path}")

    cache: dict[str, pa.Table | None] = {}
    for artifact_id in collection.get("artifacts", {}):
        cache[artifact_id] = _artifact_table(
            root, collection, artifact_id, errors, fetch_uri
        )

    dictionaries = {
        artifact_id: table.to_pydict() if table is not None else None
        for artifact_id, table in cache.items()
    }
    checked_artifacts: set[str] = set()
    checked_relationships: set[tuple[str, ...]] = set()
    physical_fingerprints: dict[Any, str] = {}

    for relative_manifest in collection.get("instances", []):
        manifest_path = _package_path(root, relative_manifest)
        if manifest_path is None:
            errors.append(f"instance manifest escapes collection root: {relative_manifest}")
            continue
        if not manifest_path.is_file():
            errors.append(f"missing instance manifest: {relative_manifest}")
            continue
        instance = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if instance_errors := _instance_errors(instance, collection["collection_id"]):
            errors.extend(f"{relative_manifest}: {message}" for message in instance_errors)
            continue
        components = instance["components"]
        mismatched_roles = [
            role
            for role, artifact_id in components.items()
            if collection["artifacts"].get(artifact_id, {}).get("role") != role
        ]
        if mismatched_roles:
            errors.append(
                f"{relative_manifest}: components reference missing or wrong-role "
                f"artifacts: {', '.join(sorted(mismatched_roles))}"
            )
            continue
        values = {role: dictionaries.get(artifact_id) for role, artifact_id in components.items()}
        if any(value is None for value in values.values()):
            errors.append(f"{relative_manifest}: unresolved component")
            continue

        requests = values["requests"]
        reveals = values["reveal_times"]
        vehicles = values["vehicles"]
        nodes = values["nodes"]
        travel = values["travel_times"]
        node_count = len(nodes["node_index"])

        declared_profile = (instance.get("spatial") or {}).get("profile")
        node_profile = collection["artifacts"][components["nodes"]].get(
            "spatial_profile", "matrix_only"
        )
        if declared_profile != node_profile:
            errors.append(
                f"{relative_manifest}: spatial.profile {declared_profile!r} does not "
                f"match nodes artifact profile {node_profile!r}"
            )
        if requests["request_index"] and not vehicles["vehicle_index"]:
            errors.append(f"{relative_manifest}: requests have no vehicles to serve them")

        for role, index_name, id_name in (
            ("requests", "request_index", "request_id"),
            ("vehicles", "vehicle_index", "vehicle_id"),
            ("nodes", "node_index", "node_id"),
        ):
            artifact_id = components[role]
            if artifact_id in checked_artifacts:
                continue
            value = values[role]
            _check_contiguous(value[index_name], f"{artifact_id}: {index_name}", errors)
            if len(set(value[id_name])) != len(value[id_name]) or not all(
                _normal(item) for item in value[id_name]
            ):
                errors.append(f"{artifact_id}: invalid or duplicate {id_name}")
            checked_artifacts.add(artifact_id)

        request_id = components["requests"]
        if request_id not in checked_artifacts:
            checked_artifacts.add(request_id)
        request_semantics_key = ("request-semantics", request_id)
        if request_semantics_key not in checked_relationships:
            checked_relationships.add(request_semantics_key)
            if any(value < 1 for value in requests["party_size"]):
                errors.append(f"{request_id}: party_size below one")
            if any(value < 0 for value in requests["earliest_pickup_time_ms"]):
                errors.append(f"{request_id}: negative earliest pickup time")
            if any(
                value < 0
                for value in requests["pickup_service_time_ms"]
                + requests["dropoff_service_time_ms"]
            ):
                errors.append(f"{request_id}: negative service time")
            if any(
                value is not None and value < 1 for value in requests["max_ride_time_ms"]
            ):
                errors.append(f"{request_id}: nonpositive maximum ride time")
            for row in range(len(requests["request_index"])):
                for lower_name, upper_name in (
                    ("earliest_pickup_time_ms", "latest_pickup_time_ms"),
                    ("earliest_dropoff_time_ms", "latest_dropoff_time_ms"),
                ):
                    lower = requests[lower_name][row]
                    upper = requests[upper_name][row]
                    if lower is not None and upper is not None and lower > upper:
                        errors.append(f"{request_id}: reversed request time window")

        reveal_id = components["reveal_times"]
        if reveal_id not in checked_artifacts:
            _check_contiguous(
                reveals["request_index"], f"{reveal_id}: request_index", errors
            )
            checked_artifacts.add(reveal_id)
        demand_reveal_key = ("demand-reveal", request_id, reveal_id)
        if demand_reveal_key not in checked_relationships:
            checked_relationships.add(demand_reveal_key)
            if requests["request_index"] != reveals["request_index"]:
                errors.append(f"{relative_manifest}: reveal rows do not match requests")
            else:
                for row, latest in enumerate(requests["latest_pickup_time_ms"]):
                    if latest is not None and reveals["base_reveal_time_ms"][row] > latest:
                        warnings.append(
                            f"{request_id}: request {row} reveals after pickup window"
                        )

        fleet_id = components["vehicles"]
        fleet_semantics_key = ("fleet-semantics", fleet_id)
        if fleet_semantics_key not in checked_relationships:
            checked_relationships.add(fleet_semantics_key)
            if any(value < 1 for value in vehicles["seat_capacity"]):
                errors.append(f"{fleet_id}: vehicle capacity below one")
            if any(value < 0 for value in vehicles["initial_load"]):
                errors.append(f"{fleet_id}: negative initial load")
            if any(
                load > capacity
                for load, capacity in zip(
                    vehicles["initial_load"], vehicles["seat_capacity"], strict=True
                )
            ):
                errors.append(f"{fleet_id}: initial load exceeds vehicle capacity")
            if any(
                end < start
                for start, end in zip(
                    vehicles["shift_start_time_ms"],
                    vehicles["shift_end_time_ms"],
                    strict=True,
                )
            ):
                errors.append(f"{fleet_id}: reversed vehicle shift")
            if any(
                duration is not None and duration < 1
                for duration in vehicles["max_route_duration_ms"]
            ):
                errors.append(f"{fleet_id}: nonpositive maximum route duration")

        shift_key = ("request-shifts", request_id, fleet_id, components["travel_times"])
        referenced_nodes = pa.chunked_array(
            [
                *cache[request_id]["pickup_node_index"].chunks,
                *cache[request_id]["dropoff_node_index"].chunks,
                *cache[fleet_id]["start_node_index"].chunks,
                *pc.drop_null(cache[fleet_id]["end_node_index"]).chunks,
            ],
            type=pa.int32(),
        )
        if (
            shift_key not in checked_relationships
            and requests["request_index"]
            and vehicles["vehicle_index"]
            and len(travel["travel_time_ms"]) == node_count * node_count
            and pc.min(referenced_nodes).as_py() >= 0
            and pc.max(referenced_nodes).as_py() < node_count
        ):
            checked_relationships.add(shift_key)
            unserved = _requests_outside_fleet_shifts(
                cache[request_id], cache[fleet_id], cache[components["travel_times"]], node_count
            )
            if unserved:
                errors.append(
                    f"{relative_manifest}: {unserved} request(s) cannot be served by any "
                    "vehicle within its shift and limits"
                )

        capacity_key = ("request-capacity", request_id, fleet_id)
        if capacity_key not in checked_relationships and vehicles["seat_capacity"]:
            checked_relationships.add(capacity_key)
            largest_vehicle = max(vehicles["seat_capacity"])
            if any(value > largest_vehicle for value in requests["party_size"]):
                errors.append(
                    f"{relative_manifest}: request party_size exceeds every vehicle capacity"
                )

        matrix_key = ("matrix", components["nodes"], components["travel_times"])
        if matrix_key not in checked_relationships:
            checked_relationships.add(matrix_key)
            if len(travel["from_node_index"]) != node_count * node_count:
                errors.append(f"{relative_manifest}: travel matrix is not K squared")
            else:
                for offset, (origin, destination) in enumerate(
                    zip(travel["from_node_index"], travel["to_node_index"], strict=True)
                ):
                    if origin != offset // node_count or destination != offset % node_count:
                        errors.append(
                            f"{relative_manifest}: travel matrix keys are incomplete or unsorted"
                        )
                        break
                for index in range(node_count):
                    if travel["travel_time_ms"][index * node_count + index] != 0:
                        errors.append(f"{relative_manifest}: nonzero travel matrix diagonal")
                        break
            if any(value < 0 for value in travel["travel_time_ms"]):
                errors.append(f"{relative_manifest}: negative travel time")
            if any(value is not None and value < 0 for value in travel["distance_mm"]):
                errors.append(f"{relative_manifest}: negative travel distance")

        feasibility_key = ("request-feasibility", request_id, components["travel_times"])
        if (
            feasibility_key not in checked_relationships
            and len(travel["travel_time_ms"]) == node_count * node_count
        ):
            checked_relationships.add(feasibility_key)
            window_rows: list[int] = []
            ride_rows: list[int] = []
            for row, (pickup, dropoff) in enumerate(
                zip(requests["pickup_node_index"], requests["dropoff_node_index"], strict=True)
            ):
                if not (0 <= pickup < node_count and 0 <= dropoff < node_count):
                    continue
                direct = travel["travel_time_ms"][pickup * node_count + dropoff]
                earliest_arrival = (
                    requests["earliest_pickup_time_ms"][row]
                    + requests["pickup_service_time_ms"][row]
                    + direct
                )
                latest_dropoff = requests["latest_dropoff_time_ms"][row]
                if latest_dropoff is not None and earliest_arrival > latest_dropoff:
                    window_rows.append(row)
                max_ride = requests["max_ride_time_ms"][row]
                if max_ride is not None and direct > max_ride:
                    ride_rows.append(row)
            if window_rows:
                errors.append(
                    f"{relative_manifest}: {len(window_rows)} request(s) cannot reach "
                    f"drop-off by latest_dropoff_time_ms, first row {window_rows[0]}"
                )
            if ride_rows:
                errors.append(
                    f"{relative_manifest}: {len(ride_rows)} request(s) have direct travel "
                    f"longer than max_ride_time_ms, first row {ride_rows[0]}"
                )

        request_nodes_key = ("request-nodes", request_id, components["nodes"])
        if request_nodes_key not in checked_relationships:
            checked_relationships.add(request_nodes_key)
            if any(
                value < 0 or value >= node_count
                for value in requests["pickup_node_index"] + requests["dropoff_node_index"]
            ):
                errors.append(f"{relative_manifest}: request node foreign key out of range")
        fleet_nodes_key = ("fleet-nodes", fleet_id, components["nodes"])
        if fleet_nodes_key not in checked_relationships:
            checked_relationships.add(fleet_nodes_key)
            fleet_nodes = vehicles["start_node_index"] + [
                value for value in vehicles["end_node_index"] if value is not None
            ]
            if any(value < 0 or value >= node_count for value in fleet_nodes):
                errors.append(f"{relative_manifest}: vehicle node foreign key out of range")

        if "onboard_requests" in components:
            onboard_id = components["onboard_requests"]
            onboard = values["onboard_requests"]
            if onboard_id not in checked_artifacts:
                _check_contiguous(
                    onboard["onboard_request_index"],
                    f"{onboard_id}: onboard_request_index",
                    errors,
                )
                if len(set(onboard["onboard_request_id"])) != len(
                    onboard["onboard_request_id"]
                ) or not all(_normal(value) for value in onboard["onboard_request_id"]):
                    errors.append(f"{onboard_id}: invalid or duplicate onboard_request_id")
                checked_artifacts.add(onboard_id)
            onboard_key = (
                "onboard-state",
                onboard_id,
                fleet_id,
                components["nodes"],
            )
            if onboard_key not in checked_relationships:
                checked_relationships.add(onboard_key)
                if any(value < 1 for value in onboard["party_size"]):
                    errors.append(f"{onboard_id}: party_size below one")
                if any(value < 1 for value in onboard["dropoff_route_position"]):
                    errors.append(f"{onboard_id}: route position below one")
                if any(value < 0 for value in onboard["dropoff_service_time_ms"]):
                    errors.append(f"{onboard_id}: negative service time")
                if any(
                    not earliest <= pickup <= departure
                    for earliest, pickup, departure in zip(
                        onboard["earliest_pickup_time_ms"],
                        onboard["pickup_time_ms"],
                        onboard["pickup_departure_time_ms"],
                        strict=True,
                    )
                ):
                    errors.append(f"{onboard_id}: impossible onboard pickup chronology")
                if any(
                    value is not None and value < 1 for value in onboard["max_ride_time_ms"]
                ):
                    errors.append(f"{onboard_id}: nonpositive maximum ride time")
                if any(
                    value < 0 or value >= node_count
                    for value in onboard["pickup_node_index"] + onboard["dropoff_node_index"]
                ):
                    errors.append(f"{onboard_id}: node foreign key out of range")
                if any(
                    value < 0 or value >= len(vehicles["vehicle_index"])
                    for value in onboard["assigned_vehicle_index"]
                ):
                    errors.append(f"{onboard_id}: vehicle foreign key out of range")
                else:
                    loads = [0] * len(vehicles["vehicle_index"])
                    for vehicle_index, party_size in zip(
                        onboard["assigned_vehicle_index"], onboard["party_size"], strict=True
                    ):
                        loads[vehicle_index] += party_size
                    if loads != vehicles["initial_load"]:
                        errors.append(f"{onboard_id}: onboard loads do not match vehicles")
            onboard_deadline_key = (
                "onboard-deadlines",
                onboard_id,
                fleet_id,
                components["travel_times"],
            )
            onboard_rows = range(len(onboard["onboard_request_index"]))
            if (
                onboard_deadline_key not in checked_relationships
                and len(travel["travel_time_ms"]) == node_count * node_count
                and all(
                    0 <= onboard["assigned_vehicle_index"][row] < len(vehicles["vehicle_index"])
                    and 0 <= onboard["dropoff_node_index"][row] < node_count
                    for row in onboard_rows
                )
                and all(
                    0 <= node < node_count
                    for node in vehicles["start_node_index"]
                    + [node for node in vehicles["end_node_index"] if node is not None]
                )
            ):
                checked_relationships.add(onboard_deadline_key)
                expired = unreachable = 0
                for row in onboard_rows:
                    vehicle = onboard["assigned_vehicle_index"][row]
                    dropoff = onboard["dropoff_node_index"][row]
                    # Earliest drop-off: drive straight there from the start node.
                    arrival = (
                        vehicles["shift_start_time_ms"][vehicle]
                        + travel["travel_time_ms"][
                            vehicles["start_node_index"][vehicle] * node_count + dropoff
                        ]
                    )
                    max_ride = onboard["max_ride_time_ms"][row]
                    if (
                        max_ride is not None
                        and arrival > onboard["pickup_departure_time_ms"][row] + max_ride
                    ):
                        expired += 1
                    remaining_work = (
                        arrival
                        - vehicles["shift_start_time_ms"][vehicle]
                        + onboard["dropoff_service_time_ms"][row]
                    )
                    end_node = vehicles["end_node_index"][vehicle]
                    if end_node is not None:
                        remaining_work += travel["travel_time_ms"][
                            dropoff * node_count + end_node
                        ]
                    max_duration = vehicles["max_route_duration_ms"][vehicle]
                    if remaining_work + vehicles["shift_start_time_ms"][vehicle] > vehicles[
                        "shift_end_time_ms"
                    ][vehicle] or (max_duration is not None and remaining_work > max_duration):
                        unreachable += 1
                if expired:
                    errors.append(
                        f"{onboard_id}: {expired} onboard rider(s) cannot reach drop-off "
                        "within max_ride_time_ms"
                    )
                if unreachable:
                    errors.append(
                        f"{onboard_id}: {unreachable} onboard rider(s) cannot be dropped "
                        "off within the assigned vehicle's shift and route duration"
                    )
        elif any(vehicles["initial_load"]):
            errors.append(f"{relative_manifest}: fleet has load but no onboard_requests component")

        expected_fingerprint = physical_problem_sha256(
            components,
            collection["artifacts"],
            service_horizon_ms=instance["time"]["service_horizon_ms"],
            relocation_allowed=instance["relocation"]["allowed"],
        )
        if instance.get("physical_problem_sha256") != expected_fingerprint:
            errors.append(f"{relative_manifest}: physical problem fingerprint mismatch")
        physical_problem_id = instance.get("physical_problem_id")
        known_fingerprint = physical_fingerprints.setdefault(
            physical_problem_id, expected_fingerprint
        )
        if known_fingerprint != expected_fingerprint:
            errors.append(
                f"{relative_manifest}: physical_problem_id {physical_problem_id!r} "
                "is reused for a different physical problem"
            )

    report = {
        "collection_id": collection.get("collection_id"),
        "valid": not errors,
        "artifact_count": len(collection.get("artifacts", {})),
        "instance_count": len(collection.get("instances", [])),
        "errors": errors,
        "warnings": warnings,
    }
    if errors:
        raise CollectionValidationError(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an RFC-0001 Parquet collection")
    parser.add_argument("collection", type=Path, help="collection root containing collection.yaml")
    parser.add_argument("--report", type=Path, help="write the machine-readable YAML report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_collection(args.collection)
    except CollectionValidationError as error:
        if args.report:
            args.report.write_text(str(error), encoding="utf-8")
        print(error, file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, yaml.YAMLError) as error:
        print(error, file=sys.stderr)
        return 1
    rendered = yaml.safe_dump(report, sort_keys=False)
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
