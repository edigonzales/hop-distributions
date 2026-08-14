#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


class NamingError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize short hop-distributions release names after all plugins are assembled."
    )
    parser.add_argument("--metadata-file", required=True)
    parser.add_argument("--geometry-type-tag", required=True)
    parser.add_argument("--geometry-type-name", required=True)
    return parser.parse_args()


def distribution_id(commit_sha: str | None) -> str:
    value = (commit_sha or "").strip()
    if not value:
        return "manual"
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        raise NamingError(f"Unexpected distribution commit SHA: {value}")
    return value[:7].lower()


def finalize_metadata(
    metadata_path: Path,
    *,
    geometry_type_tag: str,
    geometry_type_name: str,
) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    hop_version = str(metadata.get("hop_version", "")).strip()
    if not hop_version:
        raise NamingError("release metadata is missing hop_version")

    dist_id = distribution_id(metadata.get("commit_sha"))
    metadata["distribution_id"] = dist_id
    metadata["geometry_type_release_tag"] = geometry_type_tag
    metadata["geometry_type_release_name"] = geometry_type_name

    seen_names: set[str] = set()
    for artifact in metadata.get("artifacts", []):
        old_name = artifact.get("file")
        target = artifact.get("target")
        if not old_name or not target:
            raise NamingError(f"Invalid artifact metadata: {artifact}")

        old_path = metadata_path.parent / old_name
        if not old_path.is_file():
            raise NamingError(f"Artifact does not exist: {old_path}")

        new_name = f"apache-hop-client-{hop_version}-geo-{dist_id}-{target}.zip"
        if new_name in seen_names:
            raise NamingError(f"Duplicate final artifact name: {new_name}")
        seen_names.add(new_name)

        new_path = metadata_path.parent / new_name
        if new_path != old_path:
            if new_path.exists():
                raise NamingError(f"Refusing to overwrite existing artifact: {new_path}")
            old_path.rename(new_path)
        artifact["file"] = new_name

    metadata["release_tag"] = f"hop-{hop_version}-geo-{dist_id}"
    metadata["release_name"] = f"Apache Hop {hop_version} + Geo Plugins ({dist_id})"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    args = parse_args()
    metadata_path = Path(args.metadata_file)
    try:
        metadata = finalize_metadata(
            metadata_path,
            geometry_type_tag=args.geometry_type_tag,
            geometry_type_name=args.geometry_type_name,
        )
    except (NamingError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
