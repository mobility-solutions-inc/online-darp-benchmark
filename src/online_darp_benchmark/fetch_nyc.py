"""Fetch and assemble the two pinned sources needed by the NYC converter."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .convert_nyc import DYNAMIC_IPS_COMMIT, SOURCE_ARCHIVE_SHA256


ARCHIVE_URL = (
    "https://zenodo.org/api/records/20452171/files/"
    "NYC_Dataset_2015-2016.zip/content"
)
MEDIA_ROOT = (
    "https://media.githubusercontent.com/media/lab-core/dynamic-ips/"
    f"{DYNAMIC_IPS_COMMIT}/data/NYC-DARP-Benchmark/vehicles_warmStart_11"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "online-darp-benchmark"})
    with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    temporary.replace(destination)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError(f"unsafe ZIP member: {member.filename}")
        bundle.extractall(destination)


def fetch(output: Path, local_archive: Path | None = None) -> Path:
    archive = local_archive or output / "NYC_Dataset_2015-2016.zip"
    if local_archive is None and not archive.exists():
        _download(ARCHIVE_URL, archive)
    if _sha256(archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError(f"NYC source archive SHA-256 mismatch: {archive}")

    source_root = output / "NYC_Dataset_2015-2016"
    if not source_root.exists():
        _safe_extract(archive, output)
    warm_root = source_root / "3_Benchmark_instances" / "vehicles_warmStart_11"
    warm_root.mkdir(parents=True, exist_ok=True)
    for vehicle_count in range(1000, 2001, 50):
        for prefix in ("", "ONBOARDS_"):
            filename = f"{prefix}vehicles_{vehicle_count}_4.txt"
            destination = warm_root / filename
            if not destination.exists():
                _download(f"{MEDIA_ROOT}/{filename}", destination)
    return source_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="directory for the assembled pinned source")
    parser.add_argument(
        "--archive",
        type=Path,
        help="use an already downloaded NYC_Dataset_2015-2016.zip",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_root = fetch(args.output, args.archive)
    print(source_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
